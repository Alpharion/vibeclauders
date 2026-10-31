"""Build and publish auditable Member 2 model artifacts."""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from src.shared import AIRPORTS
from .data import HORIZONS, WEATHER_FEATURES, expand_horizons, join_weather, load_flights
from .evaluation import _logit, calibration_experiment, retrospective_evaluation
from .metrics import classification_metrics, normalized_delay_metrics, reliability_bins
from .model import baseline_probabilities, choose_threshold, fit_candidates, fit_historical_baseline

SCHEMA_VERSION = "2.0"
MODEL_VERSION = "member2-risk-v2"
SPLIT = {"train": ["2023-01-01", "2023-12-31"], "validation": ["2024-01-01", "2024-12-31"], "test": ["2025-01-01", "2025-07-31"], "basis": "original airport-local flight date (FL_DATE/flight_date_local); whole dates stay together; any derived original dates disclosed"}


@dataclass
class PipelineArtifacts:
    predictions: pd.DataFrame
    normalized_metrics: pd.DataFrame
    evaluation: dict
    manifest: dict
    model_bundle: dict


def _selection_end(validation, registry):
    calendar_end = max(pd.Timestamp("2025-01-01", tz=config["timezone"]).tz_convert("UTC") for config in registry.values())
    latest_outcome = (validation.scheduled_dep_utc + pd.to_timedelta(validation.dep_delay_min.clip(lower=0), unit="m")).max()
    return max(calendar_end, latest_outcome) if pd.notna(latest_outcome) else calendar_end


def _metric_rows(test, probabilities, thresholds, baseline_probs, baseline_threshold):
    rows, details = [], []
    for airport in sorted(test.airport.unique()):
        for horizon in HORIZONS:
            mask = test.airport.eq(airport) & test.horizon_hours.eq(horizon)
            part = test[mask]
            if part.empty:
                continue
            labels, probs = part.severe_delay.to_numpy(), probabilities[mask]
            # Mixed schedule/weather fallback can have different validation thresholds.
            predicted = (probs >= thresholds[mask]).astype(int)
            summary = classification_metrics(labels, probs, 0.5)
            from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix
            summary["precision"] = float(precision_score(labels, predicted, zero_division=0))
            summary["recall"] = float(recall_score(labels, predicted, zero_division=0))
            summary["f1"] = float(f1_score(labels, predicted, zero_division=0))
            tn, fp, fn, tp = confusion_matrix(labels, predicted, labels=[0, 1]).ravel()
            summary["confusion"] = {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}
            baseline = classification_metrics(labels, baseline_probs[mask], baseline_threshold)
            for metric in ["precision", "recall", "f1", "pr_auc", "brier"]:
                rows.append({"airport": airport, "horizon_hours": horizon, "metric": metric, "value": summary[metric], "baseline_value": baseline[metric], "n": summary["n"], "severe_n": summary["severe_n"], "split": "test"})
            details.append({"airport": airport, "horizon_hours": horizon, "metrics": summary, "baseline": baseline, "reliability": reliability_bins(labels, probs)})
    return rows, details


def _sources(sample_path, canonical_path, weather_features_path, storm_events_path=None):
    paths = [Path(canonical_path)] if canonical_path and Path(canonical_path).exists() else [Path(sample_path)]
    for optional in [weather_features_path, storm_events_path]:
        if optional and Path(optional).exists():
            paths.append(Path(optional))
    records = []
    for path in paths:
        digest = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        records.append({"path": str(path.resolve()), "sha256": digest.hexdigest(), "size_bytes": path.stat().st_size})
    return records


def _runtime():
    return {"python": platform.python_version(), "python_executable": sys.executable, "platform": platform.platform(), "libraries": {name: version(name) for name in ["numpy", "pandas", "scipy", "scikit-learn", "pyarrow", "joblib"]}}


def build_artifacts(sample_path, canonical_path=None, weather_features_path=None, airport_registry=None, storm_events_path=None):
    registry = airport_registry or AIRPORTS
    flights = load_flights(sample_path, canonical_path, registry)
    train = flights.eligible[flights.eligible.split.eq("train")]
    validation = flights.eligible[flights.eligible.split.eq("validation")]
    schedule_model = fit_candidates(train, validation)
    historical_baseline = fit_historical_baseline(train)
    baseline_threshold = choose_threshold(validation.severe_delay, baseline_probabilities(historical_baseline, validation))
    expanded = expand_horizons(flights.eligible)
    selection_end = _selection_end(validation, registry)
    test_candidate = expanded[expanded.split.eq("test")]
    test = test_candidate[test_candidate.asof_utc.ge(selection_end)].copy().reset_index(drop=True)
    if test.empty:
        raise ValueError("No held-out test predictions after model-selection cutoff")
    weather_table = None
    weather_model, weather_report, weather_matched = None, {"status": "unavailable", "reason": "No cutoff-safe engineered weather features supplied"}, []
    limitations = [
        "Flight source coverage is retained; sample predictions are not complete airport demand.",
        "Historical schedules are reconstructed; archived schedule publication/revision timing is not verified.",
        "Training/validation labels are retrospective; historical BTS publication latency is not established.",
        "Uncalibrated model probabilities: no post-hoc calibrator fitted; Brier score and held-out reliability bins quantify calibration.",
        "No delay minutes, fuel savings, capacity or causal intervention benefits are inferred from delay probabilities.",
    ]
    if flights.audit["original_flight_date_derived_rows"]:
        limitations.append("Canonical input omitted original flight_date_local; split dates were derived from scheduled local dates. Original 2400 day attribution cannot be recovered without source dates.")
    if weather_features_path is not None and not Path(weather_features_path).exists():
        weather_report["reason"] = f"Requested weather features path does not exist: {weather_features_path}"
    if weather_features_path is not None and Path(weather_features_path).exists():
        try:
            weather_table = pd.read_parquet(weather_features_path)
            joined, weather_audit = join_weather(expanded, weather_table)
            weather_train = joined[joined.split.eq("train") & joined.weather_available]
            weather_validation = joined[joined.split.eq("validation") & joined.weather_available]
            weather_model_candidate = fit_candidates(weather_train, weather_validation, include_weather=True)
            matched_schedule = classification_metrics(weather_validation.severe_delay, schedule_model.predict(weather_validation), schedule_model.threshold)
            weather_selected = (
                weather_model_candidate.validation["pr_auc"], -weather_model_candidate.validation["brier"]
            ) > (matched_schedule["pr_auc"], -matched_schedule["brier"])
            weather_model = weather_model_candidate if weather_selected else None
            weather_report = {"status": "available", "selected": weather_selected, "audit": weather_audit, "model": weather_model_candidate.name, "validation": weather_model_candidate.validation, "matched_schedule_validation": matched_schedule, "threshold": weather_model_candidate.threshold}
            test = joined[joined.split.eq("test") & joined.asof_utc.ge(selection_end)].copy().reset_index(drop=True)
            for (airport, horizon), part in test[test.weather_available].groupby(["airport", "horizon_hours"]):
                weather_matched.append({"airport": airport, "horizon_hours": int(horizon), "weather_model": classification_metrics(part.severe_delay, weather_model_candidate.predict(part), weather_model_candidate.threshold), "schedule_model": classification_metrics(part.severe_delay, schedule_model.predict(part), schedule_model.threshold), "n": int(len(part))})
            weather_report["test_weather_rows"] = int(test.weather_available.sum())
            weather_report["test_total_rows"] = int(len(test))
            weather_report["test_coverage_fraction"] = float(test.weather_available.mean())
            if not test.weather_available.all():
                weather_report["status"] = "partial"
                weather_report["reason"] = "Weather model fitted, but held-out weather coverage is incomplete; no performance claim for missing snapshots"
            weather_report["held_out_performance_status"] = "available" if test.weather_available.all() else "partial" if test.weather_available.any() else "unavailable"
        except (ValueError, KeyError, OSError) as exc:
            weather_report = {"status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}
    probabilities = schedule_model.predict(test)
    thresholds = np.full(len(test), schedule_model.threshold)
    model_kind = np.full(len(test), "schedule_only", dtype=object)
    if weather_model is not None:
        mask = test.weather_available.to_numpy()
        if mask.any():
            probabilities[mask] = weather_model.predict(test[mask])
            thresholds[mask] = weather_model.threshold
            model_kind[mask] = "weather_enhanced"
    if (model_kind == "schedule_only").any():
        limitations.append("Schedule-only probabilities do not model approaching weather and repeat across horizons; horizon labels identify prediction cutoffs, not measured lead-time sensitivity.")
    # Calibration is decided on validation only, for the model that scores most held-out rows.
    primary, primary_validation, primary_kind = (weather_model, weather_validation, "weather_enhanced") if weather_model is not None else (schedule_model, validation, "schedule_only")
    primary_rows = model_kind == primary_kind
    calibration = calibration_experiment(primary.name, primary_validation.flight_date, primary_validation.severe_delay, primary.predict(primary_validation), test.severe_delay[primary_rows], probabilities[primary_rows])
    calibrator = None
    if calibration["adopted"]:
        calibrator = LogisticRegression(C=1e6).fit(_logit(primary.predict(primary_validation)), primary_validation.severe_delay)
        # Monotonic transform of probability and threshold leaves every alert unchanged.
        probabilities[primary_rows] = calibrator.predict_proba(_logit(probabilities[primary_rows]))[:, 1]
        thresholds[primary_rows] = calibrator.predict_proba(_logit([primary.threshold]))[0, 1]
        limitations[3] = f"{primary_kind} probabilities are Platt-calibrated on 2024 validation data; other rows are uncalibrated. Brier score and held-out reliability bins quantify calibration."
    run_id = uuid4().hex
    generated = datetime.now(timezone.utc).isoformat()
    runtime = _runtime()
    missing_inputs = []
    if weather_report["status"] == "unavailable":
        missing_inputs.append("sufficient_cutoff_safe_weather_features_for_train_validation_test")
    elif weather_report["status"] == "partial":
        missing_inputs.append("cutoff_safe_weather_features_for_missing_held_out_snapshots")
    weather_capability = "available" if (model_kind == "weather_enhanced").all() else "unavailable" if weather_report["status"] == "unavailable" else "partial"
    capabilities = {
        "schedule_risk": {"status": "available", "test_rows": int(len(test))},
        "weather_risk": {"status": weather_capability, "weather_enhanced_prediction_rows": int((model_kind == "weather_enhanced").sum()), "reason": weather_report.get("reason", "Weather candidate selected using validation only" if weather_model is not None else "Weather candidate did not improve matched validation selection metric; schedule model retained")},
        "weather_model_evaluation": {"status": weather_report.get("held_out_performance_status", "unavailable"), "matched_test_cohorts": int(len(weather_matched))},
        "normalized_observed_delays": {"status": "available", "requires_outcome_reveal": True},
    }
    predictions = test[["flight_id", "airport", "asof_utc", "target_hour_utc", "horizon_hours", "scheduled_dep_utc", "coverage", "source_id"]].copy()
    predictions["probability_severe_delay"] = probabilities
    predictions["threshold"] = thresholds
    predictions["model_kind"] = model_kind
    predictions["model_version"] = MODEL_VERSION
    predictions["model_train_end_utc"] = train.scheduled_dep_utc.max()
    predictions["selection_end_utc"] = selection_end
    predictions["run_id"] = run_id
    predictions["status"] = "available"
    predictions["weather_source_id"] = test.weather_source_id if "weather_source_id" in test else None
    predictions["weather_available_at_utc"] = test.weather_available_at_utc if "weather_available_at_utc" in test else pd.Series(pd.NaT, index=predictions.index, dtype="datetime64[ns, UTC]")
    baseline_probs = baseline_probabilities(historical_baseline, test)
    metrics, detail = _metric_rows(test, probabilities, thresholds, baseline_probs, baseline_threshold)
    sources = _sources(sample_path, canonical_path, weather_features_path, storm_events_path)
    # Outcome/storm-based evaluation runs only after every prediction is fixed.
    retrospective = retrospective_evaluation(test, probabilities, thresholds, model_kind, baseline_probs, baseline_threshold, WEATHER_FEATURES, storm_events_path, weather_table)
    capabilities["storm_cohort_evaluation"] = {"status": retrospective["storm_annotation"]["status"], "use": "retrospective evaluation only"}
    evaluation = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "generated_at_utc": generated, "producer": "member-2", "runtime": runtime,
        "status": "available" if (model_kind == "weather_enhanced").all() else "partial",
        "model": schedule_model.name, "model_version": MODEL_VERSION, "split": SPLIT,
        "selection_end_utc": selection_end.isoformat(),
        "selection_rule": "Model: maximum validation average precision, then minimum Brier; threshold: maximum validation F1, ties use higher threshold",
        "pr_auc_definition": "Average precision (non-interpolated PR summary)",
        "calibration_method": ("Platt scaling adopted for " + calibration["model"] + " rows; " if calibration["adopted"] else "No post-hoc calibrator adopted (see calibration_experiment); ") + "held-out Brier and ten fixed reliability bins reported",
        "calibration_experiment": calibration,
        "threshold": schedule_model.threshold, "candidate_validation": schedule_model.candidate_validation,
        "baseline": {"name": "training-only airport/local-hour smoothed severe-delay rate", "threshold": baseline_threshold, "smoothing_prior_count": 20},
        "weather_model": weather_report, "weather_matched_test": weather_matched,
        "metrics": metrics, "detail": detail, "data_audit": flights.audit,
        "prediction_rows": int(len(predictions)), "unique_test_flights": int(predictions.flight_id.nunique()),
        "excluded_test_horizon_rows_before_selection_end": int(len(test_candidate) - len(test)),
        "limitations": limitations, "sources": sources, "missing_inputs": missing_inputs, "capabilities": capabilities,
        **retrospective,
    }
    failed = test[(probabilities >= thresholds).astype(int) != test.severe_delay.to_numpy()].copy()
    evaluation["failure_case"] = None
    if not failed.empty:
        row = failed.iloc[0]
        index = failed.index[0]
        evaluation["failure_case"] = {"flight_id": row.flight_id, "airport": row.airport, "horizon_hours": int(row.horizon_hours), "asof_utc": row.asof_utc.isoformat(), "probability": float(probabilities[index]), "threshold": float(thresholds[index]), "observed_severe_delay": int(row.severe_delay), "observed_dep_delay_min": float(row.dep_delay_min), "requires_outcome_reveal": True, "explanation": "Held-out misclassification; model uses limited schedule patterns and any verified weather available. No causal diagnosis is inferred."}
    normalized = normalized_delay_metrics(flights.all_flights)
    row_counts = {"predictions.parquet": int(len(predictions)), "normalized_metrics.parquet": int(len(normalized)), "evaluation.json": None, "model.joblib": None}
    evaluation["artifact_row_counts"] = row_counts
    manifest = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "generated_at_utc": generated, "status": evaluation["status"],
        "producer": "member-2", "runtime": runtime, "artifact_row_counts": row_counts,
        "model_version": MODEL_VERSION, "sources": sources, "selection_end_utc": selection_end.isoformat(),
        "airports": list(registry), "horizons": list(HORIZONS), "prediction_rows": int(len(predictions)),
        "feature_allowlist": schedule_model.features, "weather_feature_allowlist": weather_model.features if weather_model else [],
        "artifacts": ["model.joblib", "predictions.parquet", "normalized_metrics.parquet", "evaluation.json"],
        "limitations": limitations, "missing_inputs": missing_inputs, "capabilities": capabilities,
    }
    return PipelineArtifacts(predictions, normalized, evaluation, manifest, {"schedule_model": schedule_model, "weather_model": weather_model, "historical_baseline": historical_baseline, "baseline_threshold": baseline_threshold, "calibrator": calibrator, "schema_version": SCHEMA_VERSION, "run_id": run_id, "selection_end_utc": selection_end.isoformat(), "producer": "member-2", "runtime": runtime})


def json_bytes(report):
    """Platform-independent JSON bytes: LF line endings, so published hashes hold on every checkout."""
    return (json.dumps(report, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _atomic(path, writer):
    temporary = path.with_name(path.name + ".tmp")
    writer(temporary)
    temporary.replace(path)


def run_pipeline(sample_path, output_dir, canonical_path=None, weather_features_path=None, airport_registry=None, storm_events_path=None):
    artifacts = build_artifacts(sample_path, canonical_path, weather_features_path, airport_registry, storm_events_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _atomic(output / "predictions.parquet", lambda path: artifacts.predictions.to_parquet(path, index=False))
    _atomic(output / "normalized_metrics.parquet", lambda path: artifacts.normalized_metrics.to_parquet(path, index=False))
    _atomic(output / "model.joblib", lambda path: joblib.dump(artifacts.model_bundle, path))
    _atomic(output / "evaluation.json", lambda path: path.write_bytes(json_bytes(artifacts.evaluation)))
    artifacts.manifest["artifact_hashes"] = {name: sha256((output / name).read_bytes()).hexdigest() for name in artifacts.manifest["artifacts"]}
    artifacts.manifest["artifact_records"] = [{"path": name, "sha256": artifacts.manifest["artifact_hashes"][name], "row_count": artifacts.manifest["artifact_row_counts"][name]} for name in artifacts.manifest["artifacts"]]
    # Manifest last lets readers detect a mixed generation while publishing.
    _atomic(output / "manifest.json", lambda path: path.write_bytes(json_bytes(artifacts.manifest)))
    return {"output_dir": str(output.resolve()), "artifacts": {name: str((output / name).resolve()) for name in artifacts.manifest["artifacts"] + ["manifest.json"]}, "evaluation": artifacts.evaluation, "manifest": artifacts.manifest}
