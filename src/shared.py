"""Configuration and identity shared by every subsystem."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "airports.json"
REQUIRED_AIRPORT_FIELDS = ("icao", "iata", "timezone", "runway_heading_deg", "station")


@dataclass(frozen=True)
class Airport:
    icao: str
    iata: str
    timezone: str
    runway_heading_deg: int
    station: str
    name: str | None = None
    latitude: float | None = None
    longitude: float | None = None


def load_airports(path: Path = REGISTRY_PATH) -> dict[str, Airport]:
    """Read the registry, keyed by ICAO. Unknown metadata fails; it is never defaulted."""
    records = json.loads(path.read_text(encoding="utf-8"))["airports"]
    airports = {}
    for record in records:
        missing = [f for f in REQUIRED_AIRPORT_FIELDS if record.get(f) is None]
        if missing:
            raise ValueError(f"Airport {record.get('icao') or record!r} lacks {missing}")
        airports[record["icao"]] = Airport(**record)
    return airports


AIRPORTS = load_airports()


def resolve_airport(code: str) -> Airport | None:
    """Find an airport by ICAO or IATA code; None means unsupported, not a default."""
    for airport in AIRPORTS.values():
        if code in (airport.icao, airport.iata):
            return airport
    return None


def flight_key(date, carrier, number, origin, dest, scheduled_hhmm) -> str:
    """Stable flight ID from the original local schedule, never actual outcomes.

    Recovered from published IDs: bfd0e37ba4944076cf85 is
    2025-01-13|AA|2667|DFW|LAS|2000. Zero-padding of times before 10:00 is not
    covered by that example; confirm it against Member 2's copy.
    """
    text = "|".join(
        [
            str(date)[:10],
            str(carrier),
            str(int(float(number))),
            str(origin),
            str(dest),
            f"{int(float(scheduled_hhmm)):04d}",
        ]
    )
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]
