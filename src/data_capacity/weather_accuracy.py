"""Bounded, opt-in weather-regime experiment; never changes published behavior.

Frozen before scoring September--December 2024. Conditional hazards only
promote otherwise-VFR rows to the existing degraded/mvfr stratum: this is a
forecast-risk category, not a claim that TEMPO or PROB weather occurred.
Conditional aggregates cannot associate probability with individual hazards.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import capacity_estimate as ce
from .config import REPO_ROOT, resolve_airports
from .io import sha256_file

SPEC = {
    "candidate": "conditional_risk_gust_unknown_v1",
    "train": "airport-local target date in 2023",
    "validation": "airport-local target date 2024-09-01 through 2024-12-31",
    "quantile": 0.90, "demand_percentile": 0.75,
    "conditional_rule": "any conditional TS/frozen/IFR or gust >=25 promotes prevailing VFR to mvfr risk stratum; no probability-as-certainty",
    "wind_rule": "gust crosswind >=15 or gust-scaled tailwind >=10; unknown direction stays unknown unless peak speed <10 bounds both thresholds",
    "adoption": {"macro_pinball_reduction_min": 0.01, "macro_rmse_increase_max": 0.02, "cell_pinball_increase_max": 0.05},
    "headings": {"KATL": 80, "KDFW": 180},
    "limitations": "Reporting-carrier throughput proxy, not facility AAR. Conditional mvfr means forecast risk, not literal MVFR. No probability/hazard linkage recoverable from aggregates.",
}


def classify_candidate(f: pd.DataFrame) -> pd.Series:
    def col(name):
        return pd.to_numeric(f.get(name, pd.Series(np.nan, index=f.index)), errors="coerce")

    ceiling, vis = col("ceiling_ft_agl"), col("visibility_sm")
    cross, tail = col("crosswind_kt"), col("tailwind_kt")
    speed, gust = col("wind_speed_kt"), col("wind_gust_kt")
    peak = pd.concat([speed, gust], axis=1).max(axis=1).where(speed.notna() & gust.notna())
    # Scaling a maximum tailwind by max gust / max speed is only an
    # approximation across overlapping groups; never infer direction from it.
    gust_tail = tail * (peak / speed.where(speed > 0))
    gust_tail = gust_tail.where(speed != 0, tail)
    wind = (cross >= 15) | (col("crosswind_gust_kt") >= 15) | (tail >= 10) | (gust_tail >= 10)
    unresolved = (cross.isna() | tail.isna() | col("crosswind_gust_kt").isna()) & ~(peak < 10)
    conditional = (col("cond_groups") > 0) & (
        (col("cond_thunderstorm_flag") == 1) | (col("cond_frozen_precip_flag") == 1)
        | (col("cond_min_visibility_sm") < 3) | (col("cond_min_ceiling_ft_agl") < 1000)
        | (col("cond_max_gust_kt") >= 25))
    conditions = [col("thunderstorm_flag") == 1, col("frozen_precip_flag") == 1,
                  (ceiling < 1000) | (vis < 3), wind, unresolved,
                  (ceiling < 3000) | (vis < 5) | conditional]
    out = pd.Series(np.select(conditions, ["convective", "winter", "ifr", "wind", "unknown", "mvfr"], "vfr"), index=f.index)
    out[ceiling.isna() | vis.isna()] = "unknown"
    return out


def eligible(snap: pd.DataFrame, model: dict) -> pd.Series:
    return ((snap.scheduled_arrivals >= snap.airport.map(model["demand_thresholds"]))
            & snap.observed_arrivals.notna() & snap.status.isin(["available", "partial"])
            & snap.available_at_utc.notna() & (snap.available_at_utc <= snap.asof_utc)
            & snap.taf_available_at_utc.notna() & (snap.taf_available_at_utc <= snap.asof_utc)
            & (snap.taf_groups_used > 0))


def metrics(g: pd.DataFrame, column: str) -> dict:
    y, p = g.observed_arrivals, g[column]
    return {"n": len(g), "unique_target_hours": int(g.target_hour_utc.nunique()),
            "rmse": float(np.sqrt(np.mean((p-y)**2))), "pinball": ce._pinball(y, p),
            "below_frontier_share": float((y <= p).mean())}


def score(snap, incumbent, candidate, mask):
    before, after = ce.predict(snap, incumbent), ce.predict(snap.assign(weather_regime=classify_candidate(snap)), candidate)
    pool = mask & eligible(snap, incumbent)
    common = pool & before.aar_pred.notna() & after.aar_pred.notna()
    rows = []
    for (airport, lead), g in snap[common].groupby(["airport", "horizon_hours"]):
        ix = g.index
        b, a = before.loc[ix], after.loc[ix]
        severe = b.weather_regime.isin(["convective", "winter"]) | a.weather_regime.isin(["convective", "winter"])
        rows.append({"airport": airport, "lead": int(lead), "incumbent": metrics(b, "aar_pred"),
                     "candidate": metrics(a, "aar_pred"), "airport_baseline": metrics(b, "baseline_frontier"),
                     "eligible_n": int((pool & (snap.airport == airport) & (snap.horizon_hours == lead)).sum()),
                     "support_min": {"incumbent": int(b.support_n.min()), "candidate": int(a.support_n.min())},
                     "backoff_counts": {"incumbent": b.backoff_level.value_counts().to_dict(), "candidate": a.backoff_level.value_counts().to_dict()},
                     "regime_counts": {"incumbent": b.weather_regime.value_counts().to_dict(), "candidate": a.weather_regime.value_counts().to_dict()},
                     "regime_metrics": {"incumbent": {str(k): metrics(v, "aar_pred") for k, v in b.groupby("weather_regime")},
                                        "candidate": {str(k): metrics(v, "aar_pred") for k, v in a.groupby("weather_regime")}},
                     "severe": {"incumbent": metrics(b[severe], "aar_pred"), "candidate": metrics(a[severe], "aar_pred")} if severe.any() else {"n": 0}})
    changed = common & (before.aar_pred != after.aar_pred)
    worse = changed & ((after.aar_pred - snap.observed_arrivals).abs() > (before.aar_pred - snap.observed_arrivals).abs())
    ix = snap[worse].index[:1]
    failure = [{"airport": str(snap.loc[i, "airport"]), "target_hour_utc": str(snap.loc[i, "target_hour_utc"]),
                "lead": int(snap.loc[i, "horizon_hours"]), "observed": float(snap.loc[i, "observed_arrivals"]),
                "incumbent": float(before.loc[i, "aar_pred"]), "candidate": float(after.loc[i, "aar_pred"]),
                "regime_before": str(before.loc[i, "weather_regime"]), "regime_after": str(after.loc[i, "weather_regime"])} for i in ix]
    return {"cells": rows, "failure_example_absolute_error": failure,
            "unique_airport_target_hours": int(snap[common].drop_duplicates(["airport", "target_hour_utc"]).shape[0]),
            "missing_observed_in_window": int((mask & snap.observed_arrivals.isna()).sum()),
            "missing_or_future_features_in_window": int((mask & (~snap.status.isin(["available", "partial"]) | snap.available_at_utc.isna() | (snap.available_at_utc > snap.asof_utc) | snap.taf_available_at_utc.isna() | (snap.taf_available_at_utc > snap.asof_utc) | (snap.taf_groups_used <= 0))).sum()),
            "total_window_snapshots": int(mask.sum()), "eligible_snapshots": int(pool.sum()),
            "common_snapshots": int(common.sum()), "excluded_input_or_demand": int((mask & ~pool).sum()),
            "unavailable_incumbent": int((pool & before.aar_pred.isna()).sum()),
            "unavailable_candidate": int((pool & after.aar_pred.isna()).sum())}


def decision(cells):
    ratios = {m: float(np.mean([c["candidate"][m] for c in cells]) / np.mean([c["incumbent"][m] for c in cells])) for m in ["pinball", "rmse"]}
    worst = max(c["candidate"]["pinball"] / c["incumbent"]["pinball"] for c in cells)
    return {"adopt": len(cells) == 6 and ratios["pinball"] <= .99 and ratios["rmse"] <= 1.02 and worst <= 1.05,
            "macro_pinball_ratio": ratios["pinball"], "macro_rmse_ratio": ratios["rmse"], "worst_cell_pinball_ratio": worst}


def run(output: Path):
    frames, sources = ce.load_published_inputs()
    snap = ce.build_snapshots(frames["weather_features"], frames["traffic_hourly"], resolve_airports(["KATL", "KDFW"]))
    incumbent = ce.fit(snap)
    candidate = ce.fit(snap.assign(weather_regime=classify_candidate(snap)))
    validation = score(snap, incumbent, candidate, snap.target_date_local.between("2024-09-01", "2024-12-31"))
    locked = decision(validation["cells"])
    result = {"specification": SPEC, "source_hashes": sources, "estimator_sha256": sha256_file(Path(ce.__file__)),
              "experiment_sha256": sha256_file(Path(__file__)), "validation": validation, "decision_locked_before_2025": locked,
              "model": candidate, "incumbent_model": incumbent,
              "publication_changed": False}
    # Choice above is immutable: test metrics cannot reject/adopt the candidate.
    result["updated_2025_backtest"] = score(snap, incumbent, candidate, snap.split == "test")
    result["test_disclosure"] = "2025 already inspected by team; updated held-out backtest, not pristine external validation. Not used in selection."
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(locked))


if __name__ == "__main__":
    run(REPO_ROOT / "handover" / "member-1-weather-accuracy-results.json")
