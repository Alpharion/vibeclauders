"""Weather-conditioned empirical arrival-capacity PROXY (sprint interface,
``artifacts/capacity_estimate/``).

Not facility AAR. A capacity proxy for the BTS reporting-carrier population,
under the assumption that throughput in high-demand hours is informative about
attainable arrival rates. Low demand, restricted coverage and flow programmes
prevent identification of physical airport capacity.

Method ``high_demand_weather_frontier_v1`` (all parameters fixed in advance; no tuning):
1. Hour table: one row per (airport, target hour) from ``traffic_hourly``
   arrivals, so the three leads never count one hour three times.
2. Demand screen: an hour is high-demand when its scheduled arrivals are at or
   above the airport's 2023 (training) 75th percentile of scheduled arrivals.
3. Weather regime of each snapshot from cutoff-safe ``weather_features``
   (priority order): convective (TS) > winter (frozen precipitation) >
   ifr (ceiling < 1000 ft or visibility < 3 SM) > wind (crosswind >= 15 kt or
   tailwind >= 10 kt) > mvfr (ceiling < 3000 ft or visibility < 5 SM) > vfr.
   Missing ceiling or visibility -> unknown.
4. Frontier cell (airport, lead, regime): 0.90 quantile of observed arrivals in
   high-demand TRAINING hours of that cell; ``support_n`` = unique training hours.
5. Backoff when support < 30 hours: (airport, lead, regime) ->
   (airport, lead, degraded|vfr) -> (airport, lead, all regimes). Unknown regime
   uses the all-regime cell. Level and cell identity are recorded per row.
Splits by airport-local date of the target hour: train 2023 (fit), validate
2024 (reported, no selection), held-out replay Jan-Jul 2025. Only cutoffs at or
after the end of 2024 are emitted.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import PRODUCER, SCHEMA_VERSION
from .capacity import _boundary_utc, add_calendar, assign_split
from .config import CAPACITY_DIR, REPO_ROOT, Airport, new_run_id, resolve_airports, utcnow
from .io import sha256_file, write_json, write_parquet
from .traffic import POPULATION

OUT_DIR = REPO_ROOT / "artifacts" / "capacity_estimate"
METHOD = "high_demand_weather_frontier_v1"
MODEL_VERSION = "capacity-proxy-frontier-v1"
ASSUMPTIONS_ID = "capacity-proxy-assumptions-v1"
LABEL_KIND = "model_estimated_capacity"
VALIDATION_TARGET = "high_demand_observed_reporting_carrier_arrivals"
DEMAND_PERCENTILE = 0.75
FRONTIER_QUANTILE = 0.90
MIN_SUPPORT = 30
REGIMES = ("convective", "winter", "ifr", "wind", "mvfr", "vfr")
DEGRADED = {"convective", "winter", "ifr", "wind", "mvfr"}
LIMITATIONS = [
    "Model-estimated capacity PROXY, not facility AAR: no independent facility AAR label exists for validation.",
    "Population is BTS reporting carriers only; no scaling to whole-airport rates (cargo, GA, military and most "
    "international flights are excluded).",
    "Throughput in high-demand hours is assumed informative about attainable rates; low demand, flow programmes "
    "and coverage limits mean the frontier can understate physical capacity.",
    "Uncertainty bounds are not estimated (uncertainty_kind='unavailable').",
    "Validation compares the frozen frontier to observed high-demand throughput, a proxy target - not AAR accuracy.",
]
INPUTS = {
    "traffic_hourly": "artifacts/capacity/traffic_hourly.parquet",
    "weather_features": "artifacts/capacity/weather_features.parquet",
}

FORECAST_COLUMNS = {
    "airport": "string", "asof_utc": "datetime64[ns, UTC]", "target_hour_utc": "datetime64[ns, UTC]",
    "horizon_hours": "int64", "aar_pred": "float64", "aar_lower": "float64", "aar_upper": "float64",
    "status": "string", "source": "string", "source_id": "string", "label_kind": "string",
    "features_available_at_utc": "datetime64[ns, UTC]", "model_train_end_utc": "datetime64[ns, UTC]",
    "model_selection_end_utc": "datetime64[ns, UTC]", "run_id": "string", "model_version": "string",
    "coverage": "string", "aar_observed": "float64", "population": "string", "estimation_method": "string",
    "assumptions_id": "string", "validation_target": "string", "uncertainty_kind": "string",
    "support_n": "Int64", "weather_regime": "string", "frontier_cell": "string", "backoff_level": "string",
}


class EstimateError(ValueError):
    pass


# ----------------------------------------------------------------- inputs

def load_published_inputs(root: Path = REPO_ROOT) -> tuple[dict[str, pd.DataFrame], dict]:
    """Read only committed capacity inputs after verifying the capacity manifest hashes."""
    manifest_path = root / "artifacts" / "capacity" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = manifest.get("artifact_hashes") or {}
    frames, sources = {}, []
    for name, rel in INPUTS.items():
        path = root / rel
        key = Path(rel).relative_to("artifacts/capacity").as_posix()
        declared = hashes.get(key)
        if not path.exists():
            raise EstimateError(f"{rel} is not published")
        actual = sha256_file(path)
        if declared is None or declared != actual:
            raise EstimateError(f"{rel}: SHA256 does not match artifacts/capacity/manifest.json")
        df = pd.read_parquet(path)
        if "run_id" in df and set(df["run_id"]) != {manifest["run_id"]}:
            raise EstimateError(f"{rel}: run_id differs from the capacity manifest")
        frames[name] = df
        sources.append({"name": name, "path": rel, "sha256": actual, "upstream_run_id": manifest["run_id"]})
    return frames, {"capacity_manifest": "artifacts/capacity/manifest.json",
                    "capacity_manifest_sha256": sha256_file(manifest_path),
                    "upstream_run_id": manifest["run_id"], "inputs": sources}


# ----------------------------------------------------------------- model

def classify_regime(f: pd.DataFrame) -> pd.Series:
    ceiling, vis = f["ceiling_ft_agl"], f["visibility_sm"]
    cross = f["crosswind_kt"].fillna(0)
    tail = f["tailwind_kt"].fillna(0)
    conds = [
        f["thunderstorm_flag"].fillna(0).astype(int) == 1,
        f.get("frozen_precip_flag", pd.Series(0, index=f.index)).fillna(0).astype(int) == 1,
        (ceiling < 1000) | (vis < 3),
        (cross >= 15) | (tail >= 10),
        (ceiling < 3000) | (vis < 5),
    ]
    regime = pd.Series(np.select(conds, REGIMES[:5], "vfr"), index=f.index, dtype="object")
    regime[ceiling.isna() | vis.isna()] = "unknown"
    return regime


def build_snapshots(features: pd.DataFrame, traffic: pd.DataFrame, airports: list[Airport]) -> pd.DataFrame:
    arr = traffic[traffic["direction"] == "arrival"][["airport", "hour_utc", "scheduled_count", "actual_count"]]
    arr = arr.rename(columns={"hour_utc": "target_hour_utc", "scheduled_count": "scheduled_arrivals",
                              "actual_count": "observed_arrivals"})
    df = features.merge(arr, on=["airport", "target_hour_utc"], how="left")
    df["observed_arrivals"] = df["observed_arrivals"].astype("float64")
    df["scheduled_arrivals"] = df["scheduled_arrivals"].astype("float64")
    df = add_calendar(df, airports)
    df["split"] = assign_split(df)
    df["weather_regime"] = classify_regime(df)
    return df


def fit(snap: pd.DataFrame) -> dict:
    """Fit thresholds and frontier cells from TRAINING rows only."""
    train = snap[snap["split"] == "train"]
    hours = train.drop_duplicates(["airport", "target_hour_utc"])  # one row per hour for demand
    thresholds = hours.groupby("airport")["scheduled_arrivals"].quantile(DEMAND_PERCENTILE).to_dict()
    screened = train[(train["scheduled_arrivals"] >= train["airport"].map(thresholds))
                     & train["observed_arrivals"].notna()]
    cells = []

    def add(level, airport, lead, regime_key, rows):
        uniq = rows.drop_duplicates(["airport", "target_hour_utc"])
        n = len(uniq)
        cells.append({"level": level, "airport": airport, "horizon_hours": int(lead), "regime": regime_key,
                      "support_n": int(n),
                      "estimate": float(uniq["observed_arrivals"].quantile(FRONTIER_QUANTILE)) if n else None})

    for (airport, lead), g in screened.groupby(["airport", "horizon_hours"]):
        for regime in REGIMES:
            add("regime", airport, lead, regime, g[g["weather_regime"] == regime])
        add("group", airport, lead, "degraded", g[g["weather_regime"].isin(DEGRADED)])
        add("group", airport, lead, "vfr", g[g["weather_regime"] == "vfr"])
        add("airport", airport, lead, "all", g)
    baseline = {a: float(g.drop_duplicates("target_hour_utc")["observed_arrivals"].quantile(FRONTIER_QUANTILE))
                for a, g in screened.groupby("airport")}
    return {"demand_thresholds": {k: float(v) for k, v in thresholds.items()}, "cells": cells,
            "baseline_airport_frontier": baseline}


def predict(snap: pd.DataFrame, model: dict) -> pd.DataFrame:
    table = {(c["airport"], c["horizon_hours"], c["regime"]): c for c in model["cells"]}
    est, support, cell_id, level = [], [], [], []
    for airport, lead, regime in zip(snap["airport"], snap["horizon_hours"], snap["weather_regime"]):
        chain = []
        if regime != "unknown":
            chain += [("regime", regime), ("group", "degraded" if regime in DEGRADED else "vfr")]
        chain.append(("airport", "all"))
        chosen = None
        for lvl, key in chain:
            c = table.get((airport, int(lead), key))
            if c and c["estimate"] is not None and c["support_n"] >= MIN_SUPPORT:
                chosen = (lvl, key, c)
                break
        if chosen is None:
            est.append(np.nan); support.append(pd.NA); cell_id.append(None); level.append("unavailable")
        else:
            lvl, key, c = chosen
            est.append(c["estimate"]); support.append(c["support_n"])
            cell_id.append(f"{airport}/h{int(lead)}/{key}"); level.append(lvl)
    out = snap.copy()
    out["aar_pred"], out["support_n"], out["frontier_cell"], out["backoff_level"] = est, support, cell_id, level
    out["baseline_frontier"] = out["airport"].map(model["baseline_airport_frontier"])
    return out


def _pinball(y, q, tau=FRONTIER_QUANTILE) -> float:
    d = y - q
    return float(np.mean(np.maximum(tau * d, (tau - 1) * d)))


def evaluate(pred: pd.DataFrame, model: dict, split: str) -> list[dict]:
    """Frozen frontier vs observed throughput in high-demand hours (proxy target)."""
    p = pred[(pred["split"] == split) & pred["aar_pred"].notna() & pred["observed_arrivals"].notna()]
    p = p[p["scheduled_arrivals"] >= p["airport"].map(model["demand_thresholds"])]
    rows = []
    for (airport, lead), g in p.groupby(["airport", "horizon_hours"]):
        y = g["observed_arrivals"]
        for metric, value, base in (
            ("high_demand_throughput_rmse", float(np.sqrt(np.mean((g["aar_pred"] - y) ** 2))),
             float(np.sqrt(np.mean((g["baseline_frontier"] - y) ** 2)))),
            (f"pinball_loss_q{FRONTIER_QUANTILE:.2f}", _pinball(y, g["aar_pred"]), _pinball(y, g["baseline_frontier"])),
            ("share_high_demand_hours_at_or_below_frontier", float((y <= g["aar_pred"]).mean()),
             float((y <= g["baseline_frontier"]).mean())),
        ):
            rows.append({"split": split, "airport": airport, "horizon_hours": int(lead), "metric": metric,
                         "value": value, "baseline_value": base, "n": int(len(g)),
                         "units": "share" if metric.startswith("share") else "reporting-carrier arrivals/hour"})
    return rows


def regime_cohorts(pred: pd.DataFrame, model: dict, split: str) -> list[dict]:
    p = pred[(pred["split"] == split) & pred["aar_pred"].notna() & pred["observed_arrivals"].notna()]
    p = p[p["scheduled_arrivals"] >= p["airport"].map(model["demand_thresholds"])]
    out = []
    for (airport, regime), g in p.groupby(["airport", "weather_regime"]):
        y = g["observed_arrivals"]
        out.append({"split": split, "airport": airport, "weather_regime": regime, "n_snapshots": int(len(g)),
                    "n_unique_hours": int(g["target_hour_utc"].nunique()),
                    "mean_estimate": float(g["aar_pred"].mean()), "mean_observed": float(y.mean()),
                    "high_demand_throughput_rmse": float(np.sqrt(np.mean((g["aar_pred"] - y) ** 2)))})
    return out


def validate_forecast(fc: pd.DataFrame) -> list[str]:
    errs = []
    key = ["airport", "asof_utc", "target_hour_utc", "horizon_hours"]
    if fc[key].isna().any().any():
        errs.append("null snapshot keys")
    if fc.duplicated(key).any():
        errs.append("duplicate snapshot keys")
    if ((fc["target_hour_utc"] - fc["asof_utc"]) != pd.to_timedelta(fc["horizon_hours"], unit="h")).any():
        errs.append("target_hour_utc != asof_utc + horizon_hours")
    usable = fc["status"].isin(["available", "partial"])
    for col in ("features_available_at_utc", "model_train_end_utc", "model_selection_end_utc"):
        if fc.loc[usable, col].isna().any():
            errs.append(f"usable rows with null {col}")
        if (fc.loc[usable, col] > fc.loc[usable, "asof_utc"]).any():
            errs.append(f"usable rows with {col} after cutoff")
    if (fc["aar_pred"].dropna() < 0).any():
        errs.append("negative aar_pred")
    if fc["aar_observed"].notna().any():
        errs.append("aar_observed must stay null (no facility label)")
    if (fc["label_kind"] != LABEL_KIND).any():
        errs.append("label_kind must be model_estimated_capacity")
    if (fc["uncertainty_kind"] == "unavailable").any() and fc.loc[fc["uncertainty_kind"] == "unavailable",
                                                                  ["aar_lower", "aar_upper"]].notna().any().any():
        errs.append("bounds must be null when uncertainty is unavailable")
    return errs


def build(frames: dict[str, pd.DataFrame], airports: list[Airport], run_id: str) -> dict:
    snap = build_snapshots(frames["weather_features"], frames["traffic_hourly"], airports)
    model = fit(snap)
    pred = predict(snap, model)
    train_end = _boundary_utc(airports, "2023-12-31")
    select_end = _boundary_utc(airports, "2024-12-31")
    te = pred[(pred["split"] == "test") & (pred["asof_utc"] >= select_end)].copy()
    feature_ok = te["status"].isin(["available", "partial"]) & te["available_at_utc"].notna()
    status = np.where(te["aar_pred"].isna() | ~feature_ok, "unavailable",
                      np.where((te["backoff_level"] == "regime") & (te["status"] == "available"), "available", "partial"))
    fc = pd.DataFrame({
        "airport": te["airport"], "asof_utc": te["asof_utc"], "target_hour_utc": te["target_hour_utc"],
        "horizon_hours": te["horizon_hours"].astype("int64"),
        "aar_pred": te["aar_pred"].where(status != "unavailable"), "aar_lower": np.nan, "aar_upper": np.nan,
        "status": status,
        "source": "Training-only high-demand weather-regime frontier on reporting-carrier arrivals (capacity proxy)",
        "source_id": "bts_ontime_prezip+" + te["source_id"].fillna("none").astype(str), "label_kind": LABEL_KIND,
        "features_available_at_utc": te["available_at_utc"], "model_train_end_utc": train_end,
        "model_selection_end_utc": select_end, "run_id": run_id, "model_version": MODEL_VERSION,
        "coverage": "held_out_replay_2025-01..07_reporting_carriers", "aar_observed": np.nan,
        "population": POPULATION, "estimation_method": METHOD, "assumptions_id": ASSUMPTIONS_ID,
        "validation_target": VALIDATION_TARGET, "uncertainty_kind": "unavailable",
        "support_n": te["support_n"], "weather_regime": te["weather_regime"],
        "frontier_cell": te["frontier_cell"], "backoff_level": te["backoff_level"],
    })
    for c, t in FORECAST_COLUMNS.items():
        if t.startswith("datetime"):
            fc[c] = pd.to_datetime(fc[c], utc=True).astype("datetime64[ns, UTC]")
        else:
            fc[c] = fc[c].astype(t)
    fc = fc[list(FORECAST_COLUMNS)].sort_values(["airport", "asof_utc", "horizon_hours"]).reset_index(drop=True)
    errs = validate_forecast(fc)
    if errs:
        raise EstimateError("forecast failed validation: " + "; ".join(errs))
    metrics = evaluate(pred, model, "validate") + evaluate(pred[pred.index.isin(te.index)], model, "test")
    return {"forecast": fc, "model": model, "metrics": metrics, "train_end": train_end, "select_end": select_end,
            "cohorts": regime_cohorts(pred, model, "validate") + regime_cohorts(pred[pred.index.isin(te.index)], model, "test"),
            "status_counts": fc["status"].value_counts().to_dict(),
            "backoff_counts": fc["backoff_level"].value_counts().to_dict()}


def _envelope(run_id: str, status: str, **body) -> dict:
    return {"schema_version": SCHEMA_VERSION, "run_id": run_id, "generated_at_utc": utcnow(), "producer": PRODUCER,
            "status": status, "limitations": list(LIMITATIONS), "missing_inputs": [], **body}


def publish(out_dir: Path = OUT_DIR, root: Path = REPO_ROOT, airports_codes=("KATL", "KDFW"), log=print) -> dict:
    airports = resolve_airports(list(airports_codes))
    run_id = new_run_id().replace("m1-", "m1-capest-")
    frames, sources = load_published_inputs(root)
    res = build(frames, airports, run_id)
    fc = res["forecast"]
    status = "partial"  # a proxy, never a complete capability
    assumptions = _envelope(run_id, status, assumptions_id=ASSUMPTIONS_ID, population=POPULATION,
                            demand_screen={"rule": "scheduled arrivals >= airport 2023 percentile", "percentile": DEMAND_PERCENTILE,
                                           "deduplication": "one row per (airport, target hour) before thresholds"},
                            method={"name": METHOD, "frontier_quantile": FRONTIER_QUANTILE, "min_support_hours": MIN_SUPPORT,
                                    "cells": "lead-specific (airport, horizon, regime); leads are never pooled",
                                    "backoff": ["(airport, lead, regime)", "(airport, lead, degraded|vfr)", "(airport, lead, all)"],
                                    "unknown_regime": "all-regime cell, status partial"},
                            weather_regimes={"priority": list(REGIMES), "definitions": {
                                "convective": "thunderstorm_flag == 1", "winter": "frozen_precip_flag == 1",
                                "ifr": "ceiling < 1000 ft or visibility < 3 SM", "wind": "crosswind >= 15 kt or tailwind >= 10 kt",
                                "mvfr": "ceiling < 3000 ft or visibility < 5 SM", "vfr": "otherwise",
                                "unknown": "ceiling or visibility missing"}},
                            runway_assumption="crosswind/tailwind from weather_features, computed against fixed challenge "
                                              "headings ATL 080 / DFW 180",
                            splits={"train": "2023 (fit)", "validate": "2024 (reported only)", "test": "2025-01-01..2025-07-31",
                                    "basis": "airport-local date of target hour"},
                            scaling="none: no division by sample fraction, no whole-airport extrapolation")
    model_doc = _envelope(run_id, status, method=METHOD, model_version=MODEL_VERSION, assumptions_id=ASSUMPTIONS_ID,
                          fitted_on="training split only", **res["model"])
    evaluation = _envelope(run_id, status, label_kind=LABEL_KIND, validation_target=VALIDATION_TARGET, method=METHOD,
                           assumptions_id=ASSUMPTIONS_ID,
                           split={"train_end_utc": res["train_end"], "selection_end_utc": res["select_end"],
                                  "emitted_cutoffs": "asof_utc >= selection_end_utc (held-out replay only)"},
                           metrics=res["metrics"], cohorts=res["cohorts"],
                           row_status_counts={k: int(v) for k, v in res["status_counts"].items()},
                           backoff_counts={k: int(v) for k, v in res["backoff_counts"].items()},
                           baseline="train-only airport high-demand 0.90 quantile (no weather)",
                           interpretation="Metrics compare a frozen proxy with observed high-demand reporting-carrier "
                                          "throughput. They are not facility AAR accuracy.")

    out_dir = Path(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}.", dir=out_dir.parent))
    try:
        write_parquet(tmp / "forecast.parquet", fc)
        write_json(tmp / "evaluation.json", evaluation)
        write_json(tmp / "assumptions.json", assumptions)
        write_json(tmp / "model.json", model_doc)
        names = ["forecast.parquet", "evaluation.json", "assumptions.json", "model.json"]
        manifest = _envelope(run_id, status, label_kind=LABEL_KIND, estimation_method=METHOD,
                             scope="KATL/KDFW, horizons 3/6/12, held-out replay 2025-01..07, reporting carriers; capacity proxy, not AAR",
                             capabilities={"capacity_estimate": {
                                 "status": "partial",
                                 "reason": "Model-estimated capacity proxy for reporting carriers, not facility AAR; "
                                           "no uncertainty bounds."}},
                             artifact_hashes={n: sha256_file(tmp / n) for n in names},
                             outputs=[{"path": f"artifacts/capacity_estimate/{n}", "sha256": sha256_file(tmp / n),
                                       "rows": int(len(fc)) if n.endswith(".parquet") else None} for n in names],
                             sources=sources)
        write_json(tmp / "manifest.json", manifest)  # manifest last
        check = pd.read_parquet(tmp / "forecast.parquet")
        if validate_forecast(check) or len(check) != len(fc):
            raise EstimateError("published forecast failed re-validation")
        if out_dir.exists():
            shutil.rmtree(out_dir)
        tmp.rename(out_dir)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    log(f"capacity_estimate {run_id}: {len(fc)} rows {res['status_counts']} backoff {res['backoff_counts']}")
    return {"run_id": run_id, "rows": len(fc), **res}
