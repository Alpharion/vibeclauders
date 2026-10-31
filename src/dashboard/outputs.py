"""Forecast, verification and proposal outputs for the revised UI. No Streamlit here.

Each function returns published evidence or says why there is none. Nothing is estimated
here: a missing probability, interval or proposal stays missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.dashboard.data import SCORED_HORIZONS, Bundle
from src.dashboard.views import Airport, Snapshot, weather_feature_row

ALERT_THRESHOLD = 0.5
REVIEW_DELAY = pd.Timedelta(hours=1)
WINDOW = pd.Timedelta(hours=1)
PROBABILITY_CONDITIONS = ("Thunderstorm", "IFR / LIFR", "Visibility < 3 SM", "Gusts ≥ 25 kt")
DEFINITIONS = {
    "Thunderstorm": "TS reported in a METAR",
    "IFR / LIFR": "Visibility under 3 SM or ceiling under 1,000 ft AGL",
    "Visibility < 3 SM": "Prevailing visibility under 3 SM",
    "Gusts ≥ 25 kt": "Reported gust of 25 kt or more",
}
RESULT_TONE = {
    "Matched alert": "green", "False alert": "red", "Missed event": "amber",
    "Correctly quiet": "secondary", "No observation": "secondary", "Pending": "secondary",
}


# --- Weather probabilities ------------------------------------------------------


def weather_probabilities(bundle: Bundle, airport: Airport, asof_utc: pd.Timestamp) -> tuple[pd.DataFrame | None, str | None]:
    """Published model probabilities at this exact cutoff, or the reason there are none."""
    table = bundle.table("weather_probabilities")
    if table is None:
        return None, bundle.problem("weather_probabilities")
    rows = table[(table["airport"] == airport.icao) & (table["asof_utc"] == asof_utc)]
    if rows.empty:
        return None, "No weather probability forecast at this exact cutoff."
    if (rows["features_available_at_utc"] > asof_utc).any():
        return None, "Weather probabilities used inputs later than the cutoff, so replay refuses them."
    return rows, None


PLACEHOLDER_VERSION = "Illustrative placeholder, not a model"
PLACEHOLDER_LABEL = "ILLUSTRATIVE · NOT A MODEL"
# Fixed proof-of-concept values from the UI handoff. They ignore the airport, cutoff and weather.
PLACEHOLDER_SHARES = {
    3: {"Thunderstorm": .70, "IFR / LIFR": .55, "Visibility < 3 SM": .35, "Gusts ≥ 25 kt": .60, "VFR": .20, "MVFR": .25, "IFR": .45, "LIFR": .10},
    6: {"Thunderstorm": .45, "IFR / LIFR": .30, "Visibility < 3 SM": .20, "Gusts ≥ 25 kt": .35, "VFR": .35, "MVFR": .35, "IFR": .25, "LIFR": .05},
    12: {"Thunderstorm": .20, "IFR / LIFR": .10, "Visibility < 3 SM": .10, "Gusts ≥ 25 kt": .15, "VFR": .70, "MVFR": .20, "IFR": .08, "LIFR": .02},
}
PLACEHOLDER_CEILING = {3: (900, 500, 1800), 6: (2500, 1200, 3800), 12: (4000, 2500, 6500)}


def is_placeholder(rows: pd.DataFrame | None) -> bool:
    return rows is not None and (rows["model_version"] == PLACEHOLDER_VERSION).all()


def display_probabilities(bundle: Bundle, airport: Airport, asof_utc: pd.Timestamp) -> tuple[pd.DataFrame, None]:
    """Real output when published, else placeholders for display. Compare never reads these."""
    rows, _ = weather_probabilities(bundle, airport, asof_utc)
    if rows is not None:
        return rows, None
    records = [
        {"condition": condition, "horizon_hours": lead, "probability": share, "value": None, "lower": None, "upper": None, "model_version": PLACEHOLDER_VERSION}
        for lead, shares in PLACEHOLDER_SHARES.items() for condition, share in shares.items()
    ] + [
        {"condition": "Ceiling", "horizon_hours": lead, "probability": None, "value": v, "lower": lo, "upper": hi, "model_version": PLACEHOLDER_VERSION}
        for lead, (v, lo, hi) in PLACEHOLDER_CEILING.items()
    ]
    return pd.DataFrame(records), None


def probability(rows: pd.DataFrame | None, condition: str, horizon: int) -> float | None:
    if rows is None:
        return None
    match = rows[(rows["condition"] == condition) & (rows["horizon_hours"] == horizon)]
    return None if match.empty or pd.isna(match.iloc[0]["probability"]) else float(match.iloc[0]["probability"])


def taf_state(row: pd.Series, condition: str) -> str:
    """What the published TAF says, in its own terms. Never converted to a probability."""
    prevailing, conditional = _taf_flags(row)[condition]
    if pd.isna(prevailing):
        return "Unknown"
    if prevailing:
        return "Forecast"
    return "Conditional group" if conditional else "Not forecast"


def _taf_flags(row: pd.Series) -> dict[str, tuple]:
    def met(value, test):
        return pd.NA if pd.isna(value) else bool(test(value))

    visibility, ceiling = row["visibility_sm"], row["ceiling_ft_agl"]
    low_vis, low_ceiling = met(visibility, lambda v: v < 3), met(ceiling, lambda v: v < 1000)
    low = pd.NA if pd.isna(low_vis) or pd.isna(low_ceiling) else (low_vis or low_ceiling)
    cond_vis = bool(pd.notna(row["cond_min_visibility_sm"]) and row["cond_min_visibility_sm"] < 3)
    cond_ceiling = bool(pd.notna(row["cond_min_ceiling_ft_agl"]) and row["cond_min_ceiling_ft_agl"] < 1000)
    cond_gust = bool(pd.notna(row["cond_max_gust_kt"]) and row["cond_max_gust_kt"] >= 25)
    storm = row["thunderstorm_flag"]
    return {
        "Thunderstorm": (pd.NA if pd.isna(storm) else storm == 1, row["cond_thunderstorm_flag"] == 1),
        "IFR / LIFR": (low, cond_vis or cond_ceiling),
        "Visibility < 3 SM": (low_vis, cond_vis),
        "Gusts ≥ 25 kt": (met(row["wind_gust_kt"], lambda v: v >= 25), cond_gust),
    }


# --- Movement forecasts ---------------------------------------------------------


@dataclass(frozen=True)
class MovementForecast:
    hour_utc: pd.Timestamp
    direction: str
    forecast: float
    lower: float | None
    upper: float | None
    interval_level: float | None
    method: str
    provenance: str


@dataclass
class MovementForecasts:
    rows: list[MovementForecast] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)
    held: bool = False

    def at(self, hour: pd.Timestamp, direction: str) -> MovementForecast | None:
        return next((r for r in self.rows if r.hour_utc == hour and r.direction == direction), None)


def agreement_pending(bundle: Bundle) -> bool:
    """The arrivals forecast waits on team sign-off, recorded by its producer."""
    document = bundle.docs.get("throughput_evaluation") or {}
    return (document.get("team_agreement") or {}).get("status") != "agreed"


def movement_forecasts(bundle: Bundle, airport: Airport, asof_utc: pd.Timestamp, preview_held: bool) -> MovementForecasts:
    """All published movement forecasts at the cutoff, with a reason for each missing direction."""
    result = MovementForecasts()
    published = bundle.table("movement_forecast")
    if published is not None:
        rows = published[
            (published["airport"] == airport.icao) & (published["asof_utc"] == asof_utc)
            & (published["features_available_at_utc"] <= asof_utc)
        ]
        for row in rows.itertuples():
            result.rows.append(
                MovementForecast(
                    row.target_hour_utc, row.direction, float(row.forecast), row.lower, row.upper,
                    row.interval_level, row.method, row.provenance,
                )
            )
    if not any(r.direction == "arrival" for r in result.rows):
        _add_throughput(bundle, airport, asof_utc, preview_held, result)
    for direction, name in (("arrival", "incoming"), ("departure", "outgoing")):
        if direction not in result.reasons and not any(r.direction == direction for r in result.rows):
            result.reasons[direction] = f"No {name} movement forecast is published at this cutoff."
    return result


def _add_throughput(bundle: Bundle, airport: Airport, asof_utc: pd.Timestamp, preview_held: bool, result: MovementForecasts) -> None:
    table = bundle.table("throughput_forecast")
    if table is None:
        return
    rows = table[
        (table["airport"] == airport.icao) & (table["asof_utc"] == asof_utc)
        & (table["features_available_at_utc"] <= asof_utc) & table["arrivals_pred"].notna()
    ]
    if rows.empty:
        return
    if agreement_pending(bundle) and not preview_held:
        result.reasons["arrival"] = (
            "Observed-arrivals forecast is held: team agreement is pending (parallel-plan section 7)."
        )
        return
    result.held = agreement_pending(bundle)
    document = bundle.docs.get("throughput_evaluation") or {}
    interval = document.get("uncertainty") or {}
    for row in rows.itertuples():
        result.rows.append(
            MovementForecast(
                row.target_hour_utc, "arrival", float(row.arrivals_pred), float(row.arrivals_lower),
                float(row.arrivals_upper), interval.get("nominal"), row.model_version,
                "Observed reporting-carrier arrivals, not AAR",
            )
        )


def last_completed_hour(traffic: pd.DataFrame | None, airport: Airport, asof_utc: pd.Timestamp) -> dict | None:
    """Observed counts for the hour ending at the cutoff, which was complete when the forecast froze."""
    if traffic is None:
        return None
    hour = asof_utc - pd.Timedelta(hours=1)
    rows = traffic[(traffic["airport"] == airport.icao) & (traffic["hour_utc"] == hour)]
    counts = {row.direction: row.actual_count for row in rows.itertuples()}
    if pd.isna(counts.get("arrival", pd.NA)) or pd.isna(counts.get("departure", pd.NA)):
        return None
    return {"hour_utc": hour, "incoming": int(counts["arrival"]), "outgoing": int(counts["departure"])}


def hourly_movements(
    traffic: pd.DataFrame | None, forecasts: MovementForecasts, airport: Airport, asof_utc: pd.Timestamp,
    reveal: bool, before: int = 3, after: int = 12,
) -> pd.DataFrame:
    """One row per hour. Actuals before the cutoff were known then; later ones need a reveal."""
    hours = pd.date_range(asof_utc - pd.Timedelta(hours=before), periods=before + after + 1, freq="h")
    rows = pd.DataFrame({"hour_utc": hours})
    for direction, name in (("arrival", "incoming"), ("departure", "outgoing")):
        source = pd.DataFrame(columns=["hour_utc", "scheduled_count", "actual_count"])
        if traffic is not None:
            source = traffic[(traffic["airport"] == airport.icao) & (traffic["direction"] == direction)]
        indexed = source.set_index("hour_utc").reindex(hours)
        rows[f"{name}_scheduled"] = indexed["scheduled_count"].to_numpy()
        actual = indexed["actual_count"].astype("Float64").to_numpy(dtype=float, na_value=float("nan"))
        rows[f"{name}_observed"] = pd.Series(actual).where(hours < asof_utc)
        rows[f"{name}_actual"] = pd.Series(actual).where(hours >= asof_utc) if reveal else float("nan")
        found = [forecasts.at(hour, direction) for hour in hours]
        rows[f"{name}_forecast"] = [f.forecast if f else float("nan") for f in found]
        rows[f"{name}_lower"] = [f.lower if f and f.lower is not None else float("nan") for f in found]
        rows[f"{name}_upper"] = [f.upper if f and f.upper is not None else float("nan") for f in found]
    return rows


# --- Event verification ---------------------------------------------------------


@dataclass(frozen=True)
class EventVerification:
    forecast_key: str
    condition: str
    definition: str
    window_start_utc: pd.Timestamp
    window_end_utc: pd.Timestamp
    forecast_basis: str
    forecast_label: str
    probability: float | None
    alert: bool | None
    actual: str
    evidence_utc: pd.Timestamp | None
    reports: int
    result: str
    verified_as_of_utc: pd.Timestamp


def verification_as_of(snapshot: Snapshot) -> pd.Timestamp:
    return snapshot.target_hour_utc + WINDOW + REVIEW_DELAY


def event_observations(weather: pd.DataFrame | None, snapshot: Snapshot) -> pd.DataFrame:
    """METARs inside the event window that were already available at the review time."""
    if weather is None:
        return pd.DataFrame()
    start = snapshot.target_hour_utc
    rows = weather[
        (weather["airport"] == snapshot.airport.icao) & (weather["kind"] == "observation")
        & (weather["valid_from_utc"] >= start) & (weather["valid_from_utc"] < start + WINDOW)
        & (weather["available_at_utc"] <= verification_as_of(snapshot))
    ]
    return rows.sort_values("valid_from_utc")


def _observed(rows: pd.DataFrame, condition: str) -> tuple[pd.Series, pd.Series]:
    """Per report: whether the event held, and whether that report could show it at all."""
    if condition == "Thunderstorm":
        return rows["thunderstorm_flag"] == 1, rows["thunderstorm_flag"].notna()
    if condition == "IFR / LIFR":
        return (
            (rows["visibility_sm"] < 3) | (rows["ceiling_ft_agl"] < 1000),
            rows["visibility_sm"].notna() & rows["ceiling_ft_agl"].notna(),
        )
    if condition == "Visibility < 3 SM":
        return rows["visibility_sm"] < 3, rows["visibility_sm"].notna()
    return rows["wind_gust_kt"] >= 25, rows["wind_gust_kt"].notna()


def _actual_text(rows: pd.DataFrame, condition: str, happened: pd.Series) -> tuple[str, pd.Timestamp | None]:
    if happened.any():
        first = rows[happened].iloc[0]
        when = first["valid_from_utc"]
        clock = when.strftime("%H:%M")
        if condition == "Visibility < 3 SM":
            return f"Observed {clock}, {first['visibility_sm']:.1f} SM", when
        if condition == "IFR / LIFR":
            return f"Observed {clock}, {first['visibility_sm']:.1f} SM, ceiling {first['ceiling_ft_agl']:,.0f} ft", when
        if condition == "Gusts ≥ 25 kt":
            return f"Observed {clock}, gust {first['wind_gust_kt']:.0f} kt", when
        return f"Observed {clock}", when
    last = rows["valid_from_utc"].iloc[-1]
    if condition == "Gusts ≥ 25 kt":
        strongest = rows.loc[rows["wind_gust_kt"].idxmax()]
        return f"Did not occur; max {strongest['wind_gust_kt']:.0f} kt", strongest["valid_from_utc"]
    return "Did not occur", last


def verify_events(bundle: Bundle, snapshot: Snapshot) -> tuple[list[EventVerification], str | None]:
    """Score each saved forecast against METARs. A window without reports is never a non-event."""
    probabilities, _ = weather_probabilities(bundle, snapshot.airport, snapshot.asof_utc)
    feature, reason = weather_feature_row(bundle, snapshot)
    if feature is None and probabilities is None:
        return [], reason
    observations = event_observations(bundle.table("weather"), snapshot)
    as_of = verification_as_of(snapshot)
    results = []
    for condition in PROBABILITY_CONDITIONS:
        share = probability(probabilities, condition, snapshot.horizon_hours)
        if share is not None:
            basis, label, alert = "Model probability", f"{share:.0%}", share >= ALERT_THRESHOLD
        else:
            state = taf_state(feature, condition) if feature is not None else "Unknown"
            basis, label = "Published TAF", state
            alert = None if state == "Unknown" else state == "Forecast"
        happened = pd.Series(dtype=bool)
        usable = 0
        if not observations.empty:
            happened, known = _observed(observations, condition)
            usable = int(known.sum())
        actual, evidence, outcome = "No observation", None, "No observation"
        if usable:
            rows = observations[known]
            actual, evidence = _actual_text(rows, condition, happened[known])
            outcome = _result(alert, bool(happened[known].any()))
        results.append(
            EventVerification(
                f"{snapshot.airport.icao}|{snapshot.asof_utc:%Y%m%dT%H}|+{snapshot.horizon_hours}|{condition}",
                condition, DEFINITIONS[condition], snapshot.target_hour_utc, snapshot.target_hour_utc + WINDOW,
                basis, label, share, alert, actual, evidence, usable, outcome, as_of,
            )
        )
    return results, None


def _result(alert: bool | None, occurred: bool) -> str:
    if alert is None:
        return "Pending"
    if alert:
        return "Matched alert" if occurred else "False alert"
    return "Missed event" if occurred else "Correctly quiet"


def alert_counts(results: list[EventVerification]) -> dict[str, int]:
    def count(label: str) -> int:
        return sum(r.result == label for r in results)

    return {
        "alerts": sum(r.alert is True for r in results), "matched": count("Matched alert"),
        "false": count("False alert"), "missed": count("Missed event"), "unscored": count("No observation") + count("Pending"),
    }


def event_log(results: list[EventVerification], observations: pd.DataFrame) -> list[tuple[pd.Timestamp, str]]:
    """What happened, oldest first: each observed event once, then the strongest gust as evidence."""
    entries = [
        (r.evidence_utc, f"{r.condition}: {r.actual}")
        for r in results if r.evidence_utc is not None and r.actual.startswith("Observed")
    ]
    gusts = observations["wind_gust_kt"].dropna() if not observations.empty else pd.Series(dtype=float)
    if len(gusts):
        strongest = observations.loc[gusts.idxmax()]
        entries.append((strongest["valid_from_utc"], f"Maximum wind or gust {strongest['wind_gust_kt']:.0f} kt"))
    return sorted(entries, key=lambda entry: entry[0])


# --- Proposed actions -----------------------------------------------------------


def proposed_actions(bundle: Bundle, snapshot: Snapshot) -> tuple[dict[str, pd.Series], str]:
    """Saved proposals by condition. The reason explains any gap; it is shown beside each row."""
    table = bundle.table("proposed_actions")
    found = {}
    if table is not None:
        rows = snapshot.rows(table)
        found = {row["condition"]: row for _, row in rows.iterrows()}
    document = bundle.docs.get("recommendations") or {}
    missing = [str(item).split(":")[0] for item in document.get("missing_inputs", [])]
    if missing:
        return found, f"No proposal saved: {', '.join(missing)} not verified."
    return found, "No proposal saved at this cutoff."


def forecast_valid_labels(snapshot: Snapshot) -> list[dict]:
    """Stops for the map timeline: the cutoff, then each scored lead."""
    stops = [{"lead": 0, "label": snapshot.asof_utc.strftime("%H:%M"), "selected": False}]
    for lead in SCORED_HORIZONS:
        target = snapshot.asof_utc + pd.Timedelta(hours=lead)
        suffix = " +1d" if target.date() != snapshot.asof_utc.date() else ""
        stops.append({"lead": lead, "label": f"{target:%H:%M}{suffix}", "selected": lead == snapshot.horizon_hours})
    return stops


def review_brief(bundle: Bundle, snapshot: Snapshot) -> tuple[dict | None, str | None, str | None]:
    """Controller review brief for the exact on-screen snapshot, built in memory from the
    hash-verified predictions with the same summarizer as tools.delivery.controller_brief.
    Returns (brief, markdown, reason); writes nothing to disk."""
    from tools.delivery.controller_brief import markdown, summarize

    predictions = bundle.table("predictions")
    group = bundle.groups.get("risk")
    if predictions is None or group is None or group.manifest is None:
        return None, None, bundle.problem("predictions")
    manifest = group.manifest
    if snapshot.rows(predictions).empty:
        # exact key only: never substitute another cutoff or lead (and the shared summarizer
        # cannot reduce an empty pandas string column)
        return None, None, "No published predictions at this exact cutoff and lead, so no review brief."
    try:
        brief = summarize(predictions, snapshot.airport.icao, snapshot.asof_utc, snapshot.horizon_hours,
                          manifest.get("run_id"))
    except ValueError as error:
        return None, None, f"Review brief withheld: {error}"
    brief["evidence"] = {
        "predictions": "artifacts/risk/predictions.parquet",
        "predictions_sha256": (manifest.get("artifact_hashes") or {}).get("predictions.parquet"),
        "verified_by": "dashboard loader (manifest hash check)",
    }
    return brief, markdown(brief), None
