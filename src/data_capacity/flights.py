"""Canonical flights from the supplied BTS-derived sample CSV.

UTC resolution:
* Departure from a registry airport: localise FL_DATE + CRS_DEP_TIME in the
  origin timezone; scheduled arrival UTC = departure UTC + CRS_ELAPSED_TIME
  (BTS computes elapsed time from the UTC difference, so no destination
  timezone is needed).
* Arrival into a registry airport from a non-registry origin: the arrival local
  date is FL_DATE or FL_DATE+1. Each candidate implies an origin UTC offset
  (local CRS_DEP minus arrival UTC minus elapsed). The candidate whose implied
  offset is a whole half-hour within US offsets [-11 h, -3 h] is chosen; zero
  or two matches mark the row ambiguous and it is excluded (counted).
* Local times that do not exist (spring-forward) are excluded; repeated local
  times (fall-back) take the first (DST) occurrence and are flagged.
* CRS time 2400 is midnight at the end of the day and is flagged.

Actual times are retrospective outcomes. Gate times = schedule + reported
delay; runway times = gate +/- taxi minutes. They must never be predictors.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Airport
from .identity import FLIGHT_KEY_IMPL, flight_key

SOURCE_ID = "challenge_csv_bts_sample"

USECOLS = [
    "FL_DATE", "OP_UNIQUE_CARRIER", "OP_CARRIER_FL_NUM", "TAIL_NUM", "ORIGIN", "DEST",
    "CRS_DEP_TIME", "CRS_ARR_TIME", "CRS_ELAPSED_TIME", "DISTANCE",
    "DEP_DELAY", "ARR_DELAY", "TAXI_OUT", "TAXI_IN", "CANCELLED", "CANCELLATION_CODE", "DIVERTED",
    "CARRIER_DELAY", "WEATHER_DELAY", "NAS_DELAY", "SECURITY_DELAY", "LATE_AIRCRAFT_DELAY",
]


def _hhmm_to_minutes(hhmm: pd.Series) -> tuple[pd.Series, pd.Series]:
    v = pd.to_numeric(hhmm, errors="coerce")
    hh, mm = v // 100, v % 100
    valid = v.notna() & (hh >= 0) & (hh <= 24) & (mm >= 0) & (mm < 60) & ~((hh == 24) & (mm > 0))
    mins = (hh * 60 + mm).where(valid)
    return mins, v == 2400


def _localize(naive: pd.Series, tz: str) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (utc, ambiguous_flag, nonexistent_flag)."""
    strict = naive.dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT")
    first = naive.dt.tz_localize(tz, ambiguous=np.ones(len(naive), dtype=bool), nonexistent="NaT")
    nonexistent = naive.notna() & first.isna()
    ambiguous = naive.notna() & strict.isna() & first.notna()
    return first.dt.tz_convert("UTC"), ambiguous, nonexistent


def load_raw(csv_path) -> pd.DataFrame:
    return pd.read_csv(csv_path, usecols=USECOLS, low_memory=False, dtype={"CANCELLATION_CODE": "string", "TAIL_NUM": "string"})


def build_flights(raw: pd.DataFrame, airports: list[Airport], start: str, end: str) -> tuple[pd.DataFrame, dict]:
    audit: dict = {"input_rows": int(len(raw)), "flight_key_impl": FLIGHT_KEY_IMPL}
    df = raw.copy()
    df["flight_date_local"] = pd.to_datetime(df["FL_DATE"], errors="coerce")
    in_range = df["flight_date_local"].between(pd.Timestamp(start), pd.Timestamp(end))
    audit["excluded_out_of_date_range"] = int((~in_range).sum())
    df = df[in_range]

    by_iata = {a.iata: a for a in airports}
    touches = df["ORIGIN"].isin(by_iata) | df["DEST"].isin(by_iata)
    audit["excluded_no_selected_airport"] = int((~touches).sum())
    df = df[touches].copy()
    audit["rows_touching_selected_airports"] = int(len(df))

    dep_min, dep2400 = _hhmm_to_minutes(df["CRS_DEP_TIME"])
    arr_min, arr2400 = _hhmm_to_minutes(df["CRS_ARR_TIME"])
    elapsed = pd.to_numeric(df["CRS_ELAPSED_TIME"], errors="coerce")
    df["local_time_flag"] = pd.Series(pd.NA, index=df.index, dtype="string")
    df.loc[dep2400 | arr2400, "local_time_flag"] = "crs_2400"

    dep_naive = df["flight_date_local"] + pd.to_timedelta(dep_min, unit="min")
    dep_utc = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    arr_utc = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
    ambiguous_rows = pd.Series(False, index=df.index)
    nonexistent_rows = pd.Series(False, index=df.index)
    unresolved_arr = pd.Series(False, index=df.index)

    # 1) origin in registry
    for iata, ap in by_iata.items():
        m = df["ORIGIN"] == iata
        if not m.any():
            continue
        utc, amb, nonex = _localize(dep_naive[m], ap.timezone)
        dep_utc[m] = utc
        ambiguous_rows[m] = amb
        nonexistent_rows[m] = nonex
    m_orig = df["ORIGIN"].isin(by_iata)
    arr_utc[m_orig] = dep_utc[m_orig] + pd.to_timedelta(elapsed[m_orig], unit="min")

    # 2) origin outside registry, destination inside
    for iata, ap in by_iata.items():
        m = (df["DEST"] == iata) & ~m_orig
        if not m.any():
            continue
        cands = []
        for day in (0, 1):
            naive = df.loc[m, "flight_date_local"] + pd.Timedelta(days=day) + pd.to_timedelta(arr_min[m], unit="min")
            utc, amb, nonex = _localize(naive, ap.timezone)
            implied_dep_utc = utc - pd.to_timedelta(elapsed[m], unit="min")
            offset_min = (dep_naive[m] - implied_dep_utc.dt.tz_localize(None)).dt.total_seconds() / 60
            ok = offset_min.between(-11 * 60, -3 * 60) & ((offset_min % 30) == 0)
            cands.append((utc, implied_dep_utc, amb, nonex, ok.fillna(False)))
        (u0, d0, a0, n0, ok0), (u1, d1, a1, n1, ok1) = cands
        pick0, pick1 = ok0 & ~ok1, ok1 & ~ok0
        arr_utc[m] = u0.where(pick0, u1.where(pick1))
        dep_utc[m] = d0.where(pick0, d1.where(pick1))
        ambiguous_rows[m] = (a0 & pick0) | (a1 & pick1)
        nonexistent_rows[m] = (n0 & pick0) | (n1 & pick1)
        unresolved_arr[m] = ~(pick0 | pick1)

    df.loc[ambiguous_rows, "local_time_flag"] = "dst_ambiguous_first_occurrence"
    df["scheduled_dep_utc"] = dep_utc
    df["scheduled_arr_utc"] = arr_utc

    invalid = dep_min.isna() | elapsed.isna() | (elapsed <= 0) | pd.to_numeric(df["OP_CARRIER_FL_NUM"], errors="coerce").isna()
    audit["excluded_invalid_schedule_fields"] = int(invalid.sum())
    audit["excluded_nonexistent_local_time"] = int((nonexistent_rows & ~invalid).sum())
    audit["excluded_unresolved_arrival_date"] = int((unresolved_arr & ~invalid & ~nonexistent_rows).sum())
    audit["flagged_dst_ambiguous"] = int(ambiguous_rows.sum())
    audit["flagged_crs_2400"] = int((dep2400 | arr2400).sum())
    keep = ~invalid & dep_utc.notna() & arr_utc.notna()
    df = df[keep].copy()

    df["flight_number"] = pd.to_numeric(df["OP_CARRIER_FL_NUM"]).astype("int64")
    df["scheduled_dep_local_hhmm"] = pd.to_numeric(df["CRS_DEP_TIME"]).astype("int64")
    df["flight_id"] = [
        flight_key(d.date().isoformat(), c, n, o, de, h)
        for d, c, n, o, de, h in zip(
            df["flight_date_local"], df["OP_UNIQUE_CARRIER"], df["flight_number"],
            df["ORIGIN"], df["DEST"], df["scheduled_dep_local_hhmm"],
        )
    ]

    # duplicates: identical rows collapse; conflicting copies are all excluded
    exact = df.duplicated(keep="first")
    audit["collapsed_exact_duplicates"] = int(exact.sum())
    df = df[~exact]
    conflict = df["flight_id"].duplicated(keep=False)
    audit["excluded_conflicting_duplicate_keys"] = int(conflict.sum())
    df = df[~conflict]

    cancelled = pd.to_numeric(df["CANCELLED"], errors="coerce")
    diverted = pd.to_numeric(df["DIVERTED"], errors="coerce")
    dep_delay = pd.to_numeric(df["DEP_DELAY"], errors="coerce")
    arr_delay = pd.to_numeric(df["ARR_DELAY"], errors="coerce")
    actual_dep = df["scheduled_dep_utc"] + pd.to_timedelta(dep_delay, unit="min")
    actual_arr = df["scheduled_arr_utc"] + pd.to_timedelta(arr_delay, unit="min")

    out = pd.DataFrame({
        "flight_id": df["flight_id"].astype("string"),
        "origin": df["ORIGIN"].astype("string"),
        "dest": df["DEST"].astype("string"),
        "carrier": df["OP_UNIQUE_CARRIER"].astype("string"),
        "flight_number": df["flight_number"],
        "tail_number": df["TAIL_NUM"],
        "flight_date_local": df["flight_date_local"].dt.date,
        "scheduled_dep_local_hhmm": df["scheduled_dep_local_hhmm"],
        "scheduled_arr_local_hhmm": pd.to_numeric(df["CRS_ARR_TIME"]).astype("int64"),
        "scheduled_dep_utc": df["scheduled_dep_utc"],
        "scheduled_arr_utc": df["scheduled_arr_utc"],
        "scheduled_elapsed_min": pd.to_numeric(df["CRS_ELAPSED_TIME"]),
        "distance_miles": pd.to_numeric(df["DISTANCE"], errors="coerce"),
        "dep_delay_min": dep_delay,
        "arr_delay_min": arr_delay,
        "cancelled": cancelled.map({1.0: True, 0.0: False}).astype("boolean"),
        "cancellation_code": df["CANCELLATION_CODE"],
        "diverted": diverted.map({1.0: True, 0.0: False}).astype("boolean"),
        # retrospective outcomes (never predictors)
        "actual_dep_gate_utc": actual_dep,
        "actual_arr_gate_utc": actual_arr,
        "actual_wheels_off_utc": actual_dep + pd.to_timedelta(pd.to_numeric(df["TAXI_OUT"], errors="coerce"), unit="min"),
        "actual_wheels_on_utc": actual_arr - pd.to_timedelta(pd.to_numeric(df["TAXI_IN"], errors="coerce"), unit="min"),
        "taxi_out_min": pd.to_numeric(df["TAXI_OUT"], errors="coerce"),
        "taxi_in_min": pd.to_numeric(df["TAXI_IN"], errors="coerce"),
        "cause_carrier_delay_min": pd.to_numeric(df["CARRIER_DELAY"], errors="coerce"),
        "cause_weather_delay_min": pd.to_numeric(df["WEATHER_DELAY"], errors="coerce"),
        "cause_nas_delay_min": pd.to_numeric(df["NAS_DELAY"], errors="coerce"),
        "cause_security_delay_min": pd.to_numeric(df["SECURITY_DELAY"], errors="coerce"),
        "cause_late_aircraft_delay_min": pd.to_numeric(df["LATE_AIRCRAFT_DELAY"], errors="coerce"),
        "local_time_flag": df["local_time_flag"],
        "coverage": "sample",
        "source_id": SOURCE_ID,
    }).sort_values(["scheduled_dep_utc", "flight_id"], kind="stable").reset_index(drop=True)

    audit["published_rows"] = int(len(out))
    audit["unknown_cancellation_status"] = int(out["cancelled"].isna().sum())
    audit["missing_dep_delay_noncancelled"] = int((out["dep_delay_min"].isna() & (out["cancelled"] == False)).sum())  # noqa: E712
    cov = {}
    for ap in airports:
        dep = out[out["origin"] == ap.iata]
        arr = out[out["dest"] == ap.iata]
        cov[ap.iata] = {
            "departures": int(len(dep)),
            "arrivals": int(len(arr)),
            "departures_by_year": {str(k): int(v) for k, v in dep.groupby(pd.to_datetime(dep["flight_date_local"]).dt.year).size().items()},
            "arrivals_by_year": {str(k): int(v) for k, v in arr.groupby(pd.to_datetime(arr["flight_date_local"]).dt.year).size().items()},
        }
    audit["coverage_by_airport"] = cov
    audit["coverage_note"] = "Sampled flights; not complete airport demand. Movements: a flight between two selected airports counts once per airport."
    return out, audit
