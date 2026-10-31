"""Pure view logic: exact-key selection and evidence gates. No Streamlit here."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.dashboard.data import SCORED_HORIZONS, Bundle
from src.shared import AIRPORTS, airport_icao

# Allowlist: a new producer column stays hidden until someone decides it is safe.
UNREVEALED_FLIGHT_COLUMNS = [
    "flight_id", "origin", "dest", "carrier", "flight_number", "scheduled_dep_utc",
    "scheduled_arr_utc", "coverage",
]
OUTCOME_COLUMNS = ["dep_delay_min", "arr_delay_min", "cancelled", "diverted"]


@dataclass(frozen=True)
class Airport:
    icao: str
    iata: str
    heading: int


def resolve_airport(code: str) -> Airport | None:
    """Find a registry airport by ICAO or IATA; None means unsupported, not a default."""
    icao = airport_icao(code)
    info = AIRPORTS.get(icao)
    return Airport(icao, info["iata"], info["heading"]) if info else None


@dataclass(frozen=True)
class Snapshot:
    airport: Airport
    asof_utc: pd.Timestamp
    horizon_hours: int

    @property
    def target_hour_utc(self) -> pd.Timestamp:
        return self.asof_utc + pd.Timedelta(hours=self.horizon_hours)

    def rows(self, table: pd.DataFrame) -> pd.DataFrame:
        return table[
            (table["airport"] == self.airport.icao)
            & (table["asof_utc"] == self.asof_utc)
            & (table["target_hour_utc"] == self.target_hour_utc)
            & (table["horizon_hours"] == self.horizon_hours)
        ]


def utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def replay_index(bundle: Bundle) -> pd.DataFrame:
    """Every cutoff with published output, and which sources cover each exact key."""
    columns = ["airport", "asof_utc", "horizon_hours"]
    frames = []
    for name in ("predictions", "weather_features", "forecast"):
        table = bundle.table(name)
        if table is not None and not table.empty:
            keys = table[table["horizon_hours"].isin(SCORED_HORIZONS)]
            counts = keys.groupby(columns).size().rename(name).reset_index()
            frames.append(counts)
    recommendations = bundle.docs.get("recommendations")
    if recommendations and resolve_airport(str(recommendations.get("airport"))):
        frames.append(
            pd.DataFrame(
                {
                    "airport": resolve_airport(recommendations["airport"]).icao,
                    "asof_utc": utc(recommendations["asof_utc"]),
                    "horizon_hours": list(SCORED_HORIZONS),
                    "decision": 1,
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=[*columns, "predictions"])
    index = frames[0]
    for frame in frames[1:]:
        index = index.merge(frame, how="outer", on=columns)
    if "predictions" not in index:
        index["predictions"] = 0
    return index.fillna({"predictions": 0}).sort_values(columns).reset_index(drop=True)


def risk_rows(bundle: Bundle, snapshot: Snapshot) -> pd.DataFrame | None:
    """Scored flights at the exact key; never a nearby cutoff or another airport."""
    predictions = bundle.table("predictions")
    if predictions is None:
        return None
    rows = snapshot.rows(predictions).sort_values("probability_severe_delay", ascending=False)
    flights = bundle.table("flights")
    if flights is not None and not rows.empty:
        keep = [c for c in UNREVEALED_FLIGHT_COLUMNS if c != "coverage"]
        rows = rows.merge(flights[keep], how="left", on="flight_id")
    return rows


def scored_flights(flights: pd.DataFrame, snapshot: Snapshot) -> pd.DataFrame:
    """Departures in [target, target+1h), the cohort the risk model scores."""
    start = snapshot.target_hour_utc
    departures = flights["scheduled_dep_utc"]
    return flights[
        (flights["origin"] == snapshot.airport.iata)
        & (departures >= start)
        & (departures < start + pd.Timedelta(hours=1))
    ]


def planning_movements(
    flights: pd.DataFrame, airport: Airport, asof_utc: pd.Timestamp, window_hours: int
) -> dict:
    """Cumulative [asof, asof+W) traffic. A separate view from the scored cohort."""
    end = asof_utc + pd.Timedelta(hours=window_hours)
    departures = flights[
        (flights["origin"] == airport.iata)
        & (flights["scheduled_dep_utc"] >= asof_utc)
        & (flights["scheduled_dep_utc"] < end)
    ]
    arrivals = flights[
        (flights["dest"] == airport.iata)
        & (flights["scheduled_arr_utc"] >= asof_utc)
        & (flights["scheduled_arr_utc"] < end)
    ]
    hours = pd.date_range(asof_utc, periods=window_hours, freq="h")
    hourly = pd.DataFrame(
        {
            "hour_utc": hours,
            "arrivals": arrivals["scheduled_arr_utc"].dt.floor("h").value_counts()
            .reindex(hours, fill_value=0).to_numpy(),
            "departures": departures["scheduled_dep_utc"].dt.floor("h").value_counts()
            .reindex(hours, fill_value=0).to_numpy(),
        }
    )
    return {
        "arrivals": len(arrivals),
        "departures": len(departures),
        "movements": len(arrivals) + len(departures),
        "coverage": coverage_label(pd.concat([arrivals, departures])),
        "hourly": hourly,
    }


def coverage_label(rows: pd.DataFrame) -> str:
    """Decided per cohort: one non-complete row makes the whole cohort a sample."""
    if rows.empty or "coverage" not in rows:
        return "unknown"
    return "complete" if (rows["coverage"] == "complete").all() else "sampled"


def mask_outcomes(rows: pd.DataFrame, reveal: bool) -> pd.DataFrame:
    if reveal:
        return rows
    return rows[[c for c in rows.columns if c not in OUTCOME_COLUMNS and "actual" not in c]]


def weather_feature_row(bundle: Bundle, snapshot: Snapshot) -> tuple[pd.Series | None, str | None]:
    features = bundle.table("weather_features")
    if features is None:
        return None, bundle.problem("weather_features")
    rows = snapshot.rows(features)
    if rows.empty:
        return None, "No weather feature row at this exact cutoff, target hour and lead."
    row = rows.iloc[0]
    if row["available_at_utc"] > snapshot.asof_utc:
        return None, "Weather row became available after the cutoff, so replay excludes it."
    return row, None


def bulletins_as_of(weather: pd.DataFrame, snapshot: Snapshot) -> pd.DataFrame:
    """Bulletins known at cutoff and valid at target; later amendments stay out."""
    target = snapshot.target_hour_utc
    rows = weather[
        (weather["airport"] == snapshot.airport.icao)
        & (weather["available_at_utc"] <= snapshot.asof_utc)
        & (weather["valid_from_utc"] <= target)
        & (weather["valid_to_utc"] > target)
    ]
    return rows.sort_values("issued_at_utc", ascending=False)


def aar_row(bundle: Bundle, snapshot: Snapshot) -> tuple[pd.Series | None, str | None]:
    forecast = bundle.table("forecast")
    if forecast is None:
        return None, bundle.problem("forecast")
    rows = snapshot.rows(forecast)
    if rows.empty:
        return None, "No AAR forecast at this exact cutoff, target hour and lead."
    row = rows.iloc[0]
    if row["label_kind"] != "facility_aar":
        return None, f"label_kind {row['label_kind']!r} is not genuine facility AAR."
    for column in ("features_available_at_utc", "model_train_end_utc", "model_selection_end_utc"):
        if pd.isna(row[column]) or row[column] > snapshot.asof_utc:
            return None, f"{column} is later than the cutoff, so this row is not cutoff-safe."
    if pd.isna(row["aar_pred"]):
        return None, "aar_pred is null; capacity is unknown at this key."
    return row, None


def uncertainty(row: pd.Series) -> tuple[float, float] | None:
    """Bounds only when both exist. Missing means unknown, not a zero-width interval."""
    if pd.isna(row["aar_lower"]) or pd.isna(row["aar_upper"]):
        return None
    return float(row["aar_lower"]), float(row["aar_upper"])


def decision_mismatch(
    recommendations: dict | None, airport: Airport, asof_utc: pd.Timestamp, window_hours: int
) -> list[str]:
    """The published file is one snapshot; any other selection must not reuse it."""
    if recommendations is None:
        return ["recommendations.json is not available"]
    reasons = []
    if resolve_airport(str(recommendations.get("airport"))) != airport:
        reasons.append(f"published for {recommendations.get('airport')}, selected {airport.icao}")
    if utc(recommendations["asof_utc"]) != asof_utc:
        reasons.append(f"published for cutoff {recommendations['asof_utc']}")
    if recommendations.get("horizon_hours") != window_hours:
        reasons.append(f"published for a {recommendations.get('horizon_hours')}-hour window")
    return reasons


def queue_problems(
    queue: pd.DataFrame | None, airport: Airport, asof_utc: pd.Timestamp, window_hours: int
) -> list[str]:
    if queue is None:
        return ["queue.parquet is not available"]
    rows = queue[
        (queue["airport"] == airport.icao)
        & (queue["asof_utc"] == asof_utc)
        & (queue["direction"] == "arrival")
    ].sort_values("target_hour_utc")
    if rows.empty:
        return ["queue is empty for this snapshot"]
    expected = pd.date_range(asof_utc, periods=window_hours, freq="h")
    problems = []
    if list(rows["target_hour_utc"]) != list(expected):
        problems.append("hours are not contiguous across the planning window")
        return problems
    if rows[["demand_count", "start_backlog", "served", "end_backlog", "capacity"]].isna().any().any():
        problems.append("queue has null measurements")
        return problems
    if (rows["status"] != "simulated").any():
        problems.append("queue rows are not labelled simulated")
    if (rows["start_backlog"] + rows["demand_count"] - rows["served"] != rows["end_backlog"]).any():
        problems.append("conservation fails: start + demand - served != end")
    if (rows["served"] > rows["capacity"]).any():
        problems.append("served exceeds capacity")
    if (rows["capacity"] != np.floor(rows["aar_pred"])).any():
        problems.append("capacity is not floored AAR")
    numbers = rows[["demand_count", "start_backlog", "served", "end_backlog"]]
    if (numbers < 0).any().any():
        problems.append("queue has negative values")
    if (rows["start_backlog"].iloc[1:].to_numpy() != rows["end_backlog"].iloc[:-1].to_numpy()).any():
        problems.append("backlog does not carry between hours")
    return problems


def queue_rows(queue: pd.DataFrame, airport: Airport, asof_utc: pd.Timestamp) -> pd.DataFrame:
    return queue[(queue["airport"] == airport.icao) & (queue["asof_utc"] == asof_utc)].sort_values(
        "target_hour_utc"
    )


def supported_recommendations(
    recommendations: dict, queue_ok: bool, eligibility_known: bool
) -> tuple[list[dict], list[str]]:
    """Filter producer advice to what the evidence shown here supports."""
    items, withheld = [], []
    for item in recommendations.get("recommendations", []):
        if item.get("human_review_required") is not True:
            withheld.append(f"{item.get('id')}: human review is not marked as required")
        elif not queue_ok:
            withheld.append(f"{item.get('id')}: no valid queue supports it")
        elif item.get("revised_times") and not eligibility_known:
            withheld.append(f"{item.get('id')}: revised times lack verified flight eligibility")
            items.append({**item, "revised_times": [], "affected_flight_ids": []})
        else:
            items.append(item)
    return items, withheld


def history_rollup(metrics: pd.DataFrame, period: str = "W") -> pd.DataFrame:
    """Pool daily cohorts, recomputing rates from counts rather than averaging rates."""
    rows = metrics.copy()
    starts = rows["period_start_utc"].dt.tz_localize(None)
    rows["period"] = starts.dt.to_period(period).dt.start_time
    counts = [
        "scheduled_departures", "cancelled_departures", "unknown_cancellation_departures",
        "missing_delay_labels", "eligible_departures", "severe_departures",
        "total_positive_delay_minutes",
    ]
    pooled = rows.groupby(["airport", "period"], as_index=False)[counts].sum()
    eligible = pooled["eligible_departures"]
    known = pooled["scheduled_departures"] - pooled["unknown_cancellation_departures"]
    scheduled = pooled["scheduled_departures"]
    pooled["severe_delay_rate"] = (pooled["severe_departures"] / eligible).where(eligible > 0)
    pooled["delay_minutes_per_flight"] = (
        pooled["total_positive_delay_minutes"] / eligible
    ).where(eligible > 0)
    pooled["cancellation_rate"] = (pooled["cancelled_departures"] / known).where(known > 0)
    pooled["missing_label_share"] = (pooled["missing_delay_labels"] / scheduled).where(scheduled > 0)
    return pooled


def find_failure_cases(document: dict | None) -> list:
    """Failure examples may sit anywhere in nested evaluation results."""
    found = []

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if "failure" in str(key).lower():
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document or {})
    return found
