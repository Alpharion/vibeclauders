import numpy as np
import pandas as pd
import pytest

from src.flight_risk.data import expand_horizons, prepare_sample
from src.flight_risk.model import baseline_probabilities, choose_threshold, fit_candidates, fit_historical_baseline
from src.flight_risk.pipeline import build_artifacts, run_pipeline


@pytest.fixture(scope="module")
def tiny_csv(tmp_path_factory):
    records = []
    for year in [2023, 2024, 2025]:
        for i in range(80):
            records.append({"FL_DATE": f"{year}-02-{i % 20 + 1:02}", "ORIGIN": "ATL" if i % 2 else "DFW", "DEST": "LAX", "OP_UNIQUE_CARRIER": "DL", "OP_CARRIER_FL_NUM": i + 1, "CRS_DEP_TIME": 800 + i % 8 * 100, "DEP_DELAY": 65 if i % 5 == 0 else 0, "CANCELLED": 0, "CRS_ELAPSED_TIME": 120, "DISTANCE": 700, "WEATHER_DELAY": 999 if i % 5 == 0 else 0})
    path = tmp_path_factory.mktemp("risk") / "sample.csv"
    pd.DataFrame(records).to_csv(path, index=False)
    return path


def test_allowlist_and_train_only_category_fitting(tiny_csv):
    frame = prepare_sample(pd.read_csv(tiny_csv)).eligible
    train = frame[frame.split == "train"]
    validation = frame[frame.split == "validation"].copy()
    validation["carrier"] = "UNSEEN_CARRIER"
    model = fit_candidates(train, validation)
    assert "dep_delay_min" not in model.features
    assert "severe_delay" not in model.features
    category_encoder = model.estimator.named_steps["preprocess"].named_transformers_["categories"]
    assert "UNSEEN_CARRIER" not in category_encoder.categories_[1]
    before = model.predict(validation)
    validation["dep_delay_min"] = 99999
    validation["severe_delay"] = 1 - validation.severe_delay
    assert np.array_equal(before, model.predict(validation))


def test_pipeline_records_partial_weather_status_and_horizon_truth(tiny_csv):
    result = build_artifacts(tiny_csv)
    assert result.evaluation["status"] == "partial"
    assert result.evaluation["weather_model"]["status"] == "unavailable"
    predictions = result.predictions
    assert set(predictions.horizon_hours) == {3, 6, 12}
    assert predictions.probability_severe_delay.between(0, 1).all()
    assert predictions.groupby("flight_id").probability_severe_delay.nunique().eq(1).all()
    assert predictions.asof_utc.ge(pd.to_datetime(result.evaluation["selection_end_utc"], utc=True)).all()
    assert (predictions.target_hour_utc - predictions.asof_utc).eq(pd.to_timedelta(predictions.horizon_hours, unit="h")).all()
    assert set(predictions.model_kind) == {"schedule_only"}
    assert len(result.evaluation["metrics"]) == 30


def test_test_labels_cannot_change_selection_or_predictions(tiny_csv, tmp_path):
    original = build_artifacts(tiny_csv)
    raw = pd.read_csv(tiny_csv)
    raw.loc[raw.FL_DATE.str.startswith("2025"), "DEP_DELAY"] = 200
    changed = tmp_path / "changed.csv"
    raw.to_csv(changed, index=False)
    altered = build_artifacts(changed)
    assert original.evaluation["model"] == altered.evaluation["model"]
    assert original.evaluation["threshold"] == altered.evaluation["threshold"]
    assert np.array_equal(original.predictions.probability_severe_delay, altered.predictions.probability_severe_delay)


def test_manifest_hashes_and_json_are_publishable(tiny_csv, tmp_path):
    import hashlib
    import json
    output = tmp_path / "artifacts"
    result = run_pipeline(tiny_csv, output)
    manifest = json.loads((output / "manifest.json").read_text())
    for name, digest in manifest["artifact_hashes"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    # Git stores these files with LF; CRLF bytes would fail verification on a fresh clone.
    for name in ["evaluation.json", "manifest.json"]:
        assert b"\r" not in (output / name).read_bytes(), name
    assert result["evaluation"]["run_id"] == manifest["run_id"]
    assert manifest["runtime"]["python"]
    assert manifest["runtime"]["libraries"]["scikit-learn"]
    assert manifest["producer"] == "member-2"
    assert manifest["artifact_row_counts"]["predictions.parquet"] == 240
    assert manifest["capabilities"]["weather_risk"]["status"] == "unavailable"
    assert manifest["missing_inputs"]


def test_threshold_is_probability_and_baseline_has_no_test_dependence(tiny_csv):
    frame = prepare_sample(pd.read_csv(tiny_csv)).eligible
    train = frame[frame.split == "train"]
    baseline = fit_historical_baseline(train)
    probability = baseline_probabilities(baseline, frame)
    assert np.isfinite(probability).all()
    assert ((probability >= 0) & (probability <= 1)).all()
    assert 0 <= choose_threshold([0, 1, 0, 1], [0.1, 0.7, 0.3, 0.8]) <= 1


def test_weather_model_uses_verified_rows_and_falls_back_for_future_inputs(tiny_csv, tmp_path):
    frame = expand_horizons(prepare_sample(pd.read_csv(tiny_csv)).eligible)
    weather = frame[["airport", "asof_utc", "target_hour_utc", "horizon_hours", "severe_delay"]].copy()
    # Synthetic ex-ante features for pipeline testing, never exported as real data.
    weather["crosswind_kt"] = weather.severe_delay * 35.0
    weather = weather.drop(columns="severe_delay").drop_duplicates(["airport", "asof_utc", "target_hour_utc", "horizon_hours"])
    weather["available_at_utc"] = weather.asof_utc - pd.Timedelta(minutes=1)
    weather["source_id"] = "synthetic-test-fixture"
    weather["status"] = "available"
    path = tmp_path / "weather.parquet"
    weather.to_parquet(path, index=False)
    result = build_artifacts(tiny_csv, weather_features_path=path)
    assert result.evaluation["weather_model"]["status"] == "available"
    assert result.evaluation["weather_model"]["selected"]
    assert result.predictions.model_kind.eq("weather_enhanced").all()
    future_test = weather.target_hour_utc.dt.year.eq(2025)
    weather.loc[future_test, "available_at_utc"] = weather.loc[future_test, "asof_utc"] + pd.Timedelta(minutes=1)
    weather.to_parquet(path, index=False)
    fallback = build_artifacts(tiny_csv, weather_features_path=path)
    assert fallback.predictions.model_kind.eq("schedule_only").all()
    assert fallback.evaluation["weather_model"]["audit"]["invalid_timing_or_source_rows"] == int(future_test.sum())
    assert fallback.evaluation["weather_model"]["status"] == "partial"
    assert fallback.evaluation["weather_model"]["held_out_performance_status"] == "unavailable"
    assert fallback.manifest["capabilities"]["weather_risk"]["status"] == "partial"
    assert fallback.manifest["missing_inputs"]


def test_prediction_cutoffs_exclude_model_selection_boundary(tiny_csv, tmp_path):
    raw = pd.read_csv(tiny_csv)
    raw.loc[raw.FL_DATE.str.startswith("2025"), "FL_DATE"] = "2025-01-01"
    path = tmp_path / "new-year.csv"
    raw.to_csv(path, index=False)
    result = build_artifacts(path)
    assert result.evaluation["excluded_test_horizon_rows_before_selection_end"] > 0
    assert result.predictions.asof_utc.ge(pd.Timestamp("2025-01-01T06:00:00Z")).all()
