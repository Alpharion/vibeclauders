"""Bounded Candidate B experiment; production publication is opt-in, never mutated here.

Run: python -m src.data_capacity.capacity_calibration --output handover/member-1-calibration-evidence.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import capacity_estimate as ce
from .config import resolve_airports

KEY = ["airport", "target_hour_utc", "horizon_hours"]
CALIBRATION_END = "2024-08-31"
SELECTION_END = "2024-12-31"
MIN_SUPPORT = 100


def eligible(pred, model):
    """Same available, cutoff-safe, high-demand population for both estimators."""
    return (pred.aar_pred.notna() & pred.observed_arrivals.notna()
            & pred.status.isin(["available", "partial"])
            & pred.available_at_utc.notna() & (pred.available_at_utc <= pred.asof_utc)
            & (pred.scheduled_arrivals >= pred.airport.map(model["demand_thresholds"])))


def fit_correction(pred, model):
    date = pd.to_datetime(pred.target_date_local)
    rows = pred[eligible(pred, model) & (date >= "2024-01-01") & (date <= CALIBRATION_END)]
    cells = []
    for airport in sorted(model["demand_thresholds"]):
        for lead in (3, 6, 12):
            g = rows[(rows.airport == airport) & (rows.horizon_hours == lead)].drop_duplicates(KEY)
            n = len(g)
            cells.append({"airport": airport, "horizon_hours": lead, "support_n": n,
                          "offset": float((g.observed_arrivals - g.aar_pred).quantile(.90)) if n >= MIN_SUPPORT else 0.,
                          "backoff": "airport_lead_residual" if n >= MIN_SUPPORT else "identity_insufficient_support"})
    airports = resolve_airports(sorted(model["demand_thresholds"]))
    return {"method": "additive_residual_q0.90_airport_lead_v1", "quantile": .90,
            "min_support": MIN_SUPPORT, "fit_start_local": "2024-01-01",
            "model_fitted_data_end_utc": ce._boundary_utc(airports, CALIBRATION_END).isoformat(),
            "model_selection_end_utc": ce._boundary_utc(airports, SELECTION_END).isoformat(),
            "fit_end_local": CALIBRATION_END, "selection_end_local": SELECTION_END, "cells": cells}


def apply_correction(pred, correction):
    out = pred.copy()
    cells = {(c["airport"], c["horizon_hours"]): c for c in correction["cells"]}
    chosen = [cells.get((a, int(h))) for a, h in zip(out.airport, out.horizon_hours)]
    out["calibration_offset"] = [c["offset"] if c else 0. for c in chosen]
    out["calibration_support_n"] = [c["support_n"] if c else 0 for c in chosen]
    out["calibration_backoff"] = [c["backoff"] if c else "identity_missing_cell" for c in chosen]
    out["aar_pred"] = (out.aar_pred + out.calibration_offset).clip(lower=0)
    return out


def metrics(g, value="aar_pred"):
    y, p = g.observed_arrivals, g[value]
    return {"n": len(g), "n_unique_hours": int(g.target_hour_utc.nunique()),
            "rmse": float(np.sqrt(np.mean((p-y)**2))) if len(g) else None,
            "pinball": ce._pinball(y, p) if len(g) else None,
            "coverage": float((y <= p).mean()) if len(g) else None}


def compare(pred, corrected, model, mask):
    if pred.loc[mask].duplicated(KEY).any():
        raise ValueError("duplicate target-hour/lead rows in evaluation cohort")
    use = mask & eligible(pred, model)
    assert corrected.loc[use, KEY].equals(pred.loc[use, KEY])
    assert corrected.loc[use, "aar_pred"].notna().all()
    rows = []
    for (airport, lead), g in pred[mask].groupby(["airport", "horizon_hours"]):
        ix = g.index[use.loc[g.index]]
        before, after = pred.loc[ix], corrected.loc[ix]
        cohort_keys = before[KEY].sort_values(KEY).to_csv(index=False)
        severe = []
        for regime in ("convective", "winter", "ifr", "wind"):
            ri = before.index[before.weather_regime == regime]
            severe.append({"regime": regime, "before": metrics(pred.loc[ri]), "after": metrics(corrected.loc[ri])})
        rows.append({"airport": airport, "horizon_hours": int(lead), "total_snapshots": len(g),
                     "same_cohort_sha256": hashlib.sha256(cohort_keys.encode()).hexdigest(),
                     "input_status_counts": g.status.value_counts().to_dict(),
                     "unavailable_base_predictions": int(g.aar_pred.isna().sum()),
                     "excluded_snapshots": len(g)-len(ix), "before": metrics(before), "after": metrics(after),
                     "training_airport_baseline": metrics(before, "baseline_frontier"),
                     "incumbent_backoff_counts": before.backoff_level.value_counts().to_dict(),
                     "calibration_backoff_counts": after.calibration_backoff.value_counts().to_dict(),
                     "calibration_support_n": sorted(after.calibration_support_n.unique().tolist()), "severe": severe})
    return rows


def decision(rows):
    supported = len(rows) == 6 and all(r["before"]["n"] > 0 for r in rows)
    if not supported:
        return {"adopt": False, "reason": "incomplete six-cell validation support"}
    bp = np.mean([r["before"]["pinball"] for r in rows])
    ap = np.mean([r["after"]["pinball"] for r in rows])
    br = np.mean([r["before"]["rmse"] for r in rows])
    ar = np.mean([r["after"]["rmse"] for r in rows])
    worst = max(r["after"]["pinball"]/r["before"]["pinball"]-1 for r in rows)
    gain, rmse_change = 1-ap/bp, ar/br-1
    return {"adopt": bool(gain >= .01 and rmse_change <= .02 and worst <= .05),
            "macro_pinball_before": float(bp), "macro_pinball_after": float(ap),
            "macro_rmse_before": float(br), "macro_rmse_after": float(ar),
            "pinball_reduction": float(gain), "rmse_increase": float(rmse_change),
            "worst_cell_pinball_increase": float(worst)}


def run():
    frames, sources = ce.load_published_inputs()
    snap = ce.build_snapshots(frames["weather_features"], frames["traffic_hourly"], resolve_airports(["KATL", "KDFW"]))
    base_model = ce.fit(snap)
    pred = ce.predict(snap, base_model)
    correction = fit_correction(pred, base_model)
    corrected = apply_correction(pred, correction)
    date = pd.to_datetime(pred.target_date_local)
    validation = compare(pred, corrected, base_model, (date >= "2024-09-01") & (date <= SELECTION_END))
    locked = decision(validation)  # No test metrics computed before choice is locked.
    publication = ce.OUT_DIR / "manifest.json"
    evidence = {"experiment": "candidate_b_additive_q90", "sources": sources,
                "incumbent_publication_manifest_sha256": ce.sha256_file(publication),
                "incumbent_publication_run_id": json.loads(publication.read_text(encoding="utf-8"))["run_id"],
                "protocol": {"base_fit": "2023", "demand_percentile": .75, "quantile": .90,
                             "calibration": "January-August 2024", "selection": "September-December 2024",
                             "rule": ">=1% macro pinball reduction; <=2% macro RMSE increase; <=5% each-cell pinball increase",
                             "support_rule": "100 distinct eligible calibration hours per airport/lead; otherwise zero offset",
                             "cohort": "available/partial cutoff-safe weather, observed target and 2023-derived high-demand screen",
                             "test_policy": "Only after locked choice; previously inspected 2025 is not pristine external validation"},
                "base_model": base_model, "correction": correction, "validation": validation, "decision": locked}
    if locked["adopt"]:
        # One post-selection backtest; emitted predictions must be after late-2024 selection.
        select_end = ce._boundary_utc(resolve_airports(["KATL", "KDFW"]), SELECTION_END)
        evidence["updated_2025_backtest"] = compare(pred, corrected, base_model,
                                                  (pred.split == "test") & (pred.asof_utc >= select_end))
    else:
        evidence["updated_2025_backtest"] = "Not run: validation rejected candidate; incumbent publication retained."
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = run()
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(evidence["decision"], indent=2))


if __name__ == "__main__":
    main()
