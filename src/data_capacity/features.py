"""Cutoff-safe hourly weather features per snapshot key.

Key: (airport, asof_utc, target_hour_utc, horizon_hours) with
target_hour_utc = asof_utc + horizon_hours on the hourly UTC grid.

Selection (all strictly as of the cutoff):
* TAF: the latest bulletin (routine or amendment) with available_at_utc <=
  asof_utc and age <= TAF_MAX_AGE_H. A later amendment can never change an
  earlier snapshot because it is not yet available.
* Contract features come from that bulletin's PREVAILING groups (initial/FM/
  BECMG) overlapping [target, target+1h); documented aggregation = worst case
  across overlapping groups (max wind/gust/crosswind/tailwind, min visibility/
  ceiling, any precipitation/thunderstorm).
* TEMPO/PROB groups overlapping the target hour feed separate ``cond_*``
  columns; they never replace prevailing values.
* METAR persistence: latest observation with available_at_utc <= asof_utc and
  age <= METAR_MAX_AGE_H feeds ``obs_*`` columns and ``temperature_c`` (TAFs
  here carry no temperature, so temperature_c is OBSERVED AT CUTOFF).

Wind components use wind.components with the registry runway heading.
Unknown direction (VRB/missing) with nonzero speed -> null crosswind/tailwind;
``crosswind_upper_kt`` gives a bound that treats unknown direction as a full
crosswind.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import HORIZONS, METAR_MAX_AGE_H, TAF_MAX_AGE_H, Airport
from .wind import components

FEATURE_COLUMNS = ["crosswind_kt", "tailwind_kt", "wind_speed_kt", "wind_gust_kt", "visibility_sm",
                   "ceiling_ft_agl", "temperature_c", "precip_flag", "thunderstorm_flag"]

FEATURE_SEMANTICS = {
    "crosswind_kt": "Max |sustained crosswind| (kt) vs fixed runway heading across prevailing TAF groups overlapping the target hour; null if any overlapping group has unknown direction with wind.",
    "tailwind_kt": "Max sustained tailwind magnitude (kt, >=0) vs runway heading; same aggregation/null rule.",
    "wind_speed_kt": "Max prevailing forecast sustained wind (kt).",
    "wind_gust_kt": "Max prevailing forecast gust (kt); equals sustained speed when no gust group is forecast.",
    "visibility_sm": "Min prevailing forecast visibility (statute miles); TAF P6SM is encoded 6.01.",
    "ceiling_ft_agl": "Min prevailing forecast ceiling (lowest BKN/OVC/VV, ft AGL); 30000 = no ceiling layer forecast.",
    "temperature_c": "Latest METAR temperature available at cutoff (deg C) - observed, not forecast for target.",
    "precip_flag": "1 if any prevailing group forecasts precipitation (RA/SN/DZ/PL/GR/GS/IC/UP/SG) at the station.",
    "thunderstorm_flag": "1 if any prevailing group forecasts TS (including VCTS).",
    "crosswind_upper_kt": "Upper bound of crosswind: unknown-direction groups count their full speed.",
    "crosswind_gust_kt": "Max crosswind computed with gust speed.",
    "frozen_precip_flag": "1 if any prevailing group forecasts frozen/freezing precipitation (SN/PL/FZ/IC/GS/SG).",
    "cond_thunderstorm_flag": "1 if a TEMPO/PROB group overlapping the target hour forecasts TS.",
    "cond_frozen_precip_flag": "1 if a TEMPO/PROB group overlapping the target hour forecasts frozen/freezing precipitation.",
    "cond_min_visibility_sm": "Min visibility in overlapping TEMPO/PROB groups (null if none).",
    "cond_min_ceiling_ft_agl": "Min ceiling in overlapping TEMPO/PROB groups that report sky cover.",
    "cond_max_gust_kt": "Max gust/speed in overlapping TEMPO/PROB groups.",
    "cond_max_probability": "Max PROB value (0-1) among overlapping PROB groups; null for TEMPO-only or none.",
    "obs_*": "Latest METAR available at cutoff (persistence), age <= 2 h; obs_age_min gives its age.",
}


def snapshot_grid(ap: Airport, start: str, end: str, horizons=HORIZONS) -> pd.DataFrame:
    """Target hours covering local dates [start, end] for an airport, crossed with horizons."""
    lo = pd.Timestamp(start).tz_localize(ap.timezone).tz_convert("UTC").floor("h")
    hi = (pd.Timestamp(end) + pd.Timedelta(days=1)).tz_localize(ap.timezone).tz_convert("UTC").ceil("h")
    targets = pd.date_range(lo, hi, freq="h", inclusive="left", tz="UTC")
    rows = [pd.DataFrame({"target_hour_utc": targets, "horizon_hours": h}) for h in horizons]
    g = pd.concat(rows, ignore_index=True)
    g["asof_utc"] = g["target_hour_utc"] - pd.to_timedelta(g["horizon_hours"], unit="h")
    g.insert(0, "airport", ap.icao)
    g["airport_iata"] = ap.iata
    return g


def _with_components(df: pd.DataFrame, heading: float) -> pd.DataFrame:
    df = df.copy()
    df["xw"], df["tw"] = components(df["wind_speed_kt"], df["wind_direction_deg"], heading)
    df["xw_gust"], _ = components(df["wind_gust_kt"], df["wind_direction_deg"], heading)
    df["xw_upper"] = df["xw"].where(df["xw"].notna(), df["wind_speed_kt"])
    return df


def build_features(weather: pd.DataFrame, ap: Airport, start: str, end: str, horizons=HORIZONS) -> pd.DataFrame:
    grid = snapshot_grid(ap, start, end, horizons).sort_values("asof_utc").reset_index(drop=True)
    grid["_row"] = np.arange(len(grid))
    w = weather[weather["airport"] == ap.icao]

    # ---- TAF bulletin as of cutoff
    taf = _with_components(w[w["kind"] == "forecast"], ap.runway_heading_deg)
    bulletins = (taf.groupby("bulletin_id", as_index=False)
                 .agg(available_at_utc=("available_at_utc", "max"), issued_at_utc=("issued_at_utc", "max"))
                 .sort_values("available_at_utc"))
    snap = pd.merge_asof(grid, bulletins.rename(columns={"available_at_utc": "taf_available_at_utc",
                                                         "issued_at_utc": "taf_issued_at_utc"}),
                         left_on="asof_utc", right_on="taf_available_at_utc", direction="backward")
    stale = (snap["asof_utc"] - snap["taf_issued_at_utc"]) > pd.Timedelta(hours=TAF_MAX_AGE_H)
    snap.loc[stale, ["bulletin_id", "taf_available_at_utc", "taf_issued_at_utc"]] = pd.NA
    snap = snap.rename(columns={"bulletin_id": "taf_bulletin_id"})

    pairs = snap[["_row", "target_hour_utc", "taf_bulletin_id"]].dropna(subset=["taf_bulletin_id"]).merge(
        taf, left_on="taf_bulletin_id", right_on="bulletin_id")
    overlap = (pairs["valid_from_utc"] < pairs["target_hour_utc"] + pd.Timedelta(hours=1)) & (
        pairs["valid_to_utc"] > pairs["target_hour_utc"])
    pairs = pairs[overlap]
    prevailing = pairs[pairs["condition"].isin(["initial", "FM", "BECMG"])]
    conditional = pairs[pairs["condition"].isin(["TEMPO", "PROB"])]

    def _strict_max(s):  # null if any member unknown
        return np.nan if s.isna().any() else s.max()

    pa = prevailing.groupby("_row").agg(
        crosswind_kt=("xw", _strict_max),
        tailwind_kt=("tw", _strict_max),
        crosswind_upper_kt=("xw_upper", "max"),
        crosswind_gust_kt=("xw_gust", _strict_max),
        wind_speed_kt=("wind_speed_kt", "max"),
        wind_gust_kt=("wind_gust_kt", "max"),
        visibility_sm=("visibility_sm", "min"),
        ceiling_ft_agl=("ceiling_ft_agl", "min"),
        precip_flag=("precip_flag", "max"),
        thunderstorm_flag=("thunderstorm_flag", "max"),
        frozen_precip_flag=("frozen_precip_flag", "max"),
        taf_groups_used=("condition", "size"),
        taf_group_valid_from_utc=("valid_from_utc", "min"),
        taf_group_valid_to_utc=("valid_to_utc", "max"),
    )
    ca = conditional.groupby("_row").agg(
        cond_thunderstorm_flag=("thunderstorm_flag", "max"),
        cond_frozen_precip_flag=("frozen_precip_flag", "max"),
        cond_min_visibility_sm=("visibility_sm", "min"),
        cond_min_ceiling_ft_agl=("ceiling_ft_agl", "min"),
        cond_max_gust_kt=("wind_gust_kt", "max"),
        cond_max_probability=("probability", "max"),
        cond_groups=("condition", "size"),
    )

    # ---- METAR persistence as of cutoff
    obs = _with_components(w[w["kind"] == "observation"], ap.runway_heading_deg).sort_values("available_at_utc")
    obs = obs[["available_at_utc", "issued_at_utc", "bulletin_id", "wind_speed_kt", "wind_gust_kt", "xw", "tw",
               "visibility_sm", "ceiling_ft_agl", "temperature_c", "precip_flag", "thunderstorm_flag",
               "frozen_precip_flag"]].rename(columns={
        "available_at_utc": "metar_available_at_utc", "issued_at_utc": "metar_observed_at_utc",
        "bulletin_id": "metar_bulletin_id", "wind_speed_kt": "obs_wind_speed_kt", "wind_gust_kt": "obs_wind_gust_kt",
        "xw": "obs_crosswind_kt", "tw": "obs_tailwind_kt", "visibility_sm": "obs_visibility_sm",
        "ceiling_ft_agl": "obs_ceiling_ft_agl", "precip_flag": "obs_precip_flag",
        "thunderstorm_flag": "obs_thunderstorm_flag", "frozen_precip_flag": "obs_frozen_precip_flag"})
    snap = pd.merge_asof(snap.sort_values("asof_utc"), obs, left_on="asof_utc", right_on="metar_available_at_utc",
                         direction="backward")
    obs_cols = [c for c in obs.columns]
    old = (snap["asof_utc"] - snap["metar_observed_at_utc"]) > pd.Timedelta(hours=METAR_MAX_AGE_H)
    snap.loc[old, obs_cols] = np.nan
    snap["obs_age_min"] = (snap["asof_utc"] - snap["metar_observed_at_utc"]).dt.total_seconds() / 60

    snap = snap.merge(pa, left_on="_row", right_index=True, how="left").merge(ca, left_on="_row", right_index=True, how="left")
    snap["cond_groups"] = snap["cond_groups"].fillna(0).astype("int64")
    no_cond = snap["taf_bulletin_id"].notna() & (snap["cond_groups"] == 0)
    snap.loc[no_cond, ["cond_thunderstorm_flag", "cond_frozen_precip_flag"]] = 0
    snap["temperature_c"] = snap.pop("temperature_c")

    has_taf = snap["taf_groups_used"].fillna(0) > 0
    has_obs = snap["metar_observed_at_utc"].notna()
    snap["available_at_utc"] = pd.concat(
        [snap["taf_available_at_utc"].where(has_taf), snap["metar_available_at_utc"].where(has_obs)], axis=1).max(axis=1)
    snap["status"] = np.select([has_taf & has_obs, has_taf | has_obs], ["available", "partial"], "unavailable")
    snap["source_id"] = np.select([has_taf & has_obs, has_taf, has_obs], ["iem_taf+iem_metar", "iem_taf", "iem_metar"], None)
    snap["taf_age_h"] = (snap["asof_utc"] - snap["taf_issued_at_utc"]).dt.total_seconds() / 3600
    for c in ["precip_flag", "thunderstorm_flag", "frozen_precip_flag", "cond_thunderstorm_flag",
              "cond_frozen_precip_flag", "obs_precip_flag", "obs_thunderstorm_flag", "obs_frozen_precip_flag"]:
        snap[c] = snap[c].astype("Int8")
    snap["taf_groups_used"] = snap["taf_groups_used"].fillna(0).astype("int64")

    cols = (["airport", "airport_iata", "asof_utc", "target_hour_utc", "horizon_hours"] + FEATURE_COLUMNS +
            ["crosswind_upper_kt", "crosswind_gust_kt", "frozen_precip_flag", "cond_thunderstorm_flag",
             "cond_frozen_precip_flag", "cond_min_visibility_sm",
             "cond_min_ceiling_ft_agl", "cond_max_gust_kt", "cond_max_probability", "cond_groups",
             "obs_wind_speed_kt", "obs_wind_gust_kt", "obs_crosswind_kt", "obs_tailwind_kt", "obs_visibility_sm",
             "obs_ceiling_ft_agl", "obs_precip_flag", "obs_thunderstorm_flag", "obs_frozen_precip_flag", "obs_age_min",
             "available_at_utc", "status", "source_id", "taf_bulletin_id", "taf_issued_at_utc",
             "taf_available_at_utc", "taf_age_h", "taf_groups_used", "taf_group_valid_from_utc",
             "taf_group_valid_to_utc", "metar_bulletin_id", "metar_observed_at_utc", "metar_available_at_utc"])
    out = snap[cols].sort_values(["airport", "asof_utc", "horizon_hours"]).reset_index(drop=True)
    out["taf_bulletin_id"] = out["taf_bulletin_id"].astype("string")
    out["metar_bulletin_id"] = out["metar_bulletin_id"].astype("string")
    return out


def validate_features(f: pd.DataFrame) -> list[str]:
    """Contract checks. Returns a list of violations (empty = valid)."""
    errs = []
    key = ["airport", "asof_utc", "target_hour_utc", "horizon_hours"]
    if f.duplicated(key).any():
        errs.append(f"{int(f.duplicated(key).sum())} duplicate snapshot keys")
    if ((f["target_hour_utc"] - f["asof_utc"]) != pd.to_timedelta(f["horizon_hours"], unit="h")).any():
        errs.append("target_hour_utc != asof_utc + horizon_hours")
    for c in ["asof_utc", "target_hour_utc"]:
        if (f[c] != f[c].dt.floor("h")).any():
            errs.append(f"{c} not on the hourly grid")
    late = f["available_at_utc"].notna() & (f["available_at_utc"] > f["asof_utc"])
    if late.any():
        errs.append(f"{int(late.sum())} rows use inputs available after cutoff")
    for c in ["taf_available_at_utc", "metar_available_at_utc"]:
        bad = f[c].notna() & (f[c] > f["asof_utc"])
        if bad.any():
            errs.append(f"{int(bad.sum())} rows with {c} after cutoff")
    for c in ["crosswind_kt", "tailwind_kt"]:
        if (f[c].dropna() < 0).any():
            errs.append(f"negative {c}")
    for c in ["precip_flag", "thunderstorm_flag"]:
        if not f[c].dropna().isin([0, 1]).all():
            errs.append(f"{c} not 0/1")
    cover = f["taf_group_valid_from_utc"].notna() & ~(
        (f["taf_group_valid_from_utc"] < f["target_hour_utc"] + pd.Timedelta(hours=1)) &
        (f["taf_group_valid_to_utc"] > f["target_hour_utc"]))
    if cover.any():
        errs.append(f"{int(cover.sum())} rows whose TAF validity does not cover the target hour")
    if (f["status"] == "available").any() and f.loc[f["status"] == "available", FEATURE_COLUMNS].isna().all(axis=1).any():
        errs.append("available rows with wholly empty features")
    return errs
