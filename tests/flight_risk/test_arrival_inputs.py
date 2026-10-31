import pandas as pd
import pytest

from src.flight_risk.arrival_inputs import build_arrival_inputs


CUTOFF = pd.Timestamp("2025-07-12T20:00:00Z")


def traffic():
    return pd.DataFrame({"airport": "KATL", "hour_utc": pd.date_range(CUTOFF-pd.Timedelta(hours=3), periods=6, freq="h"),
                         "direction": "arrival", "scheduled_count": [5, 5, 5, 8, 0, 7],
                         "actual_count": [3, 8, 1, 999, 999, 999], "coverage": "reporting_carriers",
                         "population": "BTS reporting carriers", "source_id": "bts", "run_id": "run"})


def build(frame, **kwargs):
    return build_arrival_inputs(frame, airport="KATL", asof_utc=CUTOFF, window_hours=3, warmup_hours=3, **kwargs)


def test_explicit_scenario_backlog_and_newly_due_demand():
    result = build(traffic())
    assert result["status"] == "partial"
    assert result["demand"].demand_count.tolist() == [8, 0, 7]
    # 0 -> 2 -> 0 -> 4; early excess service is not banked for future hours.
    assert result["initial_backlog"].backlog_count.iloc[0] == 4
    assert result["initial_backlog"].warmup_initial_backlog_assumption.iloc[0] == 0
    assert result["demand"].coverage.eq("reporting_carriers").all()
    assert result["demand"].available_at_utc.isna().all()
    assert not result["known_at_cutoff_verified"]


def test_future_actuals_cancellations_and_foreign_airport_cannot_change_results():
    before = build(traffic())
    changed = traffic()
    changed.loc[changed.hour_utc >= CUTOFF, "actual_count"] = -999
    changed["cancelled"] = True
    foreign = changed.assign(airport="KDFW", actual_count=-1)
    after = build(pd.concat([changed, foreign]))
    pd.testing.assert_frame_equal(before["demand"], after["demand"])
    pd.testing.assert_frame_equal(before["initial_backlog"], after["initial_backlog"])


@pytest.mark.parametrize("index", [0, 4])
def test_absent_hour_is_not_zero(index):
    assert build(traffic().drop(index))["status"] == "unavailable"


@pytest.mark.parametrize("column,value", [("coverage", "complete"), ("population", "whole airport"),
                                          ("scheduled_count", -1), ("scheduled_count", True),
                                          ("actual_count", None), ("source_id", "")])
def test_reject_invalid_prior_input(column, value):
    frame = traffic().astype({column: object})
    frame.loc[0, column] = value
    assert build(frame)["status"] == "unavailable"


def test_duplicate_hour_rejected_and_source_unchanged():
    frame = traffic()
    saved = frame.copy(deep=True)
    assert build(pd.concat([frame, frame.iloc[[0]]]))["status"] == "unavailable"
    build(frame)
    pd.testing.assert_frame_equal(frame, saved)


@pytest.mark.parametrize("cutoff", ["2025-07-12 20:00:00", "2025-07-12T20:01:00Z"])
def test_cutoff_requires_timezone_and_hour(cutoff):
    assert build_arrival_inputs(traffic(), airport="KATL", asof_utc=cutoff, window_hours=3)["status"] == "unavailable"
