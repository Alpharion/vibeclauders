"""Bounded cutoff-feature experiment; never overwrites production publications.

The default compares original-sample cutoff features. --full-bts-manifest runs
a verified full-BTS training comparison against the same original-sample cohort.
"""
from __future__ import annotations

import argparse
import gc
from datetime import date
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .__main__ import verified_bytes
from .data import prepare_canonical, expand_horizons, join_weather, WEATHER_FEATURES
from .metrics import classification_metrics
from .model import CATEGORICAL_FEATURES, SCHEDULE_NUMERIC_FEATURES, choose_threshold
from src.shared import AIRPORTS

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = {
    "declared_before_scoring": True,
    "candidate": "sample_cutoff_history_and_full_reporting_carrier_scheduled_counts_v1",
    "full_bts_training": "not_run: monthly raw caches are absent on this machine",
    "train": "original flight-local dates in 2023; both fixed HGB models",
    "threshold_fit": "2024-01-01 through 2024-08-31, global F1-maximizing threshold per model",
    "selection": "2024-09-01 through 2024-12-31, original sample, same weather-available cohort",
    "adoption": {"macro_ap_relative_gain_min": .01, "macro_brier_relative_regression_max": .02,
                 "per_cell_ap_relative_regression_max": .05, "required_cells": 6},
    "parameters": {"max_iter": 100, "max_depth": 3, "max_leaf_nodes": 8, "learning_rate": .08,
                   "l2_regularization": 2., "min_samples_leaf": 25, "early_stopping": False, "random_state": 27},
    "limits": ["The original sample and late-2024 validation were inspected previously; this is not pristine external validation.",
               "Recent completed departures are only the challenge sample, not complete airport state.",
               "Historical observation receipt latency and schedule revision availability are unverified replay assumptions.",
               "Full-BTS expansion, inbound-tail state, destination weather and calibration are not evaluated here.",
               "No capacity ratio: the published capacity estimate cannot be used as a 2023/2024 known-at-cutoff feature.",
               "A passing experiment is not automatic production adoption; publication and consumer integration require separate review."],
}


def estimator(extra=()):
    numeric = SCHEDULE_NUMERIC_FEATURES + ["horizon_hours"] + WEATHER_FEATURES + list(extra)
    preprocess = ColumnTransformer([
        ("numeric", Pipeline([("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
                              ("scale", StandardScaler())]), numeric),
        ("categories", OneHotEncoder(handle_unknown="ignore", max_categories=25, sparse_output=False), CATEGORICAL_FEATURES),
    ], sparse_threshold=0)
    return Pipeline([("preprocess", preprocess), ("classifier", HistGradientBoostingClassifier(**PROTOCOL["parameters"]))]), numeric + CATEGORICAL_FEATURES


def matched_alert_recall(labels, scores, alerts):
    """Expected recall at exactly k alerts, sharing boundary ties pro rata."""
    labels, scores = np.asarray(labels), np.asarray(scores)
    if not len(labels) or labels.sum() == 0:
        return None
    if alerts <= 0:
        return 0.
    alerts = min(int(alerts), len(labels))
    boundary = np.sort(scores)[-alerts]
    above, tied = scores > boundary, scores == boundary
    return float((labels[above].sum() + labels[tied].sum() * (alerts-above.sum())/tied.sum()) / labels.sum())


def knowledge_end(frame, next_local_date):
    """Conservative fit/selection availability: calendar boundary AND last label."""
    calendar = max(pd.Timestamp(next_local_date, tz=c["timezone"]).tz_convert("UTC") for c in AIRPORTS.values())
    latest = (frame.scheduled_dep_utc + pd.to_timedelta(frame.dep_delay_min.clip(lower=0), unit="m")).max()
    return max(calendar, latest) if pd.notna(latest) else calendar


def compare(frame, before, after, thresholds):
    rows = []
    for (airport, lead), g in frame.groupby(["airport", "horizon_hours"]):
        ix = frame.index.get_indexer(g.index)
        b, a = before[ix], after[ix]
        bm, am = classification_metrics(g.severe_delay, b, thresholds[0]), classification_metrics(g.severe_delay, a, thresholds[1])
        alerts = int((b >= thresholds[0]).sum())
        rows.append({"airport": airport, "lead": int(lead), "incumbent": bm, "candidate": am,
                     "shared_alert_budget": alerts,
                     "incumbent_recall_at_budget": matched_alert_recall(g.severe_delay, b, alerts),
                     "candidate_recall_at_budget": matched_alert_recall(g.severe_delay, a, alerts)})
    return rows


def decision(cells):
    expected = {(a, h) for a in ("KATL", "KDFW") for h in (3, 6, 12)}
    if {(c["airport"], c["lead"]) for c in cells} != expected or len(cells) != 6:
        return {"adopt": False, "reason": "all six airport/lead cells required"}
    for c in cells:
        if any(c[m][k] is None or not np.isfinite(c[m][k]) for m in ("incumbent", "candidate") for k in ("pr_auc", "brier")):
            return {"adopt": False, "reason": "finite two-class metrics required"}
    avg = lambda side, key: float(np.mean([c[side][key] for c in cells]))
    if any(c["incumbent"]["pr_auc"] <= 0 for c in cells) or avg("incumbent", "brier") <= 0:
        return {"adopt": False, "reason": "positive baseline denominators required"}
    gain = avg("candidate", "pr_auc") / avg("incumbent", "pr_auc") - 1
    brier = avg("candidate", "brier") / avg("incumbent", "brier") - 1
    worst = max(1-c["candidate"]["pr_auc"]/c["incumbent"]["pr_auc"] for c in cells)
    return {"adopt": bool(gain >= .01 and brier <= .02 and worst <= .05),
            "macro_ap_relative_gain": gain, "macro_brier_relative_regression": brier,
            "worst_cell_ap_relative_regression": worst,
            "macro_ap_incumbent": avg("incumbent", "pr_auc"), "macro_ap_candidate": avg("candidate", "pr_auc"),
            "macro_brier_incumbent": avg("incumbent", "brier"), "macro_brier_candidate": avg("candidate", "brier")}


def run(output=ROOT / "handover/full-bts-model-evidence.json"):
    from .cutoff_features import add_cutoff_features, FEATURE_COLUMNS
    started = time.monotonic()
    # Save the immutable pre-score protocol before touching labels or fitting.
    work = ROOT / "tmp/full-bts-experiment"
    work.mkdir(parents=True, exist_ok=True)
    (work / "protocol.json").write_text(json.dumps(PROTOCOL, indent=2), encoding="utf-8")
    names = {"canonical": ROOT / "data/processed/flights.parquet", "weather": ROOT / "artifacts/capacity/weather_features.parquet",
             "traffic": ROOT / "artifacts/capacity/traffic_hourly.parquet"}
    manifest, blobs = verified_bytes(ROOT / "artifacts/capacity/manifest.json", names.values())
    frames = {k: pd.read_parquet(BytesIO(blobs[p.resolve()])) for k, p in names.items()}
    prepared = prepare_canonical(frames["canonical"])
    joined, audit = join_weather(expand_horizons(prepared.eligible), frames["weather"])
    joined = add_cutoff_features(joined, frames["canonical"], frames["traffic"])
    joined = joined[joined.weather_available].reset_index(drop=True)
    train = joined[joined.split.eq("train")]
    train_end = knowledge_end(train, "2024-01-01")
    early_pool = joined[joined.flight_date.between("2024-01-01", "2024-08-31")]
    early = early_pool[early_pool.asof_utc.ge(train_end)]
    threshold_end = knowledge_end(early, "2024-09-01")
    late_pool = joined[joined.flight_date.between("2024-09-01", "2024-12-31")]
    late = late_pool[late_pool.asof_utc.ge(threshold_end)]
    selection_end = knowledge_end(late, "2025-01-01")
    models, features, thresholds, scored = [], [], [], []
    for extra in ([], list(FEATURE_COLUMNS)):
        model, allowed = estimator(extra)
        model.fit(train[allowed], train.severe_delay)
        threshold = choose_threshold(early.severe_delay, model.predict_proba(early[allowed])[:, 1])
        models.append(model); features.append(allowed); thresholds.append(threshold)
        scored.append(model.predict_proba(late[allowed])[:, 1])
    cells = compare(late, *scored, thresholds)
    locked = decision(cells)
    result = {"protocol": PROTOCOL, "status": "evaluated", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "full_bts_status": "blocked_missing_raw_caches", "training_population": "original_challenge_sample",
              "feature_history_population": "original_challenge_sample", "feature_schedule_population": "BTS_reporting_carriers",
              "publication_changed": False, "decision": locked, "validation": cells, "thresholds": thresholds,
              "train_snapshots": len(train), "threshold_snapshots": len(early), "validation_snapshots": len(late),
              "train_unique_flights": int(train.flight_id.nunique()), "validation_unique_flights": int(late.flight_id.nunique()),
              "temporal_boundaries": {"training_available_at_utc": train_end.isoformat(),
                                      "threshold_available_at_utc": threshold_end.isoformat(),
                                      "selection_available_at_utc": selection_end.isoformat(),
                                      "early_rows_excluded_before_training_available": len(early_pool)-len(early),
                                      "late_rows_excluded_before_threshold_available": len(late_pool)-len(late)},
              "feature_columns": list(FEATURE_COLUMNS), "weather_audit": audit, "flight_audit": prepared.audit,
              "sources": {k: {"path": str(p.relative_to(ROOT)), "sha256": sha256(blobs[p.resolve()]).hexdigest()} for k, p in names.items()},
              "upstream_run_id": manifest["run_id"], "updated_2025_backtest": None,
              "selection_disclosure": "Same fixed HGB family as incumbent, refit on 2023; both thresholds reselected on Jan-Aug2024. This isolates features but is not a comparison to a newly unseen validation period."}
    # Freeze selection before any 2025 scoring. Rejected attempts do not warrant a test lookup.
    (work / "locked-decision.json").write_text(json.dumps(locked, indent=2), encoding="utf-8")
    if locked["adopt"]:
        test = joined[joined.split.eq("test") & joined.asof_utc.ge(selection_end)]
        test_probs = [m.predict_proba(test[f])[:, 1] for m, f in zip(models, features)]
        result["updated_2025_backtest"] = compare(test, *test_probs, thresholds)
        result["test_disclosure"] = "Previously inspected 2025, updated backtest only; not used in adoption decision."
    joblib.dump({"models": models, "features": features, "thresholds": thresholds, "protocol": PROTOCOL}, work / "candidate-models.joblib")
    result["elapsed_seconds"] = round(time.monotonic()-started, 2)
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"decision": locked, "elapsed_seconds": result["elapsed_seconds"], "output": str(output)}), flush=True)
    return result


def run_full(manifest_path, output):
    """Full-BTS fixed-feature candidate; sample primary and full-population secondary."""
    from threadpoolctl import threadpool_limits
    started = time.monotonic()
    manifest_path = Path(manifest_path)
    publication = json.loads(manifest_path.read_text(encoding="utf-8"))
    canonical_path = Path(publication["output"])
    digest = sha256()
    with canonical_path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            digest.update(block)
    if digest.hexdigest() != publication["sha256"] or publication["status"] != "built_experiment_only":
        raise ValueError("Full-BTS canonical publication is not verified")
    expected_months = [str(p) for p in pd.period_range("2023-01", "2025-07", freq="M")]
    if [m["month"] for m in publication["months"]] != expected_months:
        raise ValueError("All 31 canonical months are required")
    work = ROOT / "tmp/full-bts-experiment"
    protocol = {**PROTOCOL, "candidate": "full_bts_existing_weather_features_v1",
                "train": "incumbent: original sample 2023; candidate: full BTS 2023; identical fixed HGB settings",
                "full_bts_training": "2023 full BTS reporting-carrier eligible departures",
                "threshold_fit": "original sample January-August2024; each model's F1 threshold",
                "limits": [s for s in PROTOCOL["limits"] if not s.startswith(("Full-BTS expansion", "Recent completed"))]
                + ["Candidate A evaluates more training data only. Candidate B full-history extra features is deferred unless separately evaluated.",
                   "Full-population secondary metrics use thresholds chosen on the original sample; they are not population-optimal thresholds."]}
    (work / "full-protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    previous = json.loads(output.read_text()) if output.exists() else None
    if previous and previous.get("training_population") != "original_challenge_sample":
        previous = previous.get("sample_fallback_previous_result")
    names = {"canonical": ROOT / "data/processed/flights.parquet", "weather": ROOT / "artifacts/capacity/weather_features.parquet"}
    upstream, blobs = verified_bytes(ROOT / "artifacts/capacity/manifest.json", names.values())
    sample = prepare_canonical(pd.read_parquet(BytesIO(blobs[names["canonical"].resolve()])))
    weather = pd.read_parquet(BytesIO(blobs[names["weather"].resolve()]))
    sample_joined, weather_audit = join_weather(expand_horizons(sample.eligible), weather)
    sample_joined = sample_joined[sample_joined.weather_available].reset_index(drop=True)
    columns = ["flight_id", "origin", "dest", "carrier", "scheduled_dep_utc", "dep_delay_min", "cancelled",
               "flight_date_local", "scheduled_elapsed_min", "distance_miles", "coverage", "source_id"]
    def full_part(lo, hi):
        raw = pd.read_parquet(canonical_path, columns=columns,
            filters=[("origin", "in", ["ATL", "DFW"]), ("flight_date_local", ">=", date.fromisoformat(lo)),
                     ("flight_date_local", "<", date.fromisoformat(hi))])
        prepared = prepare_canonical(raw)
        joined, audit = join_weather(expand_horizons(prepared.eligible), weather)
        return joined[joined.weather_available].reset_index(drop=True), prepared.audit, audit
    full_train, train_audit, train_weather = full_part("2023-01-01", "2024-01-01")
    print(json.dumps({"stage": "full_train_ready", "snapshots": len(full_train), "unique_flights": int(full_train.flight_id.nunique())}), flush=True)
    sample_train = sample_joined[sample_joined.split.eq("train")]
    train_end = max(knowledge_end(full_train, "2024-01-01"), knowledge_end(sample_train, "2024-01-01"))
    early = sample_joined[sample_joined.flight_date.between("2024-01-01", "2024-08-31") & sample_joined.asof_utc.ge(train_end)]
    threshold_end = knowledge_end(early, "2024-09-01")
    late = sample_joined[sample_joined.flight_date.between("2024-09-01", "2024-12-31") & sample_joined.asof_utc.ge(threshold_end)]
    models, allowed, thresholds, probabilities = [], [], [], []
    for label, training in (("incumbent_sample", sample_train), ("candidate_full_bts", full_train)):
        model, feature_names = estimator()
        fit_start = time.monotonic()
        with threadpool_limits(limits=4):
            model.fit(training[feature_names], training.severe_delay)
            thresholds.append(choose_threshold(early.severe_delay, model.predict_proba(early[feature_names])[:, 1]))
            probabilities.append(model.predict_proba(late[feature_names])[:, 1])
        models.append(model); allowed.append(feature_names)
        print(json.dumps({"stage": label+"_fit", "seconds": round(time.monotonic()-fit_start, 2)}), flush=True)
    sample_cells = compare(late, *probabilities, thresholds)
    locked = decision(sample_cells)
    # Selection is locked on the original sample before any secondary or test data.
    (work / "full-locked-decision.json").write_text(json.dumps(locked, indent=2), encoding="utf-8")
    training_rows, training_flights = len(full_train), int(full_train.flight_id.nunique())
    del full_train, training
    gc.collect()
    result = {"protocol": protocol, "status": "evaluated", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "full_bts_status": "evaluated_existing_features", "training_population": "BTS_reporting_carriers",
              "publication_changed": False, "decision": locked, "validation": sample_cells,
              "thresholds": thresholds, "train_snapshots": training_rows, "train_unique_flights": training_flights,
              "validation_snapshots": len(late), "validation_unique_flights": int(late.flight_id.nunique()),
              "train_audit": train_audit, "train_weather_audit": train_weather, "sample_weather_audit": weather_audit,
              "full_bts_manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(), "full_bts_canonical_sha256": digest.hexdigest(),
              "source_months": 31, "sources": {k: {"path": str(p.relative_to(ROOT)), "sha256": sha256(blobs[p.resolve()]).hexdigest()} for k,p in names.items()},
              "upstream_run_id": upstream["run_id"], "full_population_validation": None,
              "updated_2025_backtest": None, "full_population_updated_2025_backtest": None,
              "sample_fallback_previous_result": previous,
              "temporal_boundaries": {"training_available_at_utc": train_end.isoformat(), "threshold_available_at_utc": threshold_end.isoformat()}}
    def persist():
        result["elapsed_seconds"] = round(time.monotonic()-started, 2)
        output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    persist()
    print(json.dumps({"stage": "primary_decision_locked", "decision": locked}), flush=True)
    full_late, _, _ = full_part("2024-09-01", "2025-01-01")
    full_late = full_late[full_late.asof_utc.ge(threshold_end)]
    with threadpool_limits(limits=4):
        full_probs = [m.predict_proba(full_late[f])[:,1] for m,f in zip(models, allowed)]
    result["full_population_validation"] = compare(full_late, *full_probs, thresholds)
    selection_end = max(knowledge_end(full_late, "2025-01-01"), knowledge_end(late, "2025-01-01"))
    result["temporal_boundaries"]["selection_available_at_utc"] = selection_end.isoformat()
    del full_late, full_probs
    gc.collect()
    persist()
    if locked["adopt"]:
        sample_test = sample_joined[sample_joined.split.eq("test") & sample_joined.asof_utc.ge(selection_end)]
        with threadpool_limits(limits=4):
            sample_probs = [m.predict_proba(sample_test[f])[:,1] for m,f in zip(models, allowed)]
        result["updated_2025_backtest"] = compare(sample_test, *sample_probs, thresholds)
        full_test, _, _ = full_part("2025-01-01", "2025-08-01")
        full_test = full_test[full_test.asof_utc.ge(selection_end)]
        with threadpool_limits(limits=4):
            full_probs = [m.predict_proba(full_test[f])[:,1] for m,f in zip(models, allowed)]
        result["full_population_updated_2025_backtest"] = compare(full_test, *full_probs, thresholds)
        result["test_disclosure"] = "Previously inspected 2025, updated backtest only; selection was locked first."
    model_path = work / "full-candidate-models.joblib"
    joblib.dump({"models": models, "features": allowed, "thresholds": thresholds, "protocol": protocol,
                 "canonical_sha256": digest.hexdigest(), "decision": locked}, model_path)
    reloaded = joblib.load(model_path)
    with threadpool_limits(limits=4):
        for original, loaded, columns in zip(models, reloaded["models"], allowed):
            np.testing.assert_array_equal(original.predict_proba(late[columns]), loaded.predict_proba(late[columns]))
    result["model_artifact"] = {"path": str(model_path.relative_to(ROOT)), "sha256": sha256(model_path.read_bytes()).hexdigest(),
                                "reload_predictions_match": True, "prediction_rows_checked_per_model": len(late)}
    persist()
    print(json.dumps({"stage": "complete", "decision": locked, "seconds": result["elapsed_seconds"]}), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "handover/full-bts-model-evidence.json")
    parser.add_argument("--full-bts-manifest", type=Path)
    args = parser.parse_args()
    run_full(args.full_bts_manifest, args.output) if args.full_bts_manifest else run(args.output)

