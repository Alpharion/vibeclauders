"""Current public weather. Read-only, fetched on request, and never used by replay."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import requests

from src.shared import AIRPORTS

PUBLIC_WEATHER = "https://aviationweather.gov/api/data"
STALE_OBSERVATION_MINUTES = 90


def fetch_live_weather() -> dict:
    """Read METAR and TAF; a failed product is recorded rather than raised."""
    ids = ",".join(AIRPORTS)
    bundle = {"retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "errors": []}
    for product in ("metar", "taf"):
        url = f"{PUBLIC_WEATHER}/{product}?ids={ids}&format=json"
        try:
            response = requests.get(url, timeout=12, headers={"User-Agent": "AirportPlanningPrototype/1.0"})
            response.raise_for_status()
            records = response.json()
            if not isinstance(records, list):
                raise ValueError("expected a list response")
            bundle[product] = records
        except (requests.RequestException, ValueError) as error:
            bundle[product] = []
            bundle["errors"].append(f"{product.upper()}: {type(error).__name__}: {error}")
    return bundle


def for_airport(records: list[dict], icao: str) -> dict | None:
    return next((record for record in records if record.get("icaoId") == icao), None)


def ceiling_ft(message: dict) -> int | None:
    bases = [
        layer["base"]
        for layer in message.get("clouds") or []
        if layer.get("cover") in ("BKN", "OVC", "VV") and layer.get("base") is not None
    ]
    return min(bases) if bases else None


def observation_age_minutes(message: dict, now: pd.Timestamp) -> float | None:
    if message.get("obsTime") is None:
        return None
    return (now - pd.to_datetime(message["obsTime"], unit="s", utc=True)).total_seconds() / 60


def forecast_table(message: dict | None) -> pd.DataFrame:
    """Decoded TAF periods. Conditional groups stay labelled, separate from prevailing."""
    rows = []
    for period in (message or {}).get("fcsts") or []:
        clouds = period.get("clouds") or []
        rows.append(
            {
                "From UTC": pd.to_datetime(period.get("timeFrom"), unit="s", utc=True),
                "To UTC": pd.to_datetime(period.get("timeTo"), unit="s", utc=True),
                "Condition": period.get("fcstChange") or "Prevailing",
                "Probability %": period.get("probability"),
                "Wind kt": period.get("wspd"),
                "Direction °": period.get("wdir"),
                "Gust kt": period.get("wgst"),
                "Visibility SM": str(period.get("visib", "")),
                "Weather": period.get("wxString") or "",
                "Clouds": "; ".join(f"{c.get('cover', '')} {c.get('base', '')} ft" for c in clouds),
            }
        )
    return pd.DataFrame(rows)
