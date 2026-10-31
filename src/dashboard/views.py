"""Pure view logic: exact-key selection and evidence gates. No Streamlit here."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.dashboard.data import SCORED_HORIZONS, Bundle, is_schedule_only
from src.shared import AIRPORTS, airport_icao

# Allowlist: a new producer column stays hidden until someone decides it is safe.
UNREVEALED_FLIGHT_COLUMNS = [
    "flight_id", "origin", "dest", "carrier", "flight_number", "scheduled_dep_utc",
    "scheduled_arr_utc", "coverage",
]
OUTCOME_COLUMNS = ["dep_delay_min", "arr_delay_min", "cancelled", "diverted"]
# Encodings documented in the capacity manifest's feature_semantics.
VISIBILITY_OVER_6_SM = 6.01
NO_CEILING_FT = 30000


@dataclass(frozen=True)
class Airport:
    icao: str
    iata: str
    heading: int | None


def resolve_airport(code: str) -> Airport | None:
    """Find a registry airport by ICAO or IATA; None means unsupported, not a default."""
    icao = airport_icao(code)
    info = AIRPORTS.get(icao)
    return Airport(icao, info["iata"], info.get("heading")) if info else None


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


def review_priorities(bundle: Bundle, snapshot: Snapshot) -> tuple[dict | None, str | None]:
    """Cutoff-safe human review, independent of operational queue prerequisites.

    Use prediction evidence only: no observed flight outcomes or nearby-key fallback.
    The bundle loader already verified the producer's publication hashes.
    """
    from tools.delivery.controller_brief import summarize

    rows = bundle.table("predictions")
    if rows is None:
        return None, bundle.problem("predictions")
    group = bundle.groups.get("risk")
    manifest = group.manifest if group is not None else None
    if not manifest or manifest.get("status") not in ("available", "partial"):
        return None, "No usable risk publication supports review priorities."
    try:
        brief = summarize(rows, snapshot.airport.icao, snapshot.asof_utc,
                          snapshot.horizon_hours, manifest.get("run_id"))
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        return None, f"Prediction evidence rejected: {error}"
    # The CLI's separate-brief limitation is not applicable to this dashboard view.
    brief["limitations"] = [
        "Historical replay; sampled departures, not complete airport traffic.",
        "Human review priorities only; probabilities are not calibrated guarantees.",
        "No flight times, metering rates or routing instructions are issued.",
    ]
    return brief, None


def scored_flights(flights: pd.DataFrame, snapshot: Snapshot) -> pd.DataFrame:
    """Departures in [target, target+1h), the cohort the risk model scores."""
    start = snapshot.target_hour_utc
    departures = flights["scheduled_dep_utc"]
    return flights[
        (flights["origin"] == snapshot.airport.iata)
        & (departures >= start)
        & (departures < start + pd.Timedelta(hours=1))
    ]


def model_label(model_kind: str) -> str:
    return "Schedule-only" if is_schedule_only(model_kind) else str(model_kind).replace("_", " ").capitalize()


def model_mix(predictions: pd.DataFrame) -> dict[str, int]:
    return predictions["model_kind"].map(model_label).value_counts().to_dict()


def flagged(rows: pd.DataFrame) -> pd.Series:
    """Each row carries its own model's threshold, so compare row by row."""
    return rows["probability_severe_delay"] >= rows["threshold"]


def busiest_cutoffs(index: pd.DataFrame, airport: str, horizon: int, count: int = 5) -> pd.DataFrame:
    rows = index[(index["airport"] == airport) & (index["horizon_hours"] == horizon) & (index["predictions"] > 0)]
    return rows.sort_values(["predictions", "asof_utc"], ascending=[False, True]).head(count)


def scored_counts(index: pd.DataFrame, airport: str, horizon: int) -> pd.Series:
    """Flights scored per cutoff, zero where the exact key has no predictions."""
    rows = index[(index["airport"] == airport) & (index["horizon_hours"] == horizon)]
    return rows.set_index("asof_utc")["predictions"].astype(int)


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


def flagged_routes(rows: pd.DataFrame | None, flights: pd.DataFrame) -> set[tuple[str, str]]:
    """Airport pairs with a departure above threshold in the target hour."""
    if rows is None or rows.empty:
        return set()
    ids = rows.loc[flagged(rows), "flight_id"]
    pairs = flights.loc[flights["flight_id"].isin(ids), ["origin", "dest"]]
    return set(pairs.itertuples(index=False, name=None))


def route_counts(
    flights: pd.DataFrame, airport: Airport, asof_utc: pd.Timestamp, window_hours: int
) -> pd.DataFrame:
    """Airport pairs behind the planning-window movements, counted per direction."""
    end = asof_utc + pd.Timedelta(hours=window_hours)
    outbound = flights[
        (flights["origin"] == airport.iata)
        & (flights["scheduled_dep_utc"] >= asof_utc)
        & (flights["scheduled_dep_utc"] < end)
    ].assign(direction="Departure")
    inbound = flights[
        (flights["dest"] == airport.iata)
        & (flights["scheduled_arr_utc"] >= asof_utc)
        & (flights["scheduled_arr_utc"] < end)
    ].assign(direction="Arrival")
    rows = pd.concat([inbound, outbound])
    return rows.groupby(["origin", "dest", "direction"], as_index=False).size().rename(columns={"size": "flights"})


def coverage_label(rows: pd.DataFrame) -> str:
    """Decided per cohort: one non-complete row makes the whole cohort a sample."""
    if rows.empty or "coverage" not in rows:
        return "unknown"
    return "complete" if (rows["coverage"] == "complete").all() else "sampled"


def mask_outcomes(rows: pd.DataFrame, reveal: bool) -> pd.DataFrame:
    if reveal:
        return rows
    return rows[[c for c in rows.columns if c not in OUTCOME_COLUMNS and "actual" not in c]]


def known_value(value, suffix: str = "", digits: int = 0) -> str:
    return "Unknown" if pd.isna(value) else f"{value:,.{digits}f}{suffix}"


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


def weather_display(name: str, row: pd.Series) -> str:
    """Render a feature for reading, decoding values that are markers rather than measurements."""
    value = row[name]
    if pd.isna(value):
        return "Unknown"
    if name in ("precip_flag", "thunderstorm_flag"):
        return "Forecast" if value == 1 else "Not forecast"
    if name == "visibility_sm" and value == VISIBILITY_OVER_6_SM:
        return "Over 6"
    if name.endswith("ceiling_ft_agl"):
        return "No ceiling" if value == NO_CEILING_FT else f"{value:,.0f} ft"
    if name == "wind_gust_kt" and value == row["wind_speed_kt"]:
        return "No gust"
    return f"{value:.1f}"


def flight_category(visibility_sm, ceiling_ft) -> str:
    """Standard FAA categories. Both inputs are needed; missing means Unknown, not VFR."""
    if pd.isna(visibility_sm) or pd.isna(ceiling_ft):
        return "Unknown"
    if visibility_sm < 1 or ceiling_ft < 500:
        return "LIFR"
    if visibility_sm < 3 or ceiling_ft < 1000:
        return "IFR"
    if visibility_sm <= 5 or ceiling_ft <= 3000:
        return "MVFR"
    return "VFR"


FREQUENCY_MINIMUM_REPORTS = 30
CONDITIONS = ("Thunderstorm", "IFR / LIFR", "Visibility < 3 SM", "Gusts ≥ 25 kt")
CATEGORIES = ("VFR", "MVFR", "IFR", "LIFR")


def observed_history(weather: pd.DataFrame, icao: str, asof_utc: pd.Timestamp, target: pd.Timestamp) -> pd.DataFrame:
    """METARs known by the cutoff from similar conditions: within a month and an hour of the target."""
    rows = weather[
        (weather["airport"] == icao)
        & (weather["kind"] == "observation")
        & (weather["available_at_utc"] <= asof_utc)
    ]
    months = (rows["valid_from_utc"].dt.month - target.month) % 12
    hours = (rows["valid_from_utc"].dt.hour - target.hour) % 24
    return rows[months.isin((0, 1, 11)) & hours.isin((0, 1, 23))]


def condition_frequency(history: pd.DataFrame) -> dict[str, float | None]:
    """Share of past reports meeting each condition; None when too few to be meaningful."""
    if len(history) < FREQUENCY_MINIMUM_REPORTS:
        return dict.fromkeys(CONDITIONS)
    low = (history["visibility_sm"] < 3) | (history["ceiling_ft_agl"] < 1000)
    return {
        "Thunderstorm": float((history["thunderstorm_flag"] == 1).mean()),
        "IFR / LIFR": float(low.mean()),
        "Visibility < 3 SM": float((history["visibility_sm"] < 3).mean()),
        "Gusts ≥ 25 kt": float((history["wind_gust_kt"] >= 25).mean()),
    }


def category_frequency(history: pd.DataFrame) -> dict[str, float] | None:
    if len(history) < FREQUENCY_MINIMUM_REPORTS:
        return None
    labels = [flight_category(v, c) for v, c in zip(history["visibility_sm"], history["ceiling_ft_agl"])]
    shares = pd.Series(labels).value_counts(normalize=True)
    return {category: float(shares.get(category, 0.0)) for category in CATEGORIES}


def radar_time(asof_utc: pd.Timestamp) -> pd.Timestamp:
    """Newest composite safely published by the cutoff, so replay never shows later weather."""
    return (asof_utc - pd.Timedelta(minutes=10)).floor("5min")


def scheduled_at(traffic: pd.DataFrame | None, airport: Airport, hour: pd.Timestamp) -> tuple[float, float]:
    """Scheduled arrivals and departures in one hour; a missing hour stays NaN, not zero."""
    if traffic is None:
        return float("nan"), float("nan")
    rows = traffic[(traffic["airport"] == airport.icao) & (traffic["hour_utc"] == hour)].set_index("direction")
    counts = rows["scheduled_count"].astype(float).to_dict() if len(rows) else {}
    return counts.get("arrival", float("nan")), counts.get("departure", float("nan"))


def actual_at(traffic: pd.DataFrame | None, airport: Airport, hour: pd.Timestamp) -> tuple[float, float]:
    """Actual movements in one hour. Callers show these only after a reveal."""
    if traffic is None:
        return float("nan"), float("nan")
    rows = traffic[(traffic["airport"] == airport.icao) & (traffic["hour_utc"] == hour)].set_index("direction")
    counts = {d: (float("nan") if pd.isna(v) else float(v)) for d, v in rows["actual_count"].items()} if len(rows) else {}
    return counts.get("arrival", float("nan")), counts.get("departure", float("nan"))


def network_nodes(
    flights: pd.DataFrame, rows: pd.DataFrame | None, airport: Airport, asof_utc: pd.Timestamp, window_hours: int
) -> pd.DataFrame:
    """Per connected airport: movements in the window and any scored risk on that route."""
    routes = route_counts(flights, airport, asof_utc, window_hours)
    routes["code"] = routes["dest"].where(routes["origin"] == airport.iata, routes["origin"])
    nodes = routes.pivot_table(index="code", columns="direction", values="flights", aggfunc="sum", fill_value=0)
    nodes = nodes.reindex(columns=["Arrival", "Departure"], fill_value=0).reset_index()
    nodes["max_probability"] = None
    nodes["flagged"] = False
    if rows is not None and not rows.empty:
        scored = rows.merge(flights[["flight_id", "dest"]], how="left", on="flight_id", suffixes=("", "_flight"))
        destination = scored["dest_flight"] if "dest_flight" in scored else scored["dest"]
        scored = scored.assign(code=destination, is_flagged=flagged(scored))
        summary = scored.groupby("code").agg(best=("probability_severe_delay", "max"), any_flag=("is_flagged", "any"))
        nodes["max_probability"] = nodes["code"].map(summary["best"])
        # Empty/all-unmatched Arrow maps can infer null[pyarrow], which cannot
        # accept False. Establish a nullable Boolean dtype before filling.
        nodes["flagged"] = nodes["code"].map(summary["any_flag"]).astype("boolean").fillna(False).astype(bool)
    return nodes


def airport_outlook(bundle: Bundle, icao: str, asof_utc: pd.Timestamp) -> dict[int, pd.Series]:
    """Exact-cutoff weather rows by scored lead; a usable row was available by the cutoff."""
    features = bundle.table("weather_features")
    if features is None:
        return {}
    rows = features[
        (features["airport"] == icao)
        & (features["asof_utc"] == asof_utc)
        & (features["available_at_utc"] <= asof_utc)
    ]
    return {int(row["horizon_hours"]): row for _, row in rows.iterrows() if row["horizon_hours"] in SCORED_HORIZONS}


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


ESTIMATE_TITLE = "Estimated arrival capacity - reporting carriers"


def estimate_row(bundle: Bundle, snapshot: Snapshot) -> tuple[pd.Series | None, str | None]:
    """Model-estimated capacity proxy at the exact key, only if cutoff-safe and usable."""
    table = bundle.table("capacity_estimate")
    if table is None:
        return None, bundle.problem("capacity_estimate")
    rows = snapshot.rows(table)
    if rows.empty:
        return None, "No capacity estimate at this exact cutoff, target hour and lead."
    row = rows.iloc[0]
    if row["label_kind"] != "model_estimated_capacity":
        return None, f"label_kind {row['label_kind']!r} is not a model capacity estimate."
    if row["status"] not in ("available", "partial"):
        return None, "The capacity estimate is unavailable at this key (insufficient training support)."
    for column in ("features_available_at_utc", "model_train_end_utc", "model_selection_end_utc"):
        if pd.isna(row[column]) or row[column] > snapshot.asof_utc:
            return None, f"{column} is later than the cutoff, so this estimate is not cutoff-safe."
    if pd.isna(row["aar_pred"]):
        return None, "Estimate is null at this key."
    return row, None


def capacity_row(bundle: Bundle, snapshot: Snapshot) -> tuple[pd.Series | None, str, str | None]:
    """Genuine facility AAR first; otherwise the proxy at the same exact key.
    Returns (row, kind, reason) with kind 'facility_aar', 'estimate' or 'none'."""
    row, aar_reason = aar_row(bundle, snapshot)
    if row is not None:
        return row, "facility_aar", None
    row, estimate_reason = estimate_row(bundle, snapshot)
    if row is not None:
        return row, "estimate", aar_reason
    return None, "none", f"{aar_reason} Capacity estimate: {estimate_reason}"


def estimate_note(row: pd.Series) -> str:
    support = "unknown" if pd.isna(row.get("support_n")) else f"{int(row['support_n'])} training hours"
    cell = row.get("frontier_cell") or "?"
    backoff = row.get("backoff_level") or "?"
    return (f"Model proxy, not facility AAR · {row['estimation_method']} · cell {cell} "
            f"(backoff: {backoff}, support {support}) · uncertainty {row['uncertainty_kind']}")


def estimate_metrics(document: dict | None, split: str = "test") -> pd.DataFrame:
    """Proxy-target metrics, one row per airport/lead, without any row-level outcomes."""
    metrics = pd.DataFrame((document or {}).get("metrics") or [])
    if metrics.empty:
        return metrics
    metrics = metrics[metrics["split"] == split]
    wide = metrics.pivot_table(index=["airport", "horizon_hours", "n"], columns="metric",
                               values=["value", "baseline_value"], aggfunc="first")
    wide.columns = [f"{m} ({'frontier' if v == 'value' else 'baseline'})" for v, m in wide.columns]
    return wide.reset_index().round(3)


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


def forecast_vs_actual(rows: pd.DataFrame, flights: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Score each flagged decision against its outcome. Cancelled or unlabelled flights are not on time."""
    outcomes = flights[["flight_id", "dep_delay_min", "cancelled"]]
    table = rows.merge(outcomes, how="left", on="flight_id")
    table["alert"] = flagged(table)
    known = table["dep_delay_min"].notna() & (table["cancelled"] == False)  # noqa: E712
    severe = table["dep_delay_min"] > 45
    table["result"] = "Excluded: cancelled or no label"
    table.loc[known & table["alert"] & severe, "result"] = "Matched alert"
    table.loc[known & table["alert"] & ~severe, "result"] = "False alert"
    table.loc[known & ~table["alert"] & severe, "result"] = "Missed event"
    table.loc[known & ~table["alert"] & ~severe, "result"] = "Correctly quiet"
    counts = table["result"].value_counts()
    return table, {
        "alerts": int(table["alert"].sum()),
        "matched": int(counts.get("Matched alert", 0)),
        "false": int(counts.get("False alert", 0)),
        "missed": int(counts.get("Missed event", 0)),
        "excluded": int((~known).sum()),
    }


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


def aar_trend(forecast: pd.DataFrame | None, airport: Airport, horizon: int) -> pd.DataFrame:
    """Held-out hours with a genuine observed AAR; empty until labels are published."""
    if forecast is None or "aar_observed" not in forecast:
        return pd.DataFrame()
    rows = forecast[
        (forecast["airport"] == airport.icao)
        & (forecast["horizon_hours"] == horizon)
        & (forecast["label_kind"] == "facility_aar")
        & forecast["aar_observed"].notna()
    ]
    return rows.sort_values("target_hour_utc")


def storm_table(cohorts: list[dict]) -> pd.DataFrame:
    """One row per cohort, airport and lead, with model and baseline side by side."""
    rows = pd.DataFrame(cohorts)
    key = ["cohort", "airport", "horizon_hours"]
    wide = rows.pivot(index=key, columns="metric", values=["value", "baseline_value"])
    wide.columns = [metric if kind == "value" else f"{metric} (baseline)" for kind, metric in wide.columns]
    wide = wide[sorted(wide.columns)].astype(float)
    context = [c for c in ("n", "severe_n", "reason") if c in rows]
    return rows.groupby(key)[context].first().join(wide).reset_index()


def reliability_rows(document: dict | None, airport: str, horizon: int) -> list[dict]:
    """Held-out reliability bins for one airport and lead, when published."""
    for entry in (document or {}).get("detail") or []:
        if entry.get("airport") == airport and entry.get("horizon_hours") == horizon:
            return [bin_ for bin_ in entry.get("reliability") or [] if bin_.get("n")]
    return []


def calibration_note(document: dict | None) -> str | None:
    experiment = (document or {}).get("calibration_experiment") or {}
    if experiment.get("status") != "available":
        return None
    gain = experiment.get("validation_relative_gain")
    outcome = "Adopted" if experiment.get("adopted") else "Not adopted, so probabilities are uncalibrated"
    return (
        f"Calibration tested on validation data only: {experiment.get('method')}. {outcome} "
        f"({gain:.2%} validation Brier gain). Rule: {experiment.get('decision_rule')}."
    )


def failure_cards(*documents: dict | None) -> list:
    """Distinct failure cases; a case can appear in both the old and new fields."""
    cards, seen = [], set()
    for document in documents:
        for case in find_failure_cases(document):
            key = (case.get("flight_id"), case.get("asof_utc")) if isinstance(case, dict) else repr(case)
            if key not in seen:
                seen.add(key)
                cards.append(case)
    return cards


def integrity_checks(bundle: Bundle, snapshot: Snapshot | None, reveal: bool) -> list[tuple[str, str, str]]:
    """Checks run on what is loaded now, as (label, pass/fail/none, result)."""
    problems = sum(
        1
        for group in bundle.groups.values()
        for name, reasons in group.problems.items()
        if any("rejected" in reason for reason in reasons)
    )
    checks = [("Published artifacts verified", "fail" if problems else "pass", f"{problems} rejected" if problems else "Passed")]
    if snapshot is None or bundle.table("weather_features") is None:
        checks.append(("Forecast inputs available by cutoff", "none", "Not checked"))
    else:
        rows = snapshot.rows(bundle.table("weather_features"))
        if rows.empty:
            checks.append(("Forecast inputs available by cutoff", "none", "No row at this key"))
        else:
            late = int((rows["available_at_utc"] > snapshot.asof_utc).sum())
            checks.append(("Forecast inputs available by cutoff", "fail" if late else "pass", f"{late} late" if late else "Passed"))
    checks.append(("Realised outcomes", "pass", "Revealed by user" if reveal else "Hidden"))
    predictions = bundle.table("predictions")
    if predictions is not None:
        checks.append(("Prediction probabilities and keys", "pass", f"{len(predictions):,} rows valid"))
    return checks


def find_failure_cases(document: dict | None) -> list:
    """Failure examples may sit anywhere in nested evaluation results."""
    found = []

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if "failure" in str(key).lower():
                    found.extend(value if isinstance(value, list) else [value])
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document or {})
    return found


def reporting_series(
    traffic: pd.DataFrame, airport: Airport, direction: str, asof_utc: pd.Timestamp, reveal: bool, before=3, after=8
) -> pd.DataFrame:
    """Hours around the cutoff; a missing hour stays a gap rather than becoming zero."""
    hours = pd.date_range(asof_utc - pd.Timedelta(hours=before), periods=before + after + 1, freq="h")
    rows = traffic[(traffic["airport"] == airport.icao) & (traffic["direction"] == direction)]
    series = rows.set_index("hour_utc").reindex(hours).rename_axis("hour_utc").reset_index()
    return series[["hour_utc", "scheduled_count"] + (["actual_count"] if reveal else [])]


def reporting_traffic(
    traffic: pd.DataFrame, airport: Airport, asof_utc: pd.Timestamp, window_hours: int, reveal: bool
) -> pd.DataFrame:
    """Hourly counts in the window. Missing rows stay missing rather than becoming zero."""
    hours = pd.date_range(asof_utc, periods=window_hours, freq="h")
    rows = traffic[(traffic["airport"] == airport.icao) & traffic["hour_utc"].isin(hours)]
    columns = ["hour_utc", "direction", "scheduled_count"] + (["actual_count"] if reveal else [])
    return rows.sort_values(["hour_utc", "direction"])[columns]
