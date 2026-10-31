"""Small, stable helpers shared by the three implementation members."""
from hashlib import sha1

AIRPORTS = {
    "KATL": {"iata": "ATL", "name": "Atlanta", "timezone": "America/New_York", "heading": 80, "lat": 33.6367, "lon": -84.4281},
    "KDFW": {"iata": "DFW", "name": "Dallas / Fort Worth", "timezone": "America/Chicago", "heading": 180, "lat": 32.8968, "lon": -97.0380},
}

def airport_icao(value):
    value = str(value).upper()
    return next((icao for icao, info in AIRPORTS.items() if info["iata"] == value), value)

def flight_key(date, carrier, number, origin, dest, scheduled_hhmm):
    """Stable key from original local flight-date and schedule, never actuals."""
    number = str(number).removesuffix(".0")
    hhmm = str(int(float(scheduled_hhmm))).zfill(4)
    text = "|".join([str(date)[:10], str(carrier), number, str(origin), str(dest), hhmm])
    return sha1(text.encode("utf-8")).hexdigest()[:20]
