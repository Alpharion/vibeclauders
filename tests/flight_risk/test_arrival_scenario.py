from pathlib import Path

import pandas as pd

from src.flight_risk.arrival_scenario import build_scenario
from src.flight_risk.simulation import simulate_arrival_queue


ROOT = Path(__file__).resolve().parents[2]
CUTOFF = pd.Timestamp("2025-07-12T20:00:00Z")


def inputs():
    return (pd.read_parquet(ROOT / "artifacts/capacity/traffic_hourly.parquet"),
            pd.read_parquet(ROOT / "artifacts/capacity_estimate/forecast.parquet"))


def run(traffic, forecast):
    return build_scenario(traffic, forecast, airport="KATL", asof_utc=CUTOFF,
                          window_hours=6, anchor_lead=3)


def test_real_scenario_conserves_counts_and_keeps_assumptions_visible():
    result = run(*inputs())
    assert result["status"] == "scenario"
    assert result["scenario_only"] and not result["operationally_eligible"]
    q = result["queue"]
    assert (q.start_backlog + q.demand_count - q.served == q.end_backlog).all()
    assert (q.served <= q.capacity).all()
    assert q.end_backlog.ge(0).all()
    assert q.start_backlog.iloc[1:].tolist() == q.end_backlog.iloc[:-1].tolist()
    assert any("zero" in s for s in result["limitations"])
    assert any("constant" in s for s in result["limitations"])


def test_future_outcomes_do_not_change_scenario():
    traffic, forecast = inputs()
    before = run(traffic, forecast)
    traffic.loc[traffic.hour_utc >= CUTOFF, "actual_count"] = 999999
    after = run(traffic, forecast)
    pd.testing.assert_frame_equal(before["queue"], after["queue"])
    assert before["metrics"] == after["metrics"]


def test_missing_hour_withholds_scenario_and_operational_queue_stays_gated():
    traffic, forecast = inputs()
    traffic = traffic[~((traffic.airport == "KATL") & (traffic.hour_utc == CUTOFF))]
    assert run(traffic, forecast)["status"] == "unavailable"
    assert simulate_arrival_queue(None, forecast, None, airport="KATL", asof_utc=CUTOFF,
                                  window_hours=6)["status"] == "unavailable"
