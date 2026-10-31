"""Genuine facility-AAR labels, model fitting and held-out evaluation.

Labels come ONLY from a genuine FAA ASPM export placed in ``data/public/aspm/``
(``*.csv``). Sampled arrival counts, heuristics or synthetic values are never
used as AAR. Without labels the stage publishes an empty typed forecast table
and an ``unavailable`` evaluation with the exact missing input.

Accepted label file schema (case-insensitive headers):
* airport: ``airport`` | ``locid`` | ``facility`` (FAA LOCID or ICAO)
* time, one of:
  - ``hour_start_utc`` (ISO8601), or
  - ``date`` (YYYYMMDD or ISO) + ``hour`` + optional ``quarter``/``minute`` and
    ``time_basis`` column or ``--aar-time-basis`` (``local`` | ``utc``).
    ASPM names ``yyyymmdd``, ``hr_local``/``hr_gmt``, ``qtr`` are recognised.
* AAR: ``aar`` | ``arr_rate`` | ``airport_arrival_rate`` (facility-set rate,
  arrivals per hour).
Quarter-hour records carry hourly RATES: the hourly label is the equal
time-weighted mean of the four quarters (not their sum) and is null unless all
four quarters are present.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import PUBLIC_DIR, Airport
from .features import FEATURE_COLUMNS

ASPM_DIR = PUBLIC_DIR / "aspm"
LABEL_KIND = "facility_aar"
MODEL_VERSION = "aar-hgb-v1"
EXTRA_FEATURES = ["crosswind_upper_kt", "crosswind_gust_kt", "cond_thunderstorm_flag", "cond_min_visibility_sm",
                  "cond_min_ceiling_ft_agl", "cond_max_gust_kt", "obs_wind_speed_kt", "obs_crosswind_kt",
                  "obs_tailwind_kt", "obs_visibility_sm", "obs_ceiling_ft_agl", "obs_precip_flag",
                  "obs_thunderstorm_flag"]
CALENDAR_FEATURES = ["target_hour_local", "target_dow_local", "target_month", "horizon_hours"]

FORECAST_COLUMNS = {
    "airport": "string", "asof_utc": "datetime64[ns, UTC]", "target_hour_utc": "datetime64[ns, UTC]",
    "horizon_hours": "int64", "aar_pred": "float64", "aar_lower": "float64", "aar_upper": "float64",
    "status": "string", "source": "string", "source_id": "string", "label_kind": "string",
    "features_available_at_utc": "datetime64[ns, UTC]", "model_train_end_utc": "datetime64[ns, UTC]",
    "model_selection_end_utc": "datetime64[ns, UTC]", "run_id": "string", "model_version": "string",
    "coverage": "string", "split": "string", "aar_baseline": "float64",
    # parallel-plan 2.3: genuine held-out label, shown by M3 only after outcome reveal
    "aar_observed": "float64",
}


def empty_forecast() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in FORECAST_COLUMNS.items()})


class LabelError(ValueError):
    pass


def _pick(cols: dict, *names):
    for n in names:
        if n in cols:
            return cols[n]
    return None


def load_aar_labels(airports: list[Airport], files: list[Path] | None = None, time_basis: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Return hourly labels (airport ICAO, target_hour_utc, aar) and an audit dict."""
    files = files if files is not None else sorted(ASPM_DIR.glob("*.csv"))
    audit = {"files": [p.as_posix() for p in files], "label_kind": LABEL_KIND}
    if not files:
        audit["status"] = "unavailable"
        audit["reason"] = "no genuine ASPM AAR export found in data/public/aspm/*.csv"
        return pd.DataFrame(columns=["airport", "target_hour_utc", "aar"]), audit
    lookup = {}
    for a in airports:
        lookup[a.icao] = a
        lookup[a.iata] = a
    frames = []
    for path in files:
        raw = pd.read_csv(path)
        cols = {c.strip().lower(): c for c in raw.columns}
        c_ap = _pick(cols, "airport", "locid", "facility")
        c_aar = _pick(cols, "aar", "arr_rate", "airport_arrival_rate")
        if c_ap is None or c_aar is None:
            raise LabelError(f"{path.name}: needs airport/locid and aar columns, got {list(raw.columns)}")
        ap_codes = raw[c_ap].astype(str).str.strip().str.upper()
        unknown = sorted(set(ap_codes) - set(lookup))
        if unknown:
            audit.setdefault("unsupported_airports", []).extend(unknown)
        raw = raw[ap_codes.isin(lookup)].copy()
        ap_codes = ap_codes[raw.index]
        aar = pd.to_numeric(raw[c_aar], errors="coerce")
        c_utc = _pick(cols, "hour_start_utc", "datetime_utc")
        if c_utc is not None:
            ts = pd.to_datetime(raw[c_utc], utc=True)
        else:
            c_date = _pick(cols, "date", "yyyymmdd")
            c_hr_l, c_hr_g = _pick(cols, "hr_local"), _pick(cols, "hr_gmt")
            c_hr = _pick(cols, "hour") or c_hr_l or c_hr_g
            if c_date is None or c_hr is None:
                raise LabelError(f"{path.name}: needs hour_start_utc or date+hour columns")
            basis = time_basis or ("utc" if c_hr == c_hr_g else "local" if c_hr == c_hr_l else None)
            c_basis = _pick(cols, "time_basis")
            if basis is None and c_basis is None:
                raise LabelError(f"{path.name}: hour basis unknown; pass --aar-time-basis local|utc")
            d = pd.to_datetime(raw[c_date].astype(str), format="mixed")
            c_q, c_min = _pick(cols, "quarter", "qtr"), _pick(cols, "minute")
            minute = pd.to_numeric(raw[c_min], errors="coerce") if c_min else (
                (pd.to_numeric(raw[c_q], errors="coerce") - 1) * 15 if c_q else 0)
            naive = d + pd.to_timedelta(pd.to_numeric(raw[c_hr]), unit="h") + pd.to_timedelta(minute, unit="min")
            ts = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns, UTC]")
            row_basis = raw[c_basis].str.lower() if c_basis else pd.Series(basis, index=raw.index)
            for code in ap_codes.unique():
                m = ap_codes == code
                tz = lookup[code].timezone
                mu = m & (row_basis == "utc")
                ml = m & (row_basis == "local")
                ts[mu] = naive[mu].dt.tz_localize("UTC")
                ts[ml] = naive[ml].dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
        frames.append(pd.DataFrame({"airport": ap_codes.map(lambda c: lookup[c].icao), "ts": ts, "aar": aar}))
    lab = pd.concat(frames, ignore_index=True).dropna(subset=["ts"])
    audit["input_records"] = int(len(lab))
    if (lab["aar"].dropna() < 0).any():
        raise LabelError("negative AAR values in label file")
    lab["target_hour_utc"] = lab["ts"].dt.floor("h")
    quarter = (lab["ts"] != lab["target_hour_utc"]).any()
    if quarter:
        g = lab.groupby(["airport", "target_hour_utc"])["aar"]
        hourly = g.agg(["mean", "count"]).reset_index()
        audit["incomplete_quarter_hours"] = int((hourly["count"] < 4).sum())
        hourly["aar"] = hourly["mean"].where(hourly["count"] == 4)
        hourly = hourly[["airport", "target_hour_utc", "aar"]]
        audit["aggregation"] = "mean of 4 quarter-hour rates (time-weighted); incomplete hours null"
    else:
        dup = lab.duplicated(["airport", "target_hour_utc"], keep=False)
        if dup.any():
            raise LabelError(f"{int(dup.sum())} duplicate hourly AAR records")
        hourly = lab[["airport", "target_hour_utc", "aar"]]
        audit["aggregation"] = "hourly records used directly"
    hourly = hourly.dropna(subset=["aar"]).sort_values(["airport", "target_hour_utc"]).reset_index(drop=True)
    audit["hourly_labels"] = int(len(hourly))
    audit["coverage"] = {a: {"first": g["target_hour_utc"].min(), "last": g["target_hour_utc"].max(), "hours": int(len(g))}
                         for a, g in hourly.groupby("airport")}
    audit["status"] = "available" if len(hourly) else "unavailable"
    return hourly, audit


# ------------------------------------------------------------------ modelling

def add_calendar(df: pd.DataFrame, airports: list[Airport]) -> pd.DataFrame:
    df = df.copy()
    tzs = {a.icao: a.timezone for a in airports}
    local_hour = pd.Series(index=df.index, dtype="float64")
    local_dow = pd.Series(index=df.index, dtype="float64")
    local_date = pd.Series(index=df.index, dtype="object")
    for ap, tz in tzs.items():
        m = df["airport"] == ap
        loc = df.loc[m, "target_hour_utc"].dt.tz_convert(tz)
        local_hour[m] = loc.dt.hour
        local_dow[m] = loc.dt.dayofweek
        local_date[m] = loc.dt.date
    df["target_hour_local"] = local_hour
    df["target_dow_local"] = local_dow
    df["target_month"] = df["target_hour_utc"].dt.month
    df["target_date_local"] = pd.to_datetime(local_date)
    return df


def assign_split(df: pd.DataFrame, train_end="2023-12-31", valid_end="2024-12-31", test_end="2025-07-31") -> pd.Series:
    d = df["target_date_local"]
    return pd.Series(np.select([d <= train_end, d <= valid_end, d <= test_end], ["train", "validate", "test"], "out_of_scope"),
                     index=df.index)


def _boundary_utc(airports: list[Airport], local_day: str) -> pd.Timestamp:
    """Latest UTC instant at which the given local date has ended at every airport."""
    return max((pd.Timestamp(local_day) + pd.Timedelta(days=1)).tz_localize(a.timezone).tz_convert("UTC") for a in airports)


def fit_evaluate(features: pd.DataFrame, labels: pd.DataFrame, airports: list[Airport], run_id: str,
                 interval_alpha: float = 0.1) -> tuple[pd.DataFrame, dict]:
    from sklearn.ensemble import HistGradientBoostingRegressor

    df = features.merge(labels, on=["airport", "target_hour_utc"], how="inner")
    df = df[df["status"] != "unavailable"]
    df = add_calendar(df, airports)
    df["split"] = assign_split(df)
    train_end = _boundary_utc(airports, "2023-12-31")
    select_end = _boundary_utc(airports, "2024-12-31")
    # replay cutoffs must follow model selection (no December cutoff for a January target)
    df = df[(df["split"] != "test") | (df["asof_utc"] >= select_end)]
    counts = df["split"].value_counts().to_dict()
    tr, va, te = (df[df["split"] == s] for s in ("train", "validate", "test"))
    if min(len(tr), len(va), len(te)) == 0:
        raise LabelError(f"labels do not cover the contract split (rows per split: {counts}); "
                         "propose a whole-date chronological fallback before reporting metrics")

    feats = FEATURE_COLUMNS + EXTRA_FEATURES + CALENDAR_FEATURES + ["airport_code"]
    codes = {a.icao: i for i, a in enumerate(airports)}
    for part in (tr, va, te, df):
        part["airport_code"] = part["airport"].map(codes)

    def X(part):
        return part[feats].astype("float64").to_numpy()

    # baseline: airport x local-hour mean, fitted on train only
    base = tr.groupby(["airport", "target_hour_local"])["aar"].mean().rename("aar_baseline")
    fallback = tr.groupby("airport")["aar"].mean()

    def baseline(part):
        b = part.join(base, on=["airport", "target_hour_local"])["aar_baseline"]
        return b.fillna(part["airport"].map(fallback))

    grid = [dict(max_depth=d, learning_rate=lr, max_iter=n) for d in (3, 5) for lr in (0.05, 0.1) for n in (200, 400)]
    cat_mask = [f == "airport_code" for f in feats]
    best, best_rmse, cand = None, np.inf, []
    for params in grid:
        m = HistGradientBoostingRegressor(random_state=0, categorical_features=cat_mask, l2_regularization=1.0, **params)
        m.fit(X(tr), tr["aar"])
        r = float(np.sqrt(np.mean((m.predict(X(va)) - va["aar"]) ** 2)))
        cand.append({**params, "validation_rmse": r})
        if r < best_rmse:
            best, best_rmse = m, r

    # split-conformal interval from validation residuals, per horizon
    va_res = (va["aar"] - best.predict(X(va))).abs()
    q = va_res.groupby(va["horizon_hours"]).quantile(1 - interval_alpha)

    te = te.copy()
    te["aar_pred"] = np.clip(best.predict(X(te)), 0, None)
    te["aar_baseline"] = baseline(te)
    te["aar_lower"] = np.clip(te["aar_pred"] - te["horizon_hours"].map(q), 0, None)
    te["aar_upper"] = te["aar_pred"] + te["horizon_hours"].map(q)

    metrics = []
    for (ap, h), g in te.groupby(["airport", "horizon_hours"]):
        err, berr = g["aar_pred"] - g["aar"], g["aar_baseline"] - g["aar"]
        metrics.append({
            "airport": ap, "horizon_hours": int(h), "metric": "rmse", "unit": "arrivals/hour",
            "value": float(np.sqrt(np.mean(err ** 2))), "baseline_value": float(np.sqrt(np.mean(berr ** 2))),
            "mae": float(err.abs().mean()), "n": int(len(g)),
            "interval_coverage": float(((g["aar"] >= g["aar_lower"]) & (g["aar"] <= g["aar_upper"])).mean()),
        })
    cohorts = []
    for name, mask in {
        "thunderstorm_forecast": te["thunderstorm_flag"] == 1,
        "low_ceiling_lt_1000ft": te["ceiling_ft_agl"] < 1000,
        "low_visibility_lt_3sm": te["visibility_sm"] < 3,
        "crosswind_ge_15kt": te["crosswind_kt"] >= 15,
        "benign": (te["thunderstorm_flag"] == 0) & (te["ceiling_ft_agl"] >= 3000) & (te["visibility_sm"] >= 5),
    }.items():
        g = te[mask.fillna(False)]
        if len(g):
            cohorts.append({"cohort": name, "n": int(len(g)),
                            "rmse": float(np.sqrt(np.mean((g["aar_pred"] - g["aar"]) ** 2))),
                            "baseline_rmse": float(np.sqrt(np.mean((g["aar_baseline"] - g["aar"]) ** 2)))})
    worst = te.assign(abs_err=(te["aar_pred"] - te["aar"]).abs()).nlargest(1, "abs_err").iloc[0]
    failure = {k: worst[k] for k in ["airport", "asof_utc", "target_hour_utc", "horizon_hours", "aar", "aar_pred",
                                     "aar_baseline", "aar_lower", "aar_upper", "thunderstorm_flag", "visibility_sm",
                                     "ceiling_ft_agl", "crosswind_kt", "taf_bulletin_id"]}

    fc = pd.DataFrame({
        "airport": te["airport"], "asof_utc": te["asof_utc"], "target_hour_utc": te["target_hour_utc"],
        "horizon_hours": te["horizon_hours"].astype("int64"), "aar_pred": te["aar_pred"],
        "aar_lower": te["aar_lower"], "aar_upper": te["aar_upper"],
        "status": np.where(te["status"] == "available", "available", "partial"),
        "source": "HistGradientBoosting on cutoff-safe IEM TAF/METAR features", "source_id": te["source_id"],
        "label_kind": LABEL_KIND, "features_available_at_utc": te["available_at_utc"],
        "model_train_end_utc": train_end, "model_selection_end_utc": select_end, "run_id": run_id,
        "model_version": MODEL_VERSION, "coverage": "held_out_test", "split": "test", "aar_baseline": te["aar_baseline"],
        "aar_observed": te["aar"],
    }).astype({c: t for c, t in FORECAST_COLUMNS.items() if not t.startswith("datetime")})
    report = {
        "status": "available", "label_kind": LABEL_KIND, "split": {
            "basis": "airport-local date of target hour", "train": "2023-01-01..2023-12-31",
            "validate": "2024-01-01..2024-12-31", "test": "2025-01-01..2025-07-31",
            "rows": {k: int(v) for k, v in counts.items()},
            "excluded_test_cutoffs_before_selection_end": True},
        "model": {"kind": "HistGradientBoostingRegressor", "version": MODEL_VERSION, "selected": best.get_params(),
                  "candidates": cand, "features": feats},
        "baseline": "airport x local-hour mean AAR fitted on 2023 training labels",
        "metrics": metrics, "cohorts": cohorts, "failure_case": failure,
        "uncertainty": {"method": f"split-conformal absolute-residual {(1 - interval_alpha):.0%} quantile on validation, per horizon",
                        "nominal": 1 - interval_alpha, "quantiles_by_horizon": {int(k): float(v) for k, v in q.items()}},
        "model_train_end_utc": train_end, "model_selection_end_utc": select_end,
    }
    return fc, report
