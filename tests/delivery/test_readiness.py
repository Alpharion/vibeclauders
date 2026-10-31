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

@pytest.mark.parametrize("column", ["flight_id", "run_id", "weather_available_at_utc", "threshold"])
def test_missing_required_evidence_rejected(predictions, column):
    with pytest.raises(ValueError, match="schema"):
        brief(predictions.drop(columns=column))


@pytest.mark.parametrize("identity", [None, "", "  ", float("nan")])
def test_missing_flight_identity_rejected(predictions, identity):
    predictions["flight_id"] = identity
    with pytest.raises(ValueError, match="identity"):
        brief(predictions)


def test_threshold_boundary_and_exact_keys(predictions):
    predictions["probability_severe_delay"] = predictions["threshold"]
    other_airport = predictions.assign(airport="KDFW", flight_id="other-airport")
    other_lead = predictions.assign(horizon_hours=6, flight_id="other-lead")
    other_cutoff = predictions.assign(asof_utc=pd.Timestamp("2025-07-12T19:00Z"), flight_id="other-cutoff")
    result = brief(pd.concat([predictions, other_airport, other_lead, other_cutoff]))
    assert result["sampled_flights_scored"] == 1
    assert [row["flight_id"] for row in result["review_priorities"]] == ["high"]
    assert "meets or exceeds" in result["review_priorities"][0]["reason"]


@pytest.mark.parametrize("column", ["model_train_end_utc", "selection_end_utc", "weather_available_at_utc"])
def test_all_evidence_clocks_must_be_known_at_cutoff(predictions, column):
    predictions[column] = pd.Timestamp("2025-07-12T20:00:01Z")
    with pytest.raises(ValueError, match="future"):
        brief(predictions)


def test_brief_checks_producer_hash_and_status(predictions, monkeypatch):
    from io import BytesIO
    from tools.delivery import controller_brief
    from tools.delivery.package import digest, json_bytes

    buffer = BytesIO()
    predictions.to_parquet(buffer)
    payload = buffer.getvalue()
    manifest = {"run_id": "r1", "status": "partial",
                "artifact_hashes": {"predictions.parquet": digest(payload)}}
    files = {"artifacts/risk/predictions.parquet": payload}

    def collect_fixture(root):
        return {**files, "artifacts/risk/manifest.json": json_bytes(manifest)}, []

    monkeypatch.setattr(controller_brief, "collect", collect_fixture)
    result = controller_brief.create_brief(None, "KATL", "2025-07-12T20:00Z", 3)
    assert result["evidence"]["predictions_sha256"] == digest(payload)
    assert result["evidence"]["manifest_sha256"] == digest(json_bytes(manifest))
    manifest["artifact_hashes"]["predictions.parquet"] = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        controller_brief.create_brief(None, "KATL", "2025-07-12T20:00Z", 3)
    manifest["status"] = "unavailable"
    with pytest.raises(ValueError, match="not usable"):
        controller_brief.create_brief(None, "KATL", "2025-07-12T20:00Z", 3)
