import pandas as pd
import pytest

from src.flight_risk.simulation import simulate_arrival_queue


ASOF = pd.Timestamp("2025-01-10T00:00:00Z")


def inputs(demand_counts=(5, 3, 0), capacity_rates=(2.9, 4.0, 4.0), initial=1):
    hours = pd.date_range(ASOF, periods=len(demand_counts), freq="h")
    demand = pd.DataFrame({
        "airport": "KATL", "asof_utc": ASOF, "target_hour_utc": hours,
        "direction": "arrival", "demand_count": demand_counts, "coverage": "complete",
        "population": "all_airport_arrivals",
        "available_at_utc": ASOF, "source_id": "verified-demand-fixture",
    })
    capacity = pd.DataFrame({
        "airport": "KATL", "asof_utc": ASOF, "target_hour_utc": hours,
        "horizon_hours": range(len(hours)), "aar_pred": capacity_rates,
        "status": "available", "label_kind": "facility_aar", "source": "fixture model",
        "source_id": "verified-capacity-fixture", "features_available_at_utc": ASOF,
        "model_train_end_utc": ASOF - pd.Timedelta(days=1),
        "model_selection_end_utc": ASOF - pd.Timedelta(hours=1),
    })
    backlog = pd.DataFrame([{
        "airport": "KATL", "asof_utc": ASOF, "direction": "arrival", "backlog_count": initial,
        "observed_at_utc": ASOF, "available_at_utc": ASOF, "source_id": "verified-backlog-fixture",
        "coverage": "complete",
        "population": "all_airport_arrivals",
    }])
    return demand, capacity, backlog


def run(tables, window_hours=3, asof=ASOF):
    return simulate_arrival_queue(*tables, airport="KATL", asof_utc=asof, window_hours=window_hours)


def test_conservation_floor_and_recovery():
    result = run(inputs())
    assert result["status"] == "available"
    queue = result["queue"]
    assert queue.capacity.tolist() == [2, 4, 4]
    assert queue.end_backlog.tolist() == [4, 3, 0]
    assert (queue.start_backlog + queue.demand_count - queue.served == queue.end_backlog).all()
    assert (queue.served <= queue.capacity).all()
    assert result["metrics"]["total_served_flights"] == 9
    assert result["metrics"]["backlog_area_flight_hours"] == 7
    assert result["metrics"]["recovery_at_utc"] == "2025-01-10T03:00:00+00:00"
    assert result["metrics"]["recovery_status"] == "recovered_within_window"


def test_unresolved_backlog_has_no_invented_recovery_time():
    result = run(inputs(capacity_rates=(0, 0, 0)))
    assert result["metrics"]["end_backlog_flights"] == 9
    assert result["metrics"]["recovery_at_utc"] is None
    assert result["metrics"]["recovery_status"] == "unresolved_within_window"


def test_no_backlog_recovery_not_applicable():
    result = run(inputs(demand_counts=(1, 1, 1), capacity_rates=(5, 5, 5), initial=0))
    assert result["metrics"]["peak_backlog_flights"] == 0
    assert result["metrics"]["recovery_at_utc"] is None
    assert result["metrics"]["recovery_status"] == "not_applicable"


def test_recovery_after_final_episode():
    result = run(inputs((3, 0, 4, 0), (1, 5, 1, 5), 0), window_hours=4)
    assert result["queue"].end_backlog.tolist() == [2, 0, 3, 0]
    assert result["metrics"]["recovery_at_utc"] == "2025-01-10T04:00:00+00:00"


@pytest.mark.parametrize("table,column,value,reason", [
    (0, "coverage", "sample", "complete"),
    (0, "demand_count", -1, "nonnegative"),
    (0, "demand_count", float("nan"), "nonnegative"),
    (0, "demand_count", 1.5, "integer"),
    (0, "source_id", "", "provenance"),
    (0, "source_id", None, "provenance"),
    (0, "population", None, "provenance"),
    (0, "population", "", "provenance"),
    (0, "direction", "departure", "arrival"),
    (0, "available_at_utc", ASOF + pd.Timedelta(seconds=1), "after prediction cutoff"),
    (1, "aar_pred", float("inf"), "nonnegative"),
    (1, "aar_pred", -1, "nonnegative"),
    (1, "status", "unavailable", "available predictions"),
    (1, "label_kind", "actual_throughput", "facility_aar"),
    (1, "source_id", "unknown", "provenance"),
    (1, "source_id", "null", "provenance"),
    (1, "source_id", None, "provenance"),
    (1, "horizon_hours", 12, "target-hour minus cutoff"),
    (1, "features_available_at_utc", ASOF + pd.Timedelta(seconds=1), "after prediction cutoff"),
    (1, "model_train_end_utc", ASOF + pd.Timedelta(days=1), "after prediction cutoff"),
    (1, "model_selection_end_utc", ASOF + pd.Timedelta(days=1), "after prediction cutoff"),
    (2, "backlog_count", float("nan"), "nonnegative"),
    (2, "backlog_count", -1, "nonnegative"),
    (2, "coverage", "sample", "complete"),
    (2, "population", "scheduled_domestic_arrivals", "must match"),
    (2, "population", None, "provenance"),
    (2, "observed_at_utc", ASOF - pd.Timedelta(hours=1), "stale backlog"),
    (2, "available_at_utc", ASOF + pd.Timedelta(seconds=1), "after prediction cutoff"),
])
def test_invalid_evidence_withholds_simulation(table, column, value, reason):
    tables = list(inputs())
    tables[table][column] = value
    result = run(tables)
    assert result["status"] == "unavailable"
    assert result["queue"].empty
    assert result["metrics"] == {}
    assert reason in " ".join(result["missing_inputs"])


@pytest.mark.parametrize("table", [0, 1, 2])
def test_missing_table_withholds_simulation(table):
    tables = list(inputs())
    tables[table] = None
    result = run(tables)
    assert result["status"] == "unavailable"
    assert result["queue"].empty


@pytest.mark.parametrize("table", [0, 1, 2])
def test_duplicate_records_withhold_simulation(table):
    tables = list(inputs())
    tables[table] = pd.concat([tables[table], tables[table].iloc[[0]]], ignore_index=True)
    assert run(tables)["status"] == "unavailable"


@pytest.mark.parametrize("table", [0, 1])
def test_gap_in_hourly_window_withholds_simulation(table):
    tables = list(inputs())
    tables[table] = tables[table].drop(index=1)
    result = run(tables)
    assert result["status"] == "unavailable"
    assert "consecutive hour" in result["missing_inputs"][0]


def test_naive_or_non_hourly_cutoff_rejected():
    assert run(inputs(), asof="2025-01-10 00:00:00")["status"] == "unavailable"
    assert run(inputs(), asof=ASOF + pd.Timedelta(minutes=1))["status"] == "unavailable"


def test_read_only_input_and_exact_snapshot():
    tables = inputs()
    before = [table.copy(deep=True) for table in tables]
    assert run(tables)["status"] == "available"
    for table, original in zip(tables, before):
        pd.testing.assert_frame_equal(table, original)
    assert run(tables, asof=ASOF + pd.Timedelta(hours=1))["status"] == "unavailable"


def test_other_airports_do_not_contaminate_scope():
    tables = list(inputs())
    unrelated = tables[0].copy()
    unrelated["airport"] = "KDFW"
    unrelated["demand_count"] = 100
    tables[0] = pd.concat([tables[0], unrelated], ignore_index=True)
    assert run(tables)["metrics"]["total_demand_flights"] == 8


def test_demand_horizon_when_supplied_must_match_grid():
    tables = list(inputs())
    tables[0]["horizon_hours"] = [0, 1, 2]
    assert run(tables)["status"] == "available"
    tables[0].loc[1, "horizon_hours"] = 12
    result = run(tables)
    assert result["status"] == "unavailable"
    assert "demand.horizon_hours" in result["missing_inputs"][0]


def test_population_cannot_change_mid_window():
    tables = list(inputs())
    tables[0].loc[1, "population"] = "domestic_arrivals"
    result = run(tables)
    assert result["status"] == "unavailable"
    assert "consistent traffic population" in result["missing_inputs"][0]


def test_initial_backlog_clears_at_first_hour_end():
    result = run(inputs((0, 0, 0), (2, 2, 2), 1))
    assert result["metrics"]["recovery_at_utc"] == "2025-01-10T01:00:00+00:00"
    assert result["metrics"]["recovery_status"] == "recovered_within_window"


@pytest.mark.parametrize("table,column", [(0, "population"), (2, "population"), (1, "model_selection_end_utc")])
def test_new_contract_fields_are_required(table, column):
    tables = list(inputs())
    tables[table] = tables[table].drop(columns=column)
    result = run(tables)
    assert result["status"] == "unavailable"
    assert column in result["missing_inputs"][0]


def test_unavailable_queue_preserves_types():
    result = run((None, None, None))
    assert str(result["queue"].asof_utc.dtype) == "datetime64[ns, UTC]"
    assert str(result["queue"].target_hour_utc.dtype) == "datetime64[ns, UTC]"
    assert str(result["queue"].demand_count.dtype) == "int64"
    assert str(result["queue"].aar_pred.dtype) == "float64"
