"""Read-only artifact adapters and public current-weather retrieval."""
from pathlib import Path
from datetime import datetime, timezone
import json
import pandas as pd
import requests
import streamlit as st
from src.shared import AIRPORTS, airport_icao, flight_key

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_WEATHER = "https://aviationweather.gov/api/data"

def utc(series):
    return pd.to_datetime(series, utc=True, errors="coerce")

@st.cache_data(show_spinner=False)
def airports():
    path = ROOT / "data/reference/airports.json"
    records = json.loads(path.read_text(encoding="utf-8"))["airports"] if path.exists() else []
    lookup = {x["iata"]: x for x in records}
    for icao, info in AIRPORTS.items():
        lookup.setdefault(info["iata"], {"iata": info["iata"], "icao": icao, "name": info["name"], "latitude": info["lat"], "longitude": info["lon"], "timezone": info["timezone"]})
    return lookup

def local_schedule(dates, values, zone):
    """BTS HHMM schedules use local times, including 2400 for next midnight."""
    values = pd.to_numeric(values, errors="coerce")
    hours, minutes = values // 100, values % 100
    valid = ((hours.between(0, 23) & minutes.between(0, 59)) | values.eq(2400))
    naive = pd.to_datetime(dates, errors="coerce") + pd.to_timedelta(hours, unit="h") + pd.to_timedelta(minutes, unit="m")
    return naive.where(valid).dt.tz_localize(zone, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")

@st.cache_data(show_spinner=False)
def _sample_flights(path, stamp):
    cols = ["FL_DATE", "OP_UNIQUE_CARRIER", "OP_CARRIER_FL_NUM", "ORIGIN", "DEST", "CRS_DEP_TIME", "CRS_ARR_TIME", "CRS_ELAPSED_TIME", "DEP_DELAY", "ARR_DELAY", "CANCELLED", "DIVERTED"]
    raw = pd.read_csv(path, usecols=cols)
    raw = raw[raw.ORIGIN.isin(["ATL", "DFW"]) | raw.DEST.isin(["ATL", "DFW"])].copy()
    out = pd.DataFrame(index=raw.index)
    out["flight_id"] = [flight_key(*row) for row in raw[["FL_DATE", "OP_UNIQUE_CARRIER", "OP_CARRIER_FL_NUM", "ORIGIN", "DEST", "CRS_DEP_TIME"]].itertuples(index=False, name=None)]
    out["origin"], out["dest"] = raw.ORIGIN, raw.DEST
    out["carrier"], out["flight_number"] = raw.OP_UNIQUE_CARRIER, raw.OP_CARRIER_FL_NUM.astype(str).str.removesuffix(".0")
    lookup = airports()
    out["scheduled_dep_utc"] = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")
    for code, idx in raw.groupby("ORIGIN").groups.items():
        zone = lookup.get(code, {}).get("timezone")
        if zone and zone != "\\N":
            out.loc[idx, "scheduled_dep_utc"] = local_schedule(raw.loc[idx, "FL_DATE"], raw.loc[idx, "CRS_DEP_TIME"], zone)
    # Scheduled elapsed time resolves arrival-local midnight/day changes without using actuals.
    out["scheduled_arr_utc"] = out.scheduled_dep_utc + pd.to_timedelta(raw.CRS_ELAPSED_TIME, unit="m")
    for target, original in [("dep_delay_min", "DEP_DELAY"), ("arr_delay_min", "ARR_DELAY"), ("cancelled", "CANCELLED"), ("diverted", "DIVERTED")]:
        out[target] = raw[original]
    out["coverage"] = "sample"
    out["source"] = "Challenge flight sample; reconstructed historical schedule"
    return out.reset_index(drop=True)

@st.cache_data(show_spinner=False)
def _read_table(path, stamp):
    return pd.read_parquet(path)

def artifact_table(relative, required=()):
    path = ROOT / relative
    if not path.exists():
        return pd.DataFrame(), f"Not connected: {relative}"
    try:
        table = _read_table(str(path), path.stat().st_mtime_ns)
        missing = set(required) - set(table.columns)
        if missing:
            return pd.DataFrame(), f"Invalid {relative}: missing {', '.join(sorted(missing))}"
        for col in table.columns:
            if col.endswith("_utc"):
                table[col] = utc(table[col])
        if "airport" in table:
            table["airport"] = table.airport.map(airport_icao)
        return table, None
    except Exception as exc:
        return pd.DataFrame(), f"Cannot load {relative}: {type(exc).__name__}: {exc}"

def flights():
    canonical = ROOT / "data/processed/flights.parquet"
    if canonical.exists():
        return artifact_table("data/processed/flights.parquet", ("flight_id", "origin", "dest", "scheduled_dep_utc", "scheduled_arr_utc", "coverage"))
    path = ROOT / "data/weather/Flight_Data_With_Weather_Final.csv"
    if not path.exists():
        return pd.DataFrame(), "Flight data not connected."
    return _sample_flights(str(path), path.stat().st_mtime_ns), None

def report(relative):
    path = ROOT / relative
    if not path.exists():
        return {"status": "unavailable", "limitations": [f"Not connected: {relative}"]}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("expected JSON object")
        return value
    except Exception as exc:
        return {"status": "unavailable", "limitations": [f"Invalid {relative}: {exc}"]}

def scope_predictions(table, airport, asof, horizon):
    if table.empty or not {"airport", "asof_utc", "horizon_hours"}.issubset(table):
        return table.iloc[:0]
    return table[(table.airport == airport) & (table.asof_utc == asof) & (pd.to_numeric(table.horizon_hours, errors="coerce") == horizon)].copy()

def movements(table, airport, start, end):
    iata = AIRPORTS[airport]["iata"]
    pieces = []
    for direction, endpoint, timecol in [("Inbound", "dest", "scheduled_arr_utc"), ("Outbound", "origin", "scheduled_dep_utc")]:
        part = table[(table[endpoint] == iata) & table[timecol].ge(start) & table[timecol].lt(end)].copy()
        part["direction"] = direction
        part["movement_utc"] = part[timecol]
        pieces.append(part)
    return pd.concat(pieces, ignore_index=True)

def validate_risk(table):
    if table.empty:
        return table
    result = table.copy()
    result["probability_severe_delay"] = pd.to_numeric(result.probability_severe_delay, errors="coerce")
    result["threshold"] = pd.to_numeric(result.threshold, errors="coerce")
    valid = result.probability_severe_delay.between(0, 1) & result.threshold.between(0, 1)
    return result[valid].drop_duplicates("flight_id", keep=False)

@st.cache_data(ttl=300, show_spinner=False)
def live_weather():
    result = {"retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "sources": [], "errors": []}
    for product in ["metar", "taf"]:
        url = f"{PUBLIC_WEATHER}/{product}?ids=KATL,KDFW&format=json"
        try:
            response = requests.get(url, timeout=12, headers={"User-Agent": "AirportPlanningPrototype/1.0"})
            response.raise_for_status()
            records = response.json()
            if not isinstance(records, list):
                raise ValueError("Expected list response")
            result[product] = records
            result["sources"].append(url)
        except (requests.RequestException, ValueError) as exc:
            result[product] = []
            result["errors"].append(f"{product.upper()}: {type(exc).__name__}: {exc}")
    return result
