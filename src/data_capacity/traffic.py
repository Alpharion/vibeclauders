"""Hourly airport movement counts from full BTS months (artifact
``artifacts/capacity/traffic_hourly.parquet``).

Key ``(airport, hour_utc, direction)`` with direction ``arrival``/``departure``.

* ``scheduled_count``: flights whose scheduled gate time (departure at the
  origin, arrival at the destination) falls in the hour, cancelled included.
* ``actual_count``: flights whose reconstructed runway time (wheels-off for
  departures, wheels-on for arrivals) falls in the hour. Cancelled flights and
  diversions (no arrival at the planned destination) do not count.

Population: BTS On-Time Reporting carriers only (``coverage =
'reporting_carriers'``). Not complete airport demand: excludes non-reporting
airlines, cargo, GA, military and most international operations. Schedules are
reconstructed after the fact, not known at a cutoff, so these counts are
retrospective context and are NEVER queue demand or AAR.

Zero means "no reporting-carrier movement in a covered hour". Hours in months
that failed to download are absent, not zero. ``actual_count`` is null in the
hours just before an uncovered period, where flights from the missing month
could have operated early.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Airport
from .flights import build_flights

POPULATION = ("BTS On-Time Reporting Carrier On-Time Performance: domestic scheduled flights of reporting "
              "carriers; excludes non-reporting airlines, cargo, general aviation, military and most international flights")
EARLY_SPILL_H = 2
COLUMNS = ["airport", "hour_utc", "direction", "scheduled_count", "actual_count", "coverage", "population",
           "source_id", "run_id"]


def _covered_hours(ap: Airport, months: list[str]) -> pd.DatetimeIndex:
    hours = []
    for m in sorted(months):
        p = pd.Period(m, freq="M")
        lo = p.start_time.tz_localize(ap.timezone).tz_convert("UTC")
        hi = (p.end_time.normalize() + pd.Timedelta(days=1)).tz_localize(ap.timezone).tz_convert("UTC")
        hours.append(pd.date_range(lo.ceil("h"), hi, freq="h", inclusive="left"))
    return hours[0].append(hours[1:]).unique().sort_values() if hours else pd.DatetimeIndex([], tz="UTC")


def build_traffic(raw: pd.DataFrame, airports: list[Airport], months_ok: list[str], run_id: str,
                  source_id: str) -> tuple[pd.DataFrame, dict]:
    """``raw`` holds BTS rows renamed to challenge-CSV columns (bts.RENAME)."""
    if not months_ok:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in COLUMNS}), {"status": "unavailable", "months": []}
    first = pd.Period(min(months_ok), freq="M").start_time.strftime("%Y-%m-%d")
    last = pd.Period(max(months_ok), freq="M").end_time.strftime("%Y-%m-%d")
    fl, audit = build_flights(raw, airports, first, last)
    cancelled = fl["cancelled"].fillna(True).astype(bool)
    diverted = fl["diverted"].fillna(False).astype(bool)
    frames = []
    for ap in airports:
        grid = _covered_hours(ap, months_ok)
        dep = fl[fl["origin"] == ap.iata]
        arr = fl[fl["dest"] == ap.iata]
        sched = {
            "departure": dep["scheduled_dep_utc"].dt.floor("h").value_counts(),
            "arrival": arr["scheduled_arr_utc"].dt.floor("h").value_counts(),
        }
        actual = {
            "departure": dep.loc[~cancelled[dep.index], "actual_wheels_off_utc"].dropna().dt.floor("h").value_counts(),
            "arrival": arr.loc[~cancelled[arr.index] & ~diverted[arr.index], "actual_wheels_on_utc"].dropna().dt.floor("h").value_counts(),
        }
        # hours right before a gap in coverage (or the end of coverage) may miss early operations
        step = pd.Series(grid[1:] - grid[:-1], index=grid[:-1])
        gap_starts = list(step[step > pd.Timedelta(hours=1)].index) + [grid[-1]]
        uncertain = pd.DatetimeIndex([]).tz_localize("UTC")
        for g in gap_starts:
            uncertain = uncertain.append(pd.date_range(g - pd.Timedelta(hours=EARLY_SPILL_H - 1), g, freq="h"))
        for direction in ("departure", "arrival"):
            d = pd.DataFrame({"hour_utc": grid})
            d["scheduled_count"] = d["hour_utc"].map(sched[direction]).fillna(0).astype("int64")
            act = d["hour_utc"].map(actual[direction]).fillna(0).astype("Int64")
            d["actual_count"] = act.mask(d["hour_utc"].isin(uncertain))
            d.insert(0, "airport", ap.icao)
            d.insert(2, "direction", direction)
            frames.append(d)
    t = pd.concat(frames, ignore_index=True)
    t["coverage"] = "reporting_carriers"
    t["population"] = POPULATION
    t["source_id"] = source_id
    t["run_id"] = run_id
    t = t[COLUMNS].sort_values(["airport", "hour_utc", "direction"]).reset_index(drop=True)
    t["airport"] = t["airport"].astype("string")
    t["direction"] = t["direction"].astype("string")
    summary = {
        "status": "available", "months": sorted(months_ok), "flight_audit": audit,
        "by_airport": {
            a: {d: {"hours": int(len(g2)), "scheduled_total": int(g2["scheduled_count"].sum()),
                    "actual_total": int(g2["actual_count"].sum()),
                    "median_scheduled_per_hour": float(g2["scheduled_count"].median()),
                    "max_scheduled_per_hour": int(g2["scheduled_count"].max())}
                for d, g2 in g.groupby("direction")}
            for a, g in t.groupby("airport")},
        "early_spill_masked_hours": EARLY_SPILL_H,
    }
    return t, summary


def validate_traffic(t: pd.DataFrame) -> list[str]:
    errs = []
    key = ["airport", "hour_utc", "direction"]
    if t.duplicated(key).any():
        errs.append(f"{int(t.duplicated(key).sum())} duplicate keys")
    if not t["direction"].isin(["arrival", "departure"]).all():
        errs.append("unknown direction")
    if (t["scheduled_count"] < 0).any() or (t["actual_count"].dropna() < 0).any():
        errs.append("negative counts")
    if (t["hour_utc"] != t["hour_utc"].dt.floor("h")).any():
        errs.append("hour_utc not on the hourly grid")
    if (t["coverage"] != "reporting_carriers").any():
        errs.append("coverage must be reporting_carriers")
    return errs
