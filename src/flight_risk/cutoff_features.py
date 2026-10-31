"""Retrospective replay features: completed gate departures and scheduled demand.

No production feature allowlist is changed by importing this experiment module.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.shared import AIRPORTS

FEATURE_COLUMNS = [
    "recent_departure_count_2h", "recent_severe_delay_share_2h",
    "recent_departure_count_3h", "recent_severe_delay_share_3h",
    "scheduled_arrivals_target_hour", "scheduled_departures_target_hour",
]
FEATURE_ASSUMPTIONS = [
    "Recent departures describe only the supplied canonical event population; a challenge sample produces sample-only counts/rates, not airport-wide state. Traffic-grid coverage does not imply complete departure-event coverage.",
    "Completed gate departures are assumed observable immediately; BTS records do not verify real-time receipt latency.",
    "Recent windows are [cutoff-window, cutoff): an event at the cutoff is not used. Delay means gate departure delay >45 minutes, not wheels-off delay.",
    "Schedules are reconstructed reporting-carrier schedules, assumed known at cutoff; target cancellations/outcomes are never used.",
    "Missing hourly coverage remains unknown. A covered window with no labelled observed departures has count zero and unknown severe-delay share.",
    "Capacity ratios are omitted: the published proxy's selection-end timestamp prevents valid use throughout 2023/2024 training/selection.",
]


def _utc(series, name):
    if not isinstance(series.dtype, pd.DatetimeTZDtype):
        raise ValueError(f"{name} must have an explicit timezone-aware datetime dtype")
    return series.dt.tz_convert("UTC")


def _ns(series):
    return pd.DatetimeIndex(series).as_unit("ns").asi8


def add_cutoff_features(snapshots, full_canonical, traffic, capacity_estimate=None):
    """Add six numerical features without changing inputs or selecting a model.

    Running sums/searchsorted evaluate each unique airport/cutoff once. Coverage
    comes from the published hourly traffic grid, never from future outcomes.
    ``capacity_estimate`` is intentionally unused; see FEATURE_ASSUMPTIONS.
    """
    required = {"airport", "asof_utc", "target_hour_utc"}
    if not required <= set(snapshots) or not snapshots.columns.is_unique:
        raise ValueError("snapshots require unique airport/asof_utc/target_hour_utc columns")
    if not {"flight_id", "origin", "actual_dep_gate_utc", "dep_delay_min", "cancelled"} <= set(full_canonical):
        raise ValueError("canonical completed-departure schema missing")
    if not {"airport", "hour_utc", "direction", "scheduled_count", "coverage"} <= set(traffic):
        raise ValueError("hourly traffic schema missing")
    out = snapshots.copy()
    cutoff = _utc(out.asof_utc, "asof_utc")
    target = _utc(out.target_hour_utc, "target_hour_utc")
    if cutoff.isna().any() or target.isna().any() or (cutoff != cutoff.dt.floor("h")).any():
        raise ValueError("snapshot times must be nonmissing and cutoffs hourly")
    if (target < cutoff).any() or (target != target.dt.floor("h")).any():
        raise ValueError("target hours must be hourly and not precede cutoff")
    events = full_canonical[["flight_id", "origin", "actual_dep_gate_utc", "dep_delay_min", "cancelled"]].copy()
    events["event_utc"] = _utc(events.actual_dep_gate_utc, "actual_dep_gate_utc")
    lookup = {v["iata"]: k for k, v in AIRPORTS.items()} | {k: k for k in AIRPORTS}
    events["airport"] = events.origin.map(lookup)
    delay = pd.to_numeric(events.dep_delay_min, errors="coerce")
    valid = (events.flight_id.notna() & ~events.flight_id.duplicated(keep=False)
             & events.event_utc.notna() & events.cancelled.eq(False).fillna(False)
             & np.isfinite(delay) & events.airport.notna())
    events = events.loc[valid].copy()
    events["severe"] = delay.loc[valid].gt(45).astype("int64")
    tr = traffic[["airport", "hour_utc", "direction", "scheduled_count", "coverage"]].copy()
    tr["hour_utc"] = _utc(tr.hour_utc, "hour_utc")
    if tr.duplicated(["airport", "hour_utc", "direction"]).any():
        raise ValueError("duplicate traffic hour/direction")
    counts = pd.to_numeric(tr.scheduled_count, errors="coerce")
    good_count = np.isfinite(counts) & (counts >= 0) & (counts == np.floor(counts))
    good_count &= ~tr.scheduled_count.map(lambda v: isinstance(v, (bool, np.bool_)))
    tr["scheduled_count"] = counts.where(good_count & tr.coverage.eq("reporting_carriers"))
    for col in FEATURE_COLUMNS:
        out[col] = np.nan
    for airport, positions in out.groupby("airport", sort=False).indices.items():
        ix = np.asarray(positions)
        unique_cutoffs, inverse = np.unique(_ns(cutoff.iloc[ix]), return_inverse=True)
        ev = events[events.airport == airport].sort_values("event_utc")
        event_ns = _ns(ev.event_utc)
        sums = np.r_[0, ev.severe.to_numpy().cumsum()]
        end = np.searchsorted(event_ns, unique_cutoffs, side="left")
        airport_tr = tr[tr.airport == airport]
        dep = airport_tr[airport_tr.direction == "departure"].set_index("hour_utc")
        covered = set(_ns(dep.index.to_series()[dep.scheduled_count.notna()]))
        for window in (2, 3):
            start = np.searchsorted(event_ns, unique_cutoffs - window * 3600_000_000_000, side="left")
            n = (end - start).astype(float)
            severe_n = sums[end] - sums[start]
            has_coverage = np.array([all(t - h * 3600_000_000_000 in covered for h in range(1, window + 1)) for t in unique_cutoffs])
            rate = np.divide(severe_n, n, out=np.full(len(n), np.nan), where=n > 0)
            n[~has_coverage], rate[~has_coverage] = np.nan, np.nan
            out.iloc[ix, out.columns.get_loc(f"recent_departure_count_{window}h")] = n[inverse]
            out.iloc[ix, out.columns.get_loc(f"recent_severe_delay_share_{window}h")] = rate[inverse]
        for direction, name in (("arrival", "scheduled_arrivals_target_hour"), ("departure", "scheduled_departures_target_hour")):
            values = airport_tr[airport_tr.direction == direction].set_index("hour_utc").scheduled_count
            out.iloc[ix, out.columns.get_loc(name)] = target.iloc[ix].map(values).to_numpy()
    out.attrs["cutoff_feature_assumptions"] = list(FEATURE_ASSUMPTIONS)
    out.attrs["recent_departure_population"] = (
        sorted(full_canonical.coverage.dropna().astype(str).unique().tolist())
        if "coverage" in full_canonical else ["unspecified canonical input population"]
    )
    return out
