"""Evidence-gated hourly arrival queue; this is a planning simulation, not ATC automation."""
from __future__ import annotations

import math
from numbers import Integral
from typing import Any

import pandas as pd


QUEUE_COLUMNS = [
    "airport", "asof_utc", "target_hour_utc", "direction", "demand_count",
    "start_backlog", "served", "end_backlog", "capacity", "aar_pred", "status",
]
ASSUMPTIONS = [
    "Discrete one-hour arrival queue: Q_next = max(0, Q_start + demand - floor(AAR)).",
    "AAR serves arrivals only; departure capacity and joint-runway constraints are not modelled.",
    "Demand is newly due arrivals in each interval; initial backlog is separate and must not be counted again.",
    "Queue order, within-hour timing, aircraft eligibility and individual delay are not modelled.",
    "Backlog area sums end-of-hour backlog; it is not measured delay or an intervention benefit.",
]


def _empty_queue() -> pd.DataFrame:
    dtypes = {
        "airport": "string", "asof_utc": "datetime64[ns, UTC]",
        "target_hour_utc": "datetime64[ns, UTC]", "direction": "string",
        "demand_count": "int64", "start_backlog": "int64", "served": "int64",
        "end_backlog": "int64", "capacity": "int64", "aar_pred": "float64", "status": "string",
    }
    return pd.DataFrame({column: pd.Series(dtype=dtypes[column]) for column in QUEUE_COLUMNS})


def _utc(value: Any, name: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{name}: invalid timestamp") from exc
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError(f"{name}: explicit timezone-aware timestamp required")
    return timestamp.tz_convert("UTC")


def _timestamps(frame: pd.DataFrame, column: str, name: str) -> pd.Series:
    return pd.Series(
        [_utc(value, f"{name}.{column}") for value in frame[column]],
        index=frame.index, dtype="datetime64[ns, UTC]",
    )


def _require_columns(frame: Any, columns: set[str], name: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError(f"{name}: verified input table unavailable")
    missing = columns - set(frame.columns)
    if missing:
        raise ValueError(f"{name}: missing columns {', '.join(sorted(missing))}")
    return frame.copy()


def _scope(frame: pd.DataFrame, airport: str, asof: pd.Timestamp, name: str,
           direction: bool = False) -> pd.DataFrame:
    selected = frame.loc[frame["airport"].astype(str).str.upper().eq(airport)].copy()
    if direction:
        selected = selected.loc[selected["direction"].eq("arrival")].copy()
    if selected.empty:
        raise ValueError(f"{name}: no arrival snapshot for {airport}")
    selected["asof_utc"] = _timestamps(selected, "asof_utc", name)
    selected = selected.loc[selected["asof_utc"].eq(asof)].copy()
    if selected.empty:
        raise ValueError(f"{name}: exact cutoff snapshot unavailable")
    return selected


def _source_values(frame: pd.DataFrame, column: str, name: str) -> list[str]:
    values = frame[column]
    valid = values.map(lambda value: isinstance(value, str) and bool(value.strip())
                       and value.strip().lower() not in {"unknown", "unavailable", "none", "null", "nan", "n/a"})
    if not valid.all():
        raise ValueError(f"{name}.{column}: nonempty provenance required")
    return sorted(set(values.str.strip()))


def _nonnegative(frame: pd.DataFrame, column: str, name: str,
                 integer: bool = False) -> pd.Series:
    if frame[column].map(lambda value: isinstance(value, bool)).any():
        raise ValueError(f"{name}.{column}: boolean values are not counts/rates")
    values = pd.to_numeric(frame[column], errors="coerce")
    if not values.map(lambda value: pd.notna(value) and math.isfinite(float(value)) and value >= 0).all():
        raise ValueError(f"{name}.{column}: finite nonnegative values required")
    if integer and not values.map(lambda value: float(value).is_integer()).all():
        raise ValueError(f"{name}.{column}: integer flight counts required")
    return values.astype("int64" if integer else "float64")


def _hourly_window(frame: pd.DataFrame, hours: pd.DatetimeIndex, name: str) -> pd.DataFrame:
    frame["target_hour_utc"] = _timestamps(frame, "target_hour_utc", name)
    if not frame["target_hour_utc"].eq(frame["target_hour_utc"].dt.floor("h")).all():
        raise ValueError(f"{name}: target hours must be UTC hour boundaries")
    selected = frame.loc[frame["target_hour_utc"].isin(hours)].copy()
    if selected["target_hour_utc"].duplicated().any():
        raise ValueError(f"{name}: duplicate target hours at selected cutoff")
    if set(selected["target_hour_utc"]) != set(hours):
        raise ValueError(f"{name}: every consecutive hour from cutoff through planning window is required")
    return selected.sort_values("target_hour_utc").reset_index(drop=True)


def _known_by_cutoff(frame: pd.DataFrame, column: str, cutoff: pd.Timestamp, name: str) -> None:
    frame[column] = _timestamps(frame, column, name)
    if frame[column].gt(cutoff).any():
        raise ValueError(f"{name}.{column}: information after prediction cutoff is forbidden")


def _validate_horizons(frame: pd.DataFrame, cutoff: pd.Timestamp, name: str) -> None:
    if "horizon_hours" not in frame:
        return
    horizons = _nonnegative(frame, "horizon_hours", name, True)
    expected = (frame["target_hour_utc"] - cutoff).dt.total_seconds() / 3600
    if not horizons.eq(expected).all():
        raise ValueError(f"{name}.horizon_hours: must equal target-hour minus cutoff in hours")


def simulate_arrival_queue(
    demand: pd.DataFrame | None,
    capacity: pd.DataFrame | None,
    initial_backlog: pd.DataFrame | None,
    *, airport: str, asof_utc: Any, window_hours: int,
) -> dict[str, Any]:
    """Simulate a complete hourly arrival window, or return an explicit unavailable result.

    All tables are scoped to exactly the requested airport and cutoff. The queue starts
    at that cutoff; sparse scored horizons (3/6/12) cannot substitute for contiguous
    planning forecasts. Inputs are copied and never mutated. Initial backlog must be
    a verified state *at* the cutoff, rather than an unpropagated older observation.
    """
    result: dict[str, Any] = {
        "schema_version": "2.0", "status": "unavailable",
        "queue": _empty_queue(), "metrics": {}, "metric_units": {},
        "missing_inputs": [], "limitations": list(ASSUMPTIONS), "sources": [],
    }
    for name, frame in [("demand", demand), ("capacity", capacity), ("initial_backlog", initial_backlog)]:
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            result["missing_inputs"].append(f"{name}: verified input table unavailable")
    if result["missing_inputs"]:
        return result
    try:
        if isinstance(window_hours, bool) or not isinstance(window_hours, Integral) or window_hours <= 0:
            raise ValueError("window_hours: positive integer required")
        airport = str(airport).upper().strip()
        if len(airport) != 4 or not airport.isalnum():
            raise ValueError("airport: configured four-character ICAO identifier required")
        cutoff = _utc(asof_utc, "asof_utc")
        if cutoff != cutoff.floor("h"):
            raise ValueError("asof_utc: UTC hour boundary required")
        hours = pd.date_range(cutoff, periods=int(window_hours), freq="h")

        required = {"airport", "asof_utc", "target_hour_utc"}
        demand_rows = _require_columns(demand, required | {
            "direction", "demand_count", "coverage", "population", "available_at_utc", "source_id",
        }, "demand")
        demand_rows = _hourly_window(_scope(demand_rows, airport, cutoff, "demand", True), hours, "demand")
        if not demand_rows["coverage"].eq("complete").all():
            raise ValueError("demand.coverage: complete airport arrival demand required; sample counts cannot size a queue")
        _known_by_cutoff(demand_rows, "available_at_utc", cutoff, "demand")
        _validate_horizons(demand_rows, cutoff, "demand")
        demand_rows["demand_count"] = _nonnegative(demand_rows, "demand_count", "demand", True)
        sources = _source_values(demand_rows, "source_id", "demand")
        populations = _source_values(demand_rows, "population", "demand")
        if len(populations) != 1:
            raise ValueError("demand.population: one consistent traffic population required throughout the window")

        capacity_rows = _require_columns(capacity, required | {
            "horizon_hours", "aar_pred", "status", "label_kind", "source", "source_id",
            "features_available_at_utc", "model_train_end_utc", "model_selection_end_utc",
        }, "capacity")
        capacity_rows = _hourly_window(_scope(capacity_rows, airport, cutoff, "capacity"), hours, "capacity")
        if not capacity_rows["status"].eq("available").all():
            raise ValueError("capacity.status: available predictions required for every hour")
        if not capacity_rows["label_kind"].eq("facility_aar").all():
            raise ValueError("capacity.label_kind: genuine facility_aar model target required; throughput is not AAR")
        _source_values(capacity_rows, "source", "capacity")
        sources += _source_values(capacity_rows, "source_id", "capacity")
        _known_by_cutoff(capacity_rows, "features_available_at_utc", cutoff, "capacity")
        _known_by_cutoff(capacity_rows, "model_train_end_utc", cutoff, "capacity")
        _known_by_cutoff(capacity_rows, "model_selection_end_utc", cutoff, "capacity")
        capacity_rows["aar_pred"] = _nonnegative(capacity_rows, "aar_pred", "capacity")
        _validate_horizons(capacity_rows, cutoff, "capacity")

        backlog_rows = _require_columns(initial_backlog, {
            "airport", "asof_utc", "direction", "backlog_count", "observed_at_utc",
            "available_at_utc", "source_id", "coverage", "population",
        }, "initial_backlog")
        backlog_rows = _scope(backlog_rows, airport, cutoff, "initial_backlog", True)
        if len(backlog_rows) != 1:
            raise ValueError("initial_backlog: exactly one verified state per arrival cutoff required")
        if not backlog_rows["coverage"].eq("complete").all():
            raise ValueError("initial_backlog.coverage: complete arrival backlog required")
        if _source_values(backlog_rows, "population", "initial_backlog") != populations:
            raise ValueError("initial_backlog.population: must match the demand traffic population")
        _known_by_cutoff(backlog_rows, "available_at_utc", cutoff, "initial_backlog")
        backlog_rows["observed_at_utc"] = _timestamps(backlog_rows, "observed_at_utc", "initial_backlog")
        if not backlog_rows["observed_at_utc"].eq(cutoff).all():
            raise ValueError("initial_backlog.observed_at_utc: state must represent the cutoff; stale backlog cannot be assumed unchanged")
        backlog = int(_nonnegative(backlog_rows, "backlog_count", "initial_backlog", True).iloc[0])
        sources += _source_values(backlog_rows, "source_id", "initial_backlog")
    except (ValueError, TypeError, OverflowError) as exc:
        result["missing_inputs"] = [str(exc)]
        return result

    initial = backlog
    rows = []
    for demand_row, capacity_row in zip(demand_rows.itertuples(index=False), capacity_rows.itertuples(index=False)):
        rate = float(capacity_row.aar_pred)
        slots = math.floor(rate)
        incoming = int(demand_row.demand_count)
        served = min(backlog + incoming, slots)
        end = backlog + incoming - served
        rows.append({
            "airport": airport, "asof_utc": cutoff, "target_hour_utc": demand_row.target_hour_utc,
            "direction": "arrival", "demand_count": incoming, "start_backlog": backlog,
            "served": served, "end_backlog": end, "capacity": slots, "aar_pred": rate,
            "status": "simulated",
        })
        backlog = end
    queue = pd.DataFrame(rows, columns=QUEUE_COLUMNS)
    peak = max(initial, int(queue["end_backlog"].max()))
    if backlog > 0:
        recovery, recovery_status = None, "unresolved_within_window"
    elif peak == 0:
        recovery, recovery_status = None, "not_applicable"
    else:
        # Last positive start backlog identifies the final clearing interval.
        clearing = queue.loc[queue["start_backlog"].gt(0) & queue["end_backlog"].eq(0)]
        recovery = (clearing.iloc[-1]["target_hour_utc"] + pd.Timedelta(hours=1)).isoformat()
        recovery_status = "recovered_within_window"
    result.update({
        "status": "available", "queue": queue, "sources": sorted(set(sources)), "population": populations[0],
        "metrics": {
            "initial_backlog_flights": initial, "total_demand_flights": int(queue["demand_count"].sum()),
            "total_served_flights": int(queue["served"].sum()), "peak_backlog_flights": peak,
            "end_backlog_flights": backlog, "backlog_area_flight_hours": float(queue["end_backlog"].sum()),
            "recovery_at_utc": recovery, "recovery_status": recovery_status,
        },
        "metric_units": {
            "initial_backlog_flights": "flights", "total_demand_flights": "flights",
            "total_served_flights": "flights", "peak_backlog_flights": "flights",
            "end_backlog_flights": "flights", "backlog_area_flight_hours": "flight-hours",
            "recovery_at_utc": "UTC timestamp", "recovery_status": "category",
        },
    })
    return result
