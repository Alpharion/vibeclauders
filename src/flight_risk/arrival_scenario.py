"""Illustrative reporting-carrier queue, isolated from operational recommendations."""
from __future__ import annotations

import math

import pandas as pd

from .arrival_inputs import build_arrival_inputs
from .capacity_scenario import build_constant_capacity_scenario


def build_scenario(traffic, forecast, *, airport, asof_utc, window_hours, anchor_lead):
    """Combine disclosed estimates; never promote them to verified queue inputs."""
    demand = build_arrival_inputs(traffic, airport=airport, asof_utc=asof_utc,
                                  window_hours=window_hours)
    capacity = build_constant_capacity_scenario(forecast, airport=airport,
        asof_utc=asof_utc, window_hours=window_hours, anchor_lead=anchor_lead)
    result = {"status": "unavailable", "scenario_only": True,
              "operationally_eligible": False, "queue": pd.DataFrame(), "metrics": {},
              "missing_inputs": demand["missing_inputs"] + capacity["missing_inputs"],
              "limitations": list(dict.fromkeys(demand["limitations"] + capacity["limitations"]))}
    if result["missing_inputs"] or demand["status"] == "unavailable" or capacity["status"] == "unavailable":
        return result
    rows = demand["demand"].merge(capacity["capacity"][["target_hour_utc", "aar_pred"]],
                                 on="target_hour_utc", validate="one_to_one")
    if len(rows) != window_hours:
        result["missing_inputs"].append("Scenario requires every planning hour in both inputs")
        return result
    initial = int(demand["initial_backlog"].iloc[0].backlog_count)
    backlog, queue = initial, []
    for row in rows.sort_values("target_hour_utc").itertuples(index=False):
        slots = math.floor(row.aar_pred)
        due = int(row.demand_count)
        served = min(backlog + due, slots)
        end = backlog + due - served
        queue.append({"target_hour_utc": row.target_hour_utc, "demand_count": due,
                      "start_backlog": backlog, "served": served, "end_backlog": end,
                      "capacity": slots, "capacity_proxy": float(row.aar_pred),
                      "status": "illustrative_scenario"})
        backlog = end
    result.update(status="scenario", queue=pd.DataFrame(queue),
                  metrics={"initial_backlog_flights": initial, "end_backlog_flights": backlog,
                           "peak_backlog_flights": max([initial] + [q["end_backlog"] for q in queue]),
                           "scheduled_arrivals": sum(q["demand_count"] for q in queue),
                           "constant_capacity_proxy_per_hour": capacity["constant_rate"]},
                  anchor_lead=capacity["anchor_lead"],
                  anchor_target_hour_utc=capacity["anchor_target_hour_utc"],
                  source_runs={"traffic": str(demand["demand"].run_id.iloc[0]),
                               "capacity": str(capacity["capacity"].run_id.iloc[0])})
    result["limitations"].append("Queue counts describe this assumed scenario, not identified aircraft, measured delay, savings, or a tested intervention.")
    return result
