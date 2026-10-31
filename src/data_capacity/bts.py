"""Automatic BTS On-Time Reporting ingestion (monthly PREZIP archives).

Downloads ``On_Time_Reporting_Carrier_On_Time_Performance_1987_present_<Y>_<M>.zip``,
keeps flights touching the selected airports and renames columns to the
challenge-CSV names so ``flights.build_flights`` can consume either source.
BTS covers reporting carriers only: it is not complete airport demand, and its
schedules are reconstructed after the fact, not as-of-cutoff snapshots.
"""
from __future__ import annotations

import zipfile
from io import BytesIO

import pandas as pd

from .config import PUBLIC_DIR, Airport
from .io import DownloadError, fetch_cached, read_json, sha256_file, write_json, write_parquet

PREZIP = "https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{y}_{m}.zip"
RENAME = {
    "FlightDate": "FL_DATE", "Reporting_Airline": "OP_UNIQUE_CARRIER",
    "Flight_Number_Reporting_Airline": "OP_CARRIER_FL_NUM", "Tail_Number": "TAIL_NUM", "Origin": "ORIGIN",
    "Dest": "DEST", "CRSDepTime": "CRS_DEP_TIME", "CRSArrTime": "CRS_ARR_TIME", "CRSElapsedTime": "CRS_ELAPSED_TIME",
    "Distance": "DISTANCE", "DepDelay": "DEP_DELAY", "ArrDelay": "ARR_DELAY", "TaxiOut": "TAXI_OUT",
    "TaxiIn": "TAXI_IN", "Cancelled": "CANCELLED", "CancellationCode": "CANCELLATION_CODE", "Diverted": "DIVERTED",
    "CarrierDelay": "CARRIER_DELAY", "WeatherDelay": "WEATHER_DELAY", "NASDelay": "NAS_DELAY",
    "SecurityDelay": "SECURITY_DELAY", "LateAircraftDelay": "LATE_AIRCRAFT_DELAY",
}
SOURCE_ID = "bts_ontime_prezip"


def _validate_zip(body: bytes) -> None:
    try:
        z = zipfile.ZipFile(BytesIO(body))
    except zipfile.BadZipFile as exc:
        raise DownloadError(f"not a zip archive: {exc}") from exc
    names = [n for n in z.namelist() if n.lower().endswith(".csv")]
    if not names:
        raise DownloadError("zip contains no CSV")
    head = z.open(names[0]).readline().decode("utf-8", errors="replace")
    missing = [c for c in ("FlightDate", "Reporting_Airline", "CRSDepTime") if c not in head]
    if missing:
        raise DownloadError(f"BTS header missing {missing}")
    bad = z.testzip()
    if bad:
        raise DownloadError(f"corrupt member {bad}")


def months(start: str, end: str):
    for p in pd.period_range(pd.Timestamp(start), pd.Timestamp(end), freq="M"):
        yield p.year, p.month


def acquire_month(y: int, m: int, airports: list[Airport], *, cache_only=False, refresh=False) -> dict:
    url = PREZIP.format(y=y, m=m)
    zpath = PUBLIC_DIR / "bts" / f"ontime_{y}_{m:02d}.zip"
    rec = fetch_cached(url, zpath, validate=_validate_zip, cache_only=cache_only, refresh=refresh)
    rec = {**rec, "source_id": SOURCE_ID, "month": f"{y}-{m:02d}"}
    if rec["status"] == "failed":
        return rec
    iatas = {a.iata for a in airports}
    out = PUBLIC_DIR / "bts" / "filtered" / f"ontime_{'_'.join(sorted(iatas))}_{y}_{m:02d}.parquet"
    side = out.with_name(out.name + ".meta.json")
    zip_hash = rec.get("sha256") or sha256_file(zpath)
    prev = read_json(side)
    # reuse the filtered extract only if it was cut from this exact archive
    if out.exists() and prev and prev.get("zip_sha256") == zip_hash and prev.get("sha256") == sha256_file(out):
        return {**rec, "filtered_path": out, "filtered_rows": prev["rows"]}
    z = zipfile.ZipFile(zpath)
    name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    df = pd.read_csv(z.open(name), usecols=list(RENAME), low_memory=False,
                     dtype={"CancellationCode": "string", "Tail_Number": "string"}).rename(columns=RENAME)
    df = df[df["ORIGIN"].isin(iatas) | df["DEST"].isin(iatas)]
    write_parquet(out, df)
    write_json(side, {"zip_sha256": zip_hash, "sha256": sha256_file(out), "rows": int(len(df)),
                      "airports": sorted(iatas)})
    return {**rec, "filtered_path": out, "filtered_rows": int(len(df))}


def load_filtered(paths) -> pd.DataFrame:
    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)


def acquire_months(months_ym: list[str], airports: list[Airport], *, cache_only=False, refresh=False,
                   workers: int = 4, log=None) -> list[dict]:
    """Acquire several months concurrently. BTS throttles each connection, so a
    few parallel downloads finish far sooner than a sequential loop. Results
    keep the requested month order; a failed month never aborts the others."""
    from concurrent.futures import ThreadPoolExecutor

    def one(ym: str) -> dict:
        y, m = map(int, ym.split("-"))
        try:
            r = acquire_month(y, m, airports, cache_only=cache_only, refresh=refresh)
        except Exception as exc:  # corrupt cache, parse failure, ...
            r = {"url": PREZIP.format(y=y, m=m), "path": None, "status": "failed", "source_id": SOURCE_ID,
                 "month": ym, "error": f"{type(exc).__name__}: {exc}"}
        if log:
            log(f"bts {ym}: {r['status']} {r.get('filtered_rows') or r.get('error') or ''}")
        return r

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(one, months_ym))
