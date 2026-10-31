import json

import pandas as pd

from src.flight_risk.recommendations import build_recommendations


ASOF = pd.Timestamp("2025-01-01T00:00:00Z")


def verified_tables(count=3, rate=1):
    demand = pd.DataFrame([{
        "airport": "KATL", "asof_utc": ASOF, "target_hour_utc": ASOF,
        "direction": "arrival", "demand_count": count, "coverage": "complete",
        "population": "all_airport_arrivals",
        "available_at_utc": ASOF, "source_id": "test-demand",
    }])
    capacity = pd.DataFrame([{
        "airport": "KATL", "asof_utc": ASOF, "target_hour_utc": ASOF,
        "horizon_hours": 0, "aar_pred": rate, "status": "available", "label_kind": "facility_aar",
        "source": "test capacity model", "source_id": "test-capacity",
        "features_available_at_utc": ASOF, "model_train_end_utc": ASOF - pd.Timedelta(days=1),
        "model_selection_end_utc": ASOF - pd.Timedelta(hours=1),
    }])
    initial = pd.DataFrame([{
        "airport": "KATL", "asof_utc": ASOF, "direction": "arrival", "backlog_count": 0,
        "observed_at_utc": ASOF, "available_at_utc": ASOF,
        "source_id": "test-backlog", "coverage": "complete",
        "population": "all_airport_arrivals",
    }])
    return demand, capacity, initial


def test_advisory_requires_human_review_and_does_not_invent_reschedules_or_benefits():
    result = build_recommendations(*verified_tables(), airport="KATL", asof_utc=ASOF, horizon_hours=1)
    assert result["status"] == "available"
    assert result["rescheduling"]["status"] == "unavailable"
    advisory = result["recommendations"][0]
    assert advisory["action"] == "review arrival metering"
    assert advisory["human_review_required"] is True
    assert advisory["affected_flight_ids"] == []
    assert advisory["revised_times"] == []  # Airborne or unknown-state flights cannot be rescheduled.
    assert advisory["baseline"]["kind"] == "simulation"
    assert advisory["proposed"]["status"] == "unavailable"
    assert advisory["proposed"]["metrics"] is None
    assert not any("delay" in key for key in advisory["baseline"]["metrics"])
    json.dumps(result, allow_nan=False)


def test_missing_demand_suppresses_advisory():
    _, capacity, initial = verified_tables()
    result = build_recommendations(None, capacity, initial, airport="KATL", asof_utc=ASOF, horizon_hours=1)
    assert result["status"] == "unavailable"
    assert result["recommendations"] == []
    assert result["missing_inputs"]


def test_no_deficit_results_in_monitoring_not_forced_metering():
    result = build_recommendations(*verified_tables(count=1, rate=5), airport="KATL", asof_utc=ASOF, horizon_hours=1)
    assert result["status"] == "available"
    assert result["recommendations"][0]["action"] == "monitor arrival demand"


def test_throughput_does_not_trigger_advisory():
    demand, capacity, initial = verified_tables()
    capacity["label_kind"] = "throughput"
    result = build_recommendations(demand, capacity, initial, airport="KATL", asof_utc=ASOF, horizon_hours=1)
    assert result["status"] == "unavailable"
    assert result["recommendations"] == []


def test_invalid_horizon_fails_visibly_instead_of_throwing():
    result = build_recommendations(*verified_tables(), airport="KATL", asof_utc=ASOF, horizon_hours="bad")
    assert result["status"] == "unavailable"
    assert result["horizon_hours"] is None
    json.dumps(result, allow_nan=False)


def test_all_missing_prerequisites_are_reported():
    result = build_recommendations(None, None, None, airport="KATL", asof_utc=ASOF, horizon_hours=3)
    assert len(result["missing_inputs"]) == 3
