"""Paths, airport metadata resolution and run identity."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PUBLIC_DIR = REPO_ROOT / "data" / "public"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
CAPACITY_DIR = REPO_ROOT / "artifacts" / "capacity"
HANDOVER_DIR = REPO_ROOT / "handover"

# The supplied challenge CSV. Member 2's docs place it at data/weather/; this
# checkout keeps it in claude-upload/. First existing candidate wins.
FLIGHT_CSV_CANDIDATES = [
    REPO_ROOT / "data" / "weather" / "Flight_Data_With_Weather_Final.csv",
    REPO_ROOT / "claude-upload" / "Flight_Data_With_Weather_Final.csv",
]

DEFAULT_START = "2023-01-01"  # local flight dates, inclusive
DEFAULT_END = "2025-07-31"
HORIZONS = (3, 6, 12)

# Publication-latency assumption: IEM archives only issuance/observation time,
# not receipt time. Inputs are treated as available this many minutes later.
TAF_LATENCY_MIN = 10
METAR_LATENCY_MIN = 10
# A routine TAF is issued every 6 h; anything older than this at cutoff is stale.
TAF_MAX_AGE_H = 12
METAR_MAX_AGE_H = 2
# TAF period length. The IEM archive omits the TAF validity header; US TAFs at
# large hubs (ATL, DFW) cover 30 h from their 00/06/12/18Z cycle, and every
# archived FM group for both airports starts within 30 h of issuance.
TAF_VALIDITY_H = 30


@dataclass(frozen=True)
class Airport:
    icao: str
    iata: str
    timezone: str
    runway_heading_deg: float
    metar_station: str  # IEM ASOS identifier
    taf_station: str  # IEM TAF identifier
    lat: float | None = None
    lon: float | None = None


# Fallback used ONLY when Member 3's shared registry (src.shared) is absent.
# Headings are the challenge assumptions (ATL 080, DFW 180).
_FALLBACK_REGISTRY = {
    "KATL": Airport("KATL", "ATL", "America/New_York", 80.0, "ATL", "KATL", 33.6367, -84.4281),
    "KDFW": Airport("KDFW", "DFW", "America/Chicago", 180.0, "DFW", "KDFW", 32.8968, -97.0380),
}


def registry_source() -> str:
    try:
        import src.shared as shared  # noqa: F401  (owned by Member 3)

        if hasattr(shared, "AIRPORTS"):
            return "src.shared.AIRPORTS"
    except Exception:
        pass
    return "src.data_capacity.config fallback (src.shared absent)"


def load_registry() -> dict[str, Airport]:
    """Return {ICAO: Airport}. Prefer the shared registry when present."""
    try:
        from src.shared import AIRPORTS  # type: ignore

        out = {}
        for key, rec in AIRPORTS.items():
            get = rec.get if isinstance(rec, dict) else (lambda k, d=None, r=rec: getattr(r, k, d))
            icao = get("icao") or key
            out[icao] = Airport(
                icao=icao,
                iata=get("iata"),
                timezone=get("timezone") or get("tz"),
                runway_heading_deg=float(get("heading") if get("heading") is not None else get("runway_heading_deg")),
                metar_station=get("metar_station") or get("iata"),
                taf_station=get("taf_station") or icao,
                lat=get("lat"),
                lon=get("lon"),
            )
        return out
    except Exception:
        return dict(_FALLBACK_REGISTRY)


class UnsupportedAirport(KeyError):
    pass


def resolve_airports(codes: list[str]) -> list[Airport]:
    reg = load_registry()
    by_iata = {a.iata: a for a in reg.values()}
    out = []
    for code in codes:
        code = code.upper()
        ap = reg.get(code) or by_iata.get(code)
        if ap is None or not ap.timezone:
            raise UnsupportedAirport(
                f"{code}: no registry metadata (timezone/heading); unsupported rather than guessed"
            )
        out.append(ap)
    return out


def find_flight_csv(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    for p in FLIGHT_CSV_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("Flight_Data_With_Weather_Final.csv not found in " + ", ".join(map(str, FLIGHT_CSV_CANDIDATES)))


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def new_run_id(now: datetime | None = None) -> str:
    now = now or utcnow()
    salt = hashlib.sha256(f"{now.isoformat()}{os.getpid()}".encode()).hexdigest()[:6]
    return f"m1-{now:%Y%m%dT%H%M%SZ}-{salt}"
