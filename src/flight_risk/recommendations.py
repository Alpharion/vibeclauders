"""Human-review arrival advisories from verified queue prerequisites."""
from __future__ import annotations

from numbers import Integral
from typing import Any

import pandas as pd

from .simulation import simulate_arrival_queue


def build_recommendations(
    demand: pd.DataFrame | None,
    capacity: pd.DataFrame | None,
    initial_backlog: pd.DataFrame | None,
    *, airport: str, asof_utc: Any, horizon_hours: int,
) -> dict[str, Any]:
    """Build an advisory JSON snapshot over the next ``horizon_hours`` hourly slots.

    No actual flight reschedules are emitted. Flight-level eligibility, known state,
    route constraints and a full allocation model would be necessary to produce them.
    This function does not derive delay minutes from classifier probabilities.
    """
    simulation = simulate_arrival_queue(
        demand, capacity, initial_backlog,
        airport=airport, asof_utc=asof_utc, window_hours=horizon_hours,
    )
    try:
        timestamp = pd.Timestamp(asof_utc)
        cutoff = timestamp.tz_convert("UTC").isoformat() if timestamp.tzinfo else str(asof_utc)
    except (ValueError, TypeError, OverflowError):
        cutoff = str(asof_utc)
    report: dict[str, Any] = {
        "schema_version": "2.0", "status": simulation["status"],
        "asof_utc": cutoff, "airport": str(airport).upper(),
        "horizon_hours": int(horizon_hours) if isinstance(horizon_hours, Integral) and not isinstance(horizon_hours, bool) else None,
        "recommendations": [], "missing_inputs": simulation["missing_inputs"],
        "limitations": simulation["limitations"] + [
            "Advisories require a qualified controller's review; no operational instructions are executed.",
            "Flight rescheduling is withheld: no verified flight-state, eligibility and allocation comparison is supplied.",
            "No total-delay, fuel, diversion or causal benefit improvement is claimed.",
        ],
        "rescheduling": {
            "status": "unavailable",
            "missing_inputs": ["verified flight states and eligibility at cutoff", "complete constrained flight allocation comparison"],
        },
    }
    if simulation["status"] != "available":
        return report
    metrics = simulation["metrics"]
    backlog = metrics["peak_backlog_flights"]
    if backlog == 0:
        action = "monitor arrival demand"
        rationale = "The supplied demand and AAR forecasts produce no end-of-hour arrival backlog in this planning window."
    else:
        action = "review arrival metering"
        recovery = metrics["recovery_at_utc"] or "not achieved within the planning window"
        rationale = (
            f"The discrete arrival queue reaches {backlog} flights, with "
            f"{metrics['end_backlog_flights']} remaining at window end; recovery: {recovery}. "
            "Review eligible inbound traffic and confirm capacity before considering ground metering."
        )
    report["recommendations"] = [{
        "id": f"{str(airport).upper()}:{cutoff}:{horizon_hours}:arrival-review",
        "action": action, "rationale": rationale, "affected_flight_ids": [], "revised_times": [],
        "baseline": {"kind": "simulation", "metrics": metrics, "units": simulation["metric_units"],
                     "assumptions": simulation["limitations"]},
        "proposed": {"status": "unavailable", "metrics": None,
                     "reason": "A review advisory is not a simulated intervention or executable flight allocation."},
        "prerequisites": {"arrival_demand": "complete", "capacity_target": "facility_aar",
                          "initial_backlog": "verified_at_cutoff", "temporal_validation": "passed",
                          "population": simulation["population"]},
        "source": simulation["sources"], "human_review_required": True,
    }]
    return report
