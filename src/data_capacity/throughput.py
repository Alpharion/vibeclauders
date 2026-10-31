"""Forecast of OBSERVED reporting-carrier arrivals per hour (parallel-plan
section 7 stretch). This is NOT AAR and must never be labelled or scored as
AAR.

What it forecasts: ``actual_count`` arrivals (reconstructed wheels-on) in the
target hour from ``traffic_hourly`` - throughput of the BTS reporting-carrier
population, which is bounded by demand, by capacity and by upstream flow
programmes. It is evidence about weather-driven arrival shortfalls, not a
measured runway capacity.

Inputs per snapshot (airport, asof_utc, target_hour_utc, horizon_hours):
* cutoff-safe weather features (available_at_utc <= asof_utc);
* calendar fields of the target hour;
* the published schedule for the target hour (``scheduled_count`` arrivals
  and departures). ASSUMPTION, disclosed in every report: airline schedules are
  published well before the cutoff, so the scheduled count is known at cutoff.
  BTS CRS times are a reconstruction of that schedule, not an as-of snapshot,
  and include flights later cancelled (cancellations are not known at cutoff).

Models (same rows, contract split, selection on validation only):
* ``baseline``: train-only airport x local-hour completion ratio
  (actual / scheduled) times the target hour's scheduled arrivals;
* ``schedule_only``: gradient boosting on schedule + calendar;
* ``weather``: schedule + calendar + weather features.
``weather`` vs ``schedule_only`` isolates what the weather forecast adds; the
difference is reported with a date-block bootstrap interval.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .capacity import EXTRA_FEATURES, _boundary_utc, add_calendar, assign_split
from .config import Airport
from .features import FEATURE_COLUMNS
from .traffic import POPULATION

LABEL_KIND = "observed_reporting_carrier_arrivals"
MODEL_VERSION = "arrivals-hgb-v1"
NOT_AAR = ("Forecast of observed reporting-carrier arrivals per hour (throughput). NOT the facility Airport "
           "Arrival Rate (AAR): counts are limited by demand, by BTS coverage and by upstream flow programmes, "
           "so they do not measure runway capacity. Never report this as AAR or AAR RMSE.")
SCHEDULE_FEATURES = ["scheduled_arrivals", "scheduled_departures"]
CALENDAR = ["target_hour_local", "target_dow_local", "target_month", "horizon_hours", "airport_code"]
WEATHER = FEATURE_COLUMNS + EXTRA_FEATURES
ASSUMPTIONS = [
    "Airline schedules are published well before the cutoff, so the target hour's scheduled count is treated "
    "as known at cutoff. BTS CRS times reconstruct that schedule (not an as-of snapshot) and include flights "
    "later cancelled.",
    "Target = reporting-carrier arrivals with reconstructed wheels-on in the target hour; cancelled and diverted "
    "flights do not count; hours flagged uncertain in traffic_hourly are excluded.",
    "Weather inputs are the cutoff-safe weather_features rows (available_at_utc <= asof_utc).",
]

COLUMNS = {
    "airport": "string", "asof_utc": "datetime64[ns, UTC]", "target_hour_utc": "datetime64[ns, UTC]",
    "horizon_hours": "int64", "arrivals_pred": "float64", "arrivals_lower": "float64", "arrivals_upper": "float64",
    "arrivals_pred_schedule_only": "float64", "arrivals_baseline": "float64", "arrivals_observed": "float64",
    "scheduled_arrivals": "float64", "status": "string", "label_kind": "string", "source_id": "string",
    "features_available_at_utc": "datetime64[ns, UTC]", "model_train_end_utc": "datetime64[ns, UTC]",
    "model_selection_end_utc": "datetime64[ns, UTC]", "run_id": "string", "model_version": "string",
    "coverage": "string", "population": "string",
}


def empty_forecast() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in COLUMNS.items()})


class ThroughputError(ValueError):
    pass


def build_dataset(features: pd.DataFrame, traffic: pd.DataFrame, airports: list[Airport]) -> pd.DataFrame:
    """Join snapshots to the target hour's schedule and observed arrivals."""
    # pivot (not pivot_table) keeps all-null columns; the traffic key is unique
    wide = traffic.pivot(index=["airport", "hour_utc"], columns="direction", values=["scheduled_count", "actual_count"])
    wide.columns = [f"{a}_{d}" for a, d in wide.columns]
    wide = wide.reset_index().rename(columns={
        "hour_utc": "target_hour_utc", "scheduled_count_arrival": "scheduled_arrivals",
        "scheduled_count_departure": "scheduled_departures", "actual_count_arrival": "arrivals_observed"})
    df = features.merge(wide[["airport", "target_hour_utc", "scheduled_arrivals", "scheduled_departures",
                              "arrivals_observed"]], on=["airport", "target_hour_utc"], how="inner")
    df = df[(df["status"] != "unavailable") & df["arrivals_observed"].notna()].copy()
    for c in SCHEDULE_FEATURES + ["arrivals_observed"]:
        df[c] = df[c].astype("float64")
    df = add_calendar(df, airports)
    df["airport_code"] = df["airport"].map({a.icao: i for i, a in enumerate(airports)})
    df["split"] = assign_split(df)
    return df


def weather_impacted(df: pd.DataFrame) -> pd.Series:
    """Cutoff-time forecast of thunderstorm, frozen precipitation, ceiling < 1000 ft or visibility < 3 SM."""
    return ((df["thunderstorm_flag"] == 1) | (df["frozen_precip_flag"] == 1) | (df["ceiling_ft_agl"] < 1000)
            | (df["visibility_sm"] < 3)).fillna(False).astype(bool)


def _rmse(err) -> float:
    return float(np.sqrt(np.mean(np.square(err))))


def _fit_best(X_tr, y_tr, X_va, y_va, cat_mask):
    from sklearn.ensemble import HistGradientBoostingRegressor

    best, best_rmse, cands = None, np.inf, []
    for depth in (4, 6):
        for lr in (0.05, 0.1):
            m = HistGradientBoostingRegressor(max_depth=depth, learning_rate=lr, max_iter=300, l2_regularization=1.0,
                                              categorical_features=cat_mask, random_state=0)
            m.fit(X_tr, y_tr)
            r = _rmse(m.predict(X_va) - y_va)
            cands.append({"max_depth": depth, "learning_rate": lr, "max_iter": 300, "validation_rmse": r})
            if r < best_rmse:
                best, best_rmse = m, r
    return best, cands


def _bootstrap_diff(te: pd.DataFrame, a: str, b: str, n_boot: int = 200, seed: int = 0) -> dict:
    """RMSE(a) - RMSE(b) with a 95% interval from resampling whole target dates."""
    rng = np.random.default_rng(seed)
    dates = te["target_date_local"].to_numpy()
    uniq = np.unique(dates)
    sq_a = (te[a] - te["arrivals_observed"]) ** 2
    sq_b = (te[b] - te["arrivals_observed"]) ** 2
    by_date = pd.DataFrame({"d": dates, "a": sq_a.to_numpy(), "b": sq_b.to_numpy()}).groupby("d").agg(
        sa=("a", "sum"), sb=("b", "sum"), n=("a", "size"))
    diffs = []
    for _ in range(n_boot):
        pick = by_date.loc[rng.choice(uniq, size=len(uniq), replace=True)]
        diffs.append(np.sqrt(pick["sa"].sum() / pick["n"].sum()) - np.sqrt(pick["sb"].sum() / pick["n"].sum()))
    point = _rmse(te[a] - te["arrivals_observed"]) - _rmse(te[b] - te["arrivals_observed"])
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"rmse_difference": float(point), "ci95": [float(lo), float(hi)], "resampled_unit": "target local date",
            "n_boot": n_boot}


def fit_evaluate(features: pd.DataFrame, traffic: pd.DataFrame, airports: list[Airport], run_id: str,
                 storm_hours: pd.DataFrame | None = None, interval_alpha: float = 0.1) -> tuple[pd.DataFrame, dict]:
    df = build_dataset(features, traffic, airports)
    train_end = _boundary_utc(airports, "2023-12-31")
    select_end = _boundary_utc(airports, "2024-12-31")
    df = df[(df["split"] != "test") | (df["asof_utc"] >= select_end)]
    counts = {k: int(v) for k, v in df["split"].value_counts().items()}
    tr, va, te = (df[df["split"] == s].copy() for s in ("train", "validate", "test"))
    if min(len(tr), len(va), len(te)) == 0:
        raise ThroughputError(f"traffic/features do not cover the contract split (rows per split: {counts})")

    # baseline: completion ratio by airport x local hour, training rows only
    ratio = (tr.groupby(["airport", "target_hour_local"])[["arrivals_observed", "scheduled_arrivals"]].sum()
             .pipe(lambda g: g["arrivals_observed"] / g["scheduled_arrivals"].replace(0, np.nan)).rename("ratio"))
    overall = tr.groupby("airport").apply(lambda g: g["arrivals_observed"].sum() / max(g["scheduled_arrivals"].sum(), 1))

    def baseline(part):
        r = part.join(ratio, on=["airport", "target_hour_local"])["ratio"].fillna(part["airport"].map(overall))
        return r * part["scheduled_arrivals"]

    sets = {"schedule_only": SCHEDULE_FEATURES + CALENDAR, "weather": SCHEDULE_FEATURES + CALENDAR + WEATHER}
    models, candidates = {}, {}
    for name, cols in sets.items():
        cat = [c == "airport_code" for c in cols]
        X = lambda p, cols=cols: p[cols].astype("float64").to_numpy()  # noqa: E731
        models[name], candidates[name] = _fit_best(X(tr), tr["arrivals_observed"], X(va), va["arrivals_observed"], cat)
        for part in (va, te):
            part[f"pred_{name}"] = np.clip(models[name].predict(X(part)), 0, None)
    for part in (va, te):
        part["pred_baseline"] = baseline(part)

    # Mondrian split-conformal: one residual quantile per (horizon, weather-impacted) group, so
    # benign hours do not set the width of intervals in storms
    for part in (va, te):
        part["impacted"] = weather_impacted(part)
    q = (va["arrivals_observed"] - va["pred_weather"]).abs().groupby(
        [va["horizon_hours"], va["impacted"]]).quantile(1 - interval_alpha)
    half = pd.Series([q.get((h, i), np.nan) for h, i in zip(te["horizon_hours"], te["impacted"])], index=te.index)
    te["lower"] = np.clip(te["pred_weather"] - half, 0, None)
    te["upper"] = te["pred_weather"] + half

    def score(g):
        y = g["arrivals_observed"]
        return {"n": int(len(g)),
                "rmse_weather": _rmse(g["pred_weather"] - y), "rmse_schedule_only": _rmse(g["pred_schedule_only"] - y),
                "rmse_baseline": _rmse(g["pred_baseline"] - y), "mae_weather": float((g["pred_weather"] - y).abs().mean()),
                "mean_observed": float(y.mean()),
                "interval_coverage": float(((y >= g["lower"]) & (y <= g["upper"])).mean())}

    metrics = [{"airport": a, "horizon_hours": int(h), "unit": "observed reporting-carrier arrivals/hour", **score(g)}
               for (a, h), g in te.groupby(["airport", "horizon_hours"])]
    peak_cut = tr.groupby("airport")["scheduled_arrivals"].quantile(0.9)
    cohort_masks = {
        "thunderstorm_forecast": te["thunderstorm_flag"] == 1,
        "frozen_precip_forecast": te["frozen_precip_flag"] == 1,
        "low_ceiling_lt_1000ft": te["ceiling_ft_agl"] < 1000,
        "low_visibility_lt_3sm": te["visibility_sm"] < 3,
        "crosswind_ge_15kt": te["crosswind_kt"] >= 15,
        "peak_schedule_ge_train_p90": te["scheduled_arrivals"] >= te["airport"].map(peak_cut),
        "benign": (te["thunderstorm_flag"] == 0) & (te["ceiling_ft_agl"] >= 3000) & (te["visibility_sm"] >= 5),
    }
    te["storm_event_types"] = None
    if storm_hours is not None and len(storm_hours):
        types = te[["airport", "target_hour_utc"]].merge(storm_hours, on=["airport", "target_hour_utc"], how="left")
        te["storm_event_types"] = types["storm_event_types"].to_numpy()
        cohort_masks["noaa_storm_event_hour_retrospective"] = te["storm_event_types"].notna()
    cohorts = [{"cohort": k, **score(te[m.fillna(False)])} for k, m in cohort_masks.items() if m.fillna(False).sum() > 0]

    impacted = te["impacted"]
    te["abs_err"] = (te["pred_weather"] - te["arrivals_observed"]).abs()
    worst = te.nlargest(1, "abs_err").iloc[0]
    failure = {k: worst[k] for k in ["airport", "asof_utc", "target_hour_utc", "horizon_hours", "arrivals_observed",
                                     "pred_weather", "pred_schedule_only", "pred_baseline", "scheduled_arrivals",
                                     "lower", "upper", "thunderstorm_flag", "frozen_precip_flag", "precip_flag",
                                     "visibility_sm", "ceiling_ft_agl", "crosswind_kt", "taf_bulletin_id",
                                     "storm_event_types"]}
    failure["kind"] = "largest held-out error of the weather model"
    failure["evidence"] = (f"Cutoff-time TAF {worst['taf_bulletin_id']}: precip_flag={worst['precip_flag']}, "
                           f"frozen_precip_flag={worst['frozen_precip_flag']}, thunderstorm_flag={worst['thunderstorm_flag']}, "
                           f"visibility {worst['visibility_sm']} SM, ceiling {worst['ceiling_ft_agl']} ft. "
                           f"Retrospective NOAA events in the hour: {worst['storm_event_types'] or 'none'}. "
                           f"{worst['scheduled_arrivals']:.0f} arrivals scheduled, {worst['arrivals_observed']:.0f} observed.")
    failure["explanation"] = ("Arrivals can collapse far below schedule when airlines cancel in advance of a rare "
                              "event; the model only sees the scheduled count (which includes those cancellations) "
                              "and few comparable training hours. The error is a property of the throughput target, "
                              "not evidence about runway capacity.")

    fc = pd.DataFrame({
        "airport": te["airport"], "asof_utc": te["asof_utc"], "target_hour_utc": te["target_hour_utc"],
        "horizon_hours": te["horizon_hours"].astype("int64"), "arrivals_pred": te["pred_weather"],
        "arrivals_lower": te["lower"], "arrivals_upper": te["upper"],
        "arrivals_pred_schedule_only": te["pred_schedule_only"], "arrivals_baseline": te["pred_baseline"],
        "arrivals_observed": te["arrivals_observed"], "scheduled_arrivals": te["scheduled_arrivals"],
        "status": np.where(te["status"] == "available", "available", "partial"), "label_kind": LABEL_KIND,
        "source_id": "bts_ontime_prezip+" + te["source_id"].astype(str), "features_available_at_utc": te["available_at_utc"],
        "model_train_end_utc": train_end, "model_selection_end_utc": select_end, "run_id": run_id,
        "model_version": MODEL_VERSION, "coverage": "held_out_test", "population": POPULATION,
    }).astype({c: t for c, t in COLUMNS.items() if not t.startswith("datetime")})
    fc = fc.sort_values(["airport", "asof_utc", "horizon_hours"]).reset_index(drop=True)

    overall_scores = score(te)
    report = {
        "status": "available", "label_kind": LABEL_KIND, "not_aar": NOT_AAR,
        "team_agreement": {"status": "agreed", "required_by": "parallel-plan section 7 (all three members)",
                           "recorded_at_utc": "2026-10-31T09:10:42Z",
                           "note": "All three members agreed to present it, as reported by Member 1's supervisor. "
                                   "Still labelled throughput, never AAR."},
        "assumptions": ASSUMPTIONS,
        "split": {"basis": "airport-local date of target hour", "train": "2023", "validate": "2024",
                  "test": "2025-01-01..2025-07-31", "rows": counts, "excluded_test_cutoffs_before_selection_end": True},
        "models": {name: {"features": cols, "selected": models[name].get_params(), "candidates": candidates[name]}
                   for name, cols in sets.items()},
        "baseline": "train-only airport x local-hour completion ratio x scheduled arrivals",
        "overall": overall_scores,
        "weather_value": {"weather_minus_schedule_only": _bootstrap_diff(te, "pred_weather", "pred_schedule_only"),
                          "weather_minus_baseline": _bootstrap_diff(te, "pred_weather", "pred_baseline"),
                          "weather_impacted_hours": {
                              "definition": "thunderstorm, frozen precipitation, ceiling < 1000 ft or visibility < 3 SM forecast at cutoff",
                              "n": int(impacted.sum()),
                              "weather_minus_schedule_only": _bootstrap_diff(te[impacted], "pred_weather", "pred_schedule_only")},
                          "reading": "negative = the weather model has lower RMSE"},
        "metrics": metrics, "cohorts": cohorts, "failure_case": failure,
        "uncertainty": {"method": f"Mondrian split-conformal absolute residual, {(1 - interval_alpha):.0%} quantile on "
                                  "validation, per (horizon, weather-impacted) group",
                        "nominal": 1 - interval_alpha,
                        "half_width_by_group": [{"horizon_hours": int(h), "weather_impacted": bool(i), "half_width": float(v)}
                                                for (h, i), v in q.items()]},
        "model_train_end_utc": train_end, "model_selection_end_utc": select_end,
    }
    return fc, report
