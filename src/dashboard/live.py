"""Current public weather. Read-only, fetched on request, and never used by replay.

A feed keeps the last good report per station, so one failed source shows an honest cached
state with its original timestamp rather than a blank or a report that looks fresh.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import requests

from src.shared import AIRPORTS

PUBLIC_WEATHER = os.environ.get("LIVE_WEATHER_URL", "https://aviationweather.gov/api/data")
RADAR_STATUS = os.environ.get(
    "LIVE_RADAR_URL", "https://mesonet.agron.iastate.edu/data/gis/images/4326/USCOMP/n0q_0.json"
)
STALE_OBSERVATION_MINUTES = 90
HISTORY_HOURS = 4
HPA_TO_INHG = 0.02953
TIMEOUT_SECONDS = 12
HEADERS = {"User-Agent": "AirportPlanningPrototype/1.0"}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_reports(icao: str) -> list[dict]:
    url = f"{PUBLIC_WEATHER}/metar?ids={icao}&format=json&hours={HISTORY_HOURS}"
    response = requests.get(url, timeout=TIMEOUT_SECONDS, headers=HEADERS)
    response.raise_for_status()
    records = response.json()
    if not isinstance(records, list):
        raise ValueError("expected a list response")
    return sorted(records, key=lambda record: record.get("obsTime") or 0, reverse=True)


def _fetch_radar() -> dict:
    response = requests.get(RADAR_STATUS, timeout=TIMEOUT_SECONDS, headers=HEADERS)
    response.raise_for_status()
    valid = (response.json().get("meta") or {}).get("valid")
    if not valid:
        raise ValueError("radar status has no valid time")
    return {"status": "available", "valid_utc": valid, "error": None}


def _refresh_station(icao: str, previous: dict | None, retrieved: str) -> dict:
    """A failed or empty read keeps the last good reports and says so."""
    try:
        reports = _fetch_reports(icao)
        if not reports:
            raise ValueError("no report returned")
    except (requests.RequestException, ValueError) as error:
        message = f"{type(error).__name__}: {error}"
        if previous and previous.get("reports"):
            return {**previous, "status": "cached", "error": message}
        return {"status": "unavailable", "reports": [], "retrieved_at_utc": None, "error": message}
    return {"status": "available", "reports": reports, "retrieved_at_utc": retrieved, "error": None}


def _refresh_radar(previous: dict | None) -> dict:
    try:
        return _fetch_radar()
    except (requests.RequestException, ValueError) as error:
        message = f"{type(error).__name__}: {error}"
        if previous and previous.get("valid_utc"):
            return {**previous, "status": "cached", "error": message}
        return {"status": "unavailable", "valid_utc": None, "error": message}


def refresh_feed(feed: dict | None = None, only: list[str] | None = None) -> dict:
    """Refresh every source, or just the named ones. A failure never raises."""
    feed = feed or {"stations": {}, "radar": None}
    retrieved = now_utc()
    names = only if only is not None else [*AIRPORTS, "radar"]
    stations = dict(feed["stations"])
    for icao in AIRPORTS:
        if icao in names:
            stations[icao] = _refresh_station(icao, stations.get(icao), retrieved)
    radar = _refresh_radar(feed["radar"]) if "radar" in names else feed["radar"]
    return {"retrieved_at_utc": retrieved, "stations": stations, "radar": radar}


def failed_sources(feed: dict) -> list[str]:
    names = [icao for icao, station in feed["stations"].items() if station["status"] != "available"]
    if feed["radar"] and feed["radar"]["status"] != "available":
        names.append("radar")
    return names


def latest(station: dict | None) -> dict | None:
    reports = (station or {}).get("reports") or []
    return reports[0] if reports else None


def ceiling_ft(message: dict) -> int | None:
    bases = [
        layer["base"]
        for layer in message.get("clouds") or []
        if layer.get("cover") in ("BKN", "OVC", "VV") and layer.get("base") is not None
    ]
    return min(bases) if bases else None


def observed_at(message: dict) -> pd.Timestamp | None:
    return None if message.get("obsTime") is None else pd.to_datetime(message["obsTime"], unit="s", utc=True)


def observation_age_minutes(message: dict, now: pd.Timestamp) -> float | None:
    stamp = observed_at(message)
    return None if stamp is None else (now - stamp).total_seconds() / 60


def age_label(minutes: float | None) -> str:
    return "age unknown" if minutes is None else f"{minutes:.0f} min old"


def is_stale(message: dict, now: pd.Timestamp) -> bool:
    age = observation_age_minutes(message, now)
    return age is not None and age > STALE_OBSERVATION_MINUTES


def wind_text(message: dict) -> str:
    direction, speed, gust = message.get("wdir"), message.get("wspd"), message.get("wgst")
    if speed is None:
        return "Unknown"
    heading = "VRB" if direction == "VRB" else f"{direction}°" if direction is not None else "?"
    return f"{heading} {speed}G{gust} kt" if gust else f"{heading} {speed} kt"


def pressure_inhg(message: dict) -> float | None:
    """The API reports altimeter setting in hectopascals."""
    return None if message.get("altim") is None else float(message["altim"]) * HPA_TO_INHG


def category(message: dict) -> str:
    value = message.get("fltCat")
    return value if value in ("VFR", "MVFR", "IFR", "LIFR") else "Unknown"


def recent_rows(station: dict | None) -> list[dict]:
    """Reports newest first, one per row, in the units the table shows."""
    rows = []
    for message in (station or {}).get("reports") or []:
        stamp = observed_at(message)
        ceiling = ceiling_ft(message)
        rows.append(
            {
                "observed": "Unknown" if stamp is None else stamp.strftime("%H:%M"),
                "category": category(message),
                "visibility": f"{message.get('visib', 'Unknown')} SM",
                "ceiling": "None reported" if ceiling is None else f"{ceiling:,} ft",
                "wind": wind_text(message),
                "temperature": "Unknown" if message.get("temp") is None else f"{message['temp']:.0f}°C",
            }
        )
    return rows
