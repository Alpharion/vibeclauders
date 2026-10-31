"""NOAA Storm Events (retrospective annotation only - NEVER a predictor).

Discovers the latest ``StormEvents_details`` file per year from the NCEI index,
caches it, and keeps events in the counties/zones around each airport. Events
are used to define evaluation cohorts after the fact; they are published
under data/processed/ and are not joined into weather_features.
"""
from __future__ import annotations

import gzip
import re
from io import BytesIO
from pathlib import Path

import pandas as pd

from .config import PUBLIC_DIR, Airport
from .io import DownloadError, fetch_cached

INDEX_URL = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
# County/zone names (CZ_NAME, upper case) treated as the airport's vicinity.
VICINITY = {
    "KATL": ("GEORGIA", {"FULTON", "CLAYTON", "DEKALB", "COBB", "HENRY", "FAYETTE", "SOUTH FULTON"}),
    "KDFW": ("TEXAS", {"TARRANT", "DALLAS", "DENTON", "COLLIN", "ELLIS", "JOHNSON"}),
}
RELEVANT_TYPES = {"Thunderstorm Wind", "Hail", "Heavy Rain", "Flash Flood", "Flood", "Tornado", "Lightning",
                  "Winter Storm", "Ice Storm", "Winter Weather", "Heavy Snow", "Dense Fog", "High Wind",
                  "Strong Wind", "Sleet", "Freezing Fog", "Funnel Cloud", "Tropical Storm"}
TZ_RE = re.compile(r"([A-Z]+)-?(\d+)")


def _validate_gz(body: bytes) -> None:
    with gzip.open(BytesIO(body)) as f:
        head = f.readline().decode("utf-8", errors="replace")
    if "BEGIN_YEARMONTH" not in head or "EVENT_TYPE" not in head:
        raise DownloadError("unexpected storm events header")


def discover(years: list[int], session=None) -> dict[int, str]:
    import requests

    resp = (session or requests).get(INDEX_URL, timeout=(15, 60))
    resp.raise_for_status()
    found = {}
    for y in years:
        names = sorted(set(re.findall(rf"StormEvents_details-ftp_v1\.0_d{y}_c\d+\.csv\.gz", resp.text)))
        if names:
            found[y] = names[-1]
    return found


def acquire(years: list[int], *, cache_only=False, refresh=False) -> list[dict]:
    cache = PUBLIC_DIR / "noaa_storms"
    recs = []
    if cache_only:
        for y in years:
            hits = sorted(cache.glob(f"StormEvents_details-ftp_v1.0_d{y}_c*.csv.gz"))
            if hits:
                recs.append(fetch_cached(INDEX_URL + hits[-1].name, hits[-1], validate=_validate_gz, cache_only=True) | {"year": y})
            else:
                recs.append({"year": y, "status": "failed", "error": "cache-only and no cached file", "url": INDEX_URL, "path": None})
        return recs
    try:
        names = discover(years)
    except Exception as exc:
        return [{"year": y, "status": "failed", "error": f"index: {exc}", "url": INDEX_URL, "path": None} for y in years]
    for y in years:
        if y not in names:
            recs.append({"year": y, "status": "failed", "error": "no details file listed", "url": INDEX_URL, "path": None})
            continue
        rec = fetch_cached(INDEX_URL + names[y], cache / names[y], validate=_validate_gz, refresh=refresh)
        recs.append(rec | {"year": y})
    return recs


def _to_utc(local: pd.Series, tzcode: pd.Series) -> pd.Series:
    # CZ_TIMEZONE like "EST-5" / "CST-6": a fixed standard offset (no DST)
    hours = tzcode.str.extract(TZ_RE)[1].astype(float)
    return (local + pd.to_timedelta(hours, unit="h")).dt.tz_localize("UTC")


def build_storms(records: list[dict], airports: list[Airport]) -> pd.DataFrame:
    frames = []
    for rec in records:
        if rec.get("status") == "failed" or not rec.get("path"):
            continue
        df = pd.read_csv(rec["path"], compression="gzip", low_memory=False)
        for ap in airports:
            if ap.icao not in VICINITY:
                continue
            state, names = VICINITY[ap.icao]
            m = (df["STATE"].str.upper() == state) & df["CZ_NAME"].str.upper().isin(names) & df["EVENT_TYPE"].isin(RELEVANT_TYPES)
            g = df[m]
            if g.empty:
                continue
            begin = pd.to_datetime(g["BEGIN_DATE_TIME"], format="%d-%b-%y %H:%M:%S")
            end = pd.to_datetime(g["END_DATE_TIME"], format="%d-%b-%y %H:%M:%S")
            frames.append(pd.DataFrame({
                "airport": ap.icao,
                "event_id": g["EVENT_ID"].astype("int64"),
                "episode_id": g["EPISODE_ID"],
                "event_type": g["EVENT_TYPE"],
                "cz_name": g["CZ_NAME"],
                "begin_utc": _to_utc(begin, g["CZ_TIMEZONE"]),
                "end_utc": _to_utc(end, g["CZ_TIMEZONE"]),
                "magnitude": pd.to_numeric(g["MAGNITUDE"], errors="coerce"),
                "magnitude_type": g["MAGNITUDE_TYPE"],
                "source_id": "noaa_storm_events",
                "source_file": Path(rec["path"]).name,
                "use": "retrospective_evaluation_only",
            }))
    if not frames:
        return pd.DataFrame(columns=["airport", "event_id", "event_type", "begin_utc", "end_utc"])
    return pd.concat(frames, ignore_index=True).drop_duplicates(["airport", "event_id"]).sort_values(["airport", "begin_utc"]).reset_index(drop=True)


def storm_hours(storms: pd.DataFrame) -> pd.DataFrame:
    """Hourly (airport, target_hour_utc) cells touched by any storm event."""
    rows = []
    for r in storms.itertuples():
        hrs = pd.date_range(r.begin_utc.floor("h"), max(r.end_utc, r.begin_utc).floor("h"), freq="h")
        rows.append(pd.DataFrame({"airport": r.airport, "target_hour_utc": hrs, "event_type": r.event_type}))
    if not rows:
        return pd.DataFrame(columns=["airport", "target_hour_utc", "storm_event_types"])
    h = pd.concat(rows)
    return h.groupby(["airport", "target_hour_utc"])["event_type"].agg(lambda s: ";".join(sorted(set(s)))).rename(
        "storm_event_types").reset_index()
