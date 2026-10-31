"""Retrospective reporting-carrier scenario inputs, never verified airport demand.

The source has no historical publication timestamps. Schedule availability and
immediate availability of completed-hour observations are explicit assumptions.
These rows deliberately cannot satisfy the operational queue's verified-input
contract: coverage stays reporting_carriers and availability remains unknown.
"""
from __future__ import annotations

from numbers import Integral

import numpy as np
import pandas as pd


LIMITATIONS = [
    "Retrospective scenario only: schedules are reconstructed after the fact; their availability at cutoff is assumed, not verified.",
    "Only BTS reporting carriers are represented; these are not complete airport arrival inputs.",
    "Scheduled gate arrivals include cancellations; observed counts represent runway arrivals. Their difference is an aggregate imbalance proxy, not identified waiting aircraft.",
    "Backlog starts at an explicitly assumed zero at the warmup boundary; earlier backlog, early arrivals, diversions and cancellations are not reconstructed.",
    "Completed-hour observations are assumed immediately available for this replay; historical publication latency is unknown.",
    "No current/future actual arrivals or post-cutoff cancellation labels are used. No flight rescheduling or operational metering is supported.",
]


def _utc(value):
    t = pd.Timestamp(value)
    if pd.isna(t) or t.tzinfo is None:
        raise ValueError("timestamps must be explicit timezone-aware values")
    return t.tz_convert("UTC")


def _counts(series, name):
    values = pd.to_numeric(series, errors="coerce")
    valid = np.isfinite(values) & (values >= 0) & (values == np.floor(values))
    valid &= ~series.map(lambda v: isinstance(v, (bool, np.bool_)))
    if not valid.fillna(False).all():
        raise ValueError(f"{name}: finite nonnegative integer counts required")
    return values.astype("int64")


def build_arrival_inputs(traffic: pd.DataFrame, *, airport: str, asof_utc,
                         window_hours: int, warmup_hours: int = 24) -> dict:
    """Build consecutive schedule demand and an explicitly assumed backlog proxy.

    Returns status ``partial`` for a usable scenario, or ``unavailable`` with
    reasons. Future actual counts are never accessed. Missing coverage differs
    from an observed zero. No input is mutated and no artifacts are published.
    """
    result = {"status": "unavailable", "demand": pd.DataFrame(),
              "initial_backlog": pd.DataFrame(), "missing_inputs": [],
              "limitations": list(LIMITATIONS), "scenario_only": True,
              "known_at_cutoff_verified": False}
    try:
        for name, value in (("window_hours", window_hours), ("warmup_hours", warmup_hours)):
            if isinstance(value, bool) or not isinstance(value, Integral) or not 1 <= value <= 168:
                raise ValueError(f"{name}: integer from 1 through 168 required")
        if airport not in ("KATL", "KDFW"):
            raise ValueError("airport must be KATL or KDFW")
        cutoff = _utc(asof_utc)
        if cutoff != cutoff.floor("h"):
            raise ValueError("asof_utc must be an hour boundary")
        required = {"airport", "hour_utc", "direction", "scheduled_count", "actual_count",
                    "coverage", "population", "source_id", "run_id"}
        if not isinstance(traffic, pd.DataFrame) or not traffic.columns.is_unique or not required <= set(traffic):
            raise ValueError("traffic requires unique columns and the published hourly traffic schema")
        rows = traffic[(traffic.airport == airport) & (traffic.direction == "arrival")].copy()
        rows["hour_utc"] = pd.to_datetime([_utc(t) for t in rows.hour_utc], utc=True)
        history_hours = pd.date_range(cutoff - pd.Timedelta(hours=warmup_hours), periods=warmup_hours, freq="h")
        demand_hours = pd.date_range(cutoff, periods=window_hours, freq="h")
        expected = history_hours.append(demand_hours)
        rows = rows[rows.hour_utc.isin(expected)].sort_values("hour_utc")
        if rows.hour_utc.duplicated().any():
            raise ValueError("duplicate arrival hours in requested warmup/window")
        if set(rows.hour_utc) != set(expected):
            raise ValueError("every warmup and planning hour must be covered; absent hours are not zero")
        if not rows.coverage.eq("reporting_carriers").all():
            raise ValueError("coverage must remain reporting_carriers")
        for column in ("population", "source_id", "run_id"):
            if not rows[column].map(lambda v: isinstance(v, str) and bool(v.strip())).all():
                raise ValueError(f"{column}: nonempty provenance required")
            if rows[column].nunique() != 1:
                raise ValueError(f"{column}: mixed publications/populations are unsupported")
        if not rows.population.str.contains("reporting carrier", case=False).all():
            raise ValueError("population must identify reporting carriers")
        rows["scheduled_count"] = _counts(rows.scheduled_count, "scheduled_count")
        history = rows[rows.hour_utc < cutoff].copy()
        history["actual_count"] = _counts(history.actual_count, "prior completed-hour actual_count")
        backlog = 0
        for row in history.itertuples(index=False):
            backlog = max(0, backlog + int(row.scheduled_count) - int(row.actual_count))
        shared = {"airport": airport, "asof_utc": cutoff, "direction": "arrival",
                  "coverage": "reporting_carriers", "population": rows.population.iloc[0],
                  "source_id": rows.source_id.iloc[0], "run_id": rows.run_id.iloc[0],
                  "status": "scenario_estimate", "scenario_only": True,
                  "known_at_cutoff_verified": False, "available_at_utc": pd.NaT}
        demand = rows[rows.hour_utc >= cutoff][["hour_utc", "scheduled_count"]].rename(
            columns={"hour_utc": "target_hour_utc", "scheduled_count": "demand_count"})
        for key, value in shared.items():
            demand[key] = value
        demand["horizon_hours"] = ((demand.target_hour_utc - cutoff).dt.total_seconds() / 3600).astype(int)
        demand["demand_kind"] = "reconstructed_schedule_estimate"
        initial = pd.DataFrame([{**shared, "backlog_count": backlog,
                                 "backlog_kind": "aggregate_imbalance_estimate",
                                 "state_at_utc": cutoff, "observed_at_utc": pd.NaT,
                                 "warmup_start_utc": history_hours[0], "warmup_hours": warmup_hours,
                                 "warmup_initial_backlog_assumption": 0,
                                 "latest_observed_hour_end_utc": cutoff}])
        result.update(status="partial", demand=demand.reset_index(drop=True), initial_backlog=initial,
                      warmup_hours=warmup_hours, population=shared["population"])
    except (ValueError, TypeError, OverflowError) as exc:
        result["missing_inputs"] = [str(exc)]
    return result
