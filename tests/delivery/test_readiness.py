"""Review advice and release gates must not promote unsupported evidence."""
import pandas as pd
import pytest

from tools.delivery.controller_brief import summarize
from tools.delivery.verify_release import release_blockers


@pytest.fixture
def predictions():
    return pd.DataFrame([dict(flight_id="high", airport="KATL", asof_utc=pd.Timestamp("2025-07-12T20:00Z"),
        target_hour_utc=pd.Timestamp("2025-07-12T23:00Z"), horizon_hours=3, run_id="r1", status="available",
        model_train_end_utc=pd.Timestamp("2024-01-01T00:00Z"), selection_end_utc=pd.Timestamp("2025-01-01T00:00Z"),
        weather_available_at_utc=pd.Timestamp("2025-07-12T19:00Z"), model_kind="weather_enhanced",
        probability_severe_delay=0.6, threshold=0.15, dep_delay_min=999)])


def brief(rows, asof="2025-07-12T20:00Z"):
    return summarize(rows, "KATL", asof, 3, "r1")


def test_review_uses_exact_snapshot_without_outcomes(predictions):
    result = brief(predictions)
    assert result["flagged_flights"] == 1
    assert "dep_delay_min" not in str(result)
    predictions["dep_delay_min"] = -999
    assert brief(predictions) == result
    assert brief(predictions, "2025-07-12T19:00Z")["status"] == "unavailable"


def test_no_alerts_never_means_all_clear(predictions):
    predictions["probability_severe_delay"] = 0.1
    result = brief(predictions)
    assert result["review_priorities"] == []
    assert "not an airport all-clear" in result["summary"]


@pytest.mark.parametrize("column,value", [
    ("selection_end_utc", pd.Timestamp("2025-07-13T00:00Z")),
    ("weather_available_at_utc", pd.NaT),
    ("model_train_end_utc", pd.Timestamp("2025-07-12T19:00")),
    ("target_hour_utc", pd.Timestamp("2025-07-13T00:00Z")),
    ("run_id", "another"), ("probability_severe_delay", float("nan")),
    ("threshold", 2.0), ("model_kind", "unknown"), ("status", "unavailable")])
def test_bad_review_evidence_is_rejected(predictions, column, value):
    predictions[column] = value
    with pytest.raises(ValueError):
        brief(predictions)


def test_naive_cutoff_and_duplicate_flights_rejected(predictions):
    with pytest.raises(ValueError, match="timezone"):
        brief(predictions, "2025-07-12T20:00")
    with pytest.raises(ValueError, match="Duplicate"):
        brief(pd.concat([predictions, predictions]))


def test_fallback_uses_its_own_threshold(predictions):
    predictions["model_kind"] = "schedule_only"
    predictions["weather_available_at_utc"] = pd.NaT
    predictions["threshold"] = 0.7
    assert brief(predictions)["flagged_flights"] == 0


def publication():
    return {"manifest": "artifacts/capacity_estimate/manifest.json", "status": "partial",
            "payloads": ["artifacts/capacity_estimate/" + n for n in
                         ("forecast.parquet", "evaluation.json", "assumptions.json", "model.json")]}


def test_combined_release_needs_estimate_but_baseline_does_not():
    checks = [{"name": "app_smoke", "exit_code": 0}]
    assert release_blockers(checks, [], False)
    assert release_blockers(checks, [], False, baseline=True) == []
    assert release_blockers(checks, [publication()], False) == []
    missing = publication()
    missing["payloads"].pop()
    assert release_blockers(checks, [missing], False)


@pytest.mark.parametrize("baseline", [False, True])
def test_neither_mode_waives_failures_or_changed_inputs(baseline):
    assert release_blockers([{"name": "full_suite", "exit_code": 1}], [publication()], False, baseline)
    assert release_blockers([{"name": "full_suite", "exit_code": 0}], [publication()], True, baseline)
