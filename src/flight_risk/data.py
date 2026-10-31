"""Conservative flight preparation and cutoff-safe feature joins.

Outcome columns remain available for evaluation, but model.py selects an explicit
schedule/weather allowlist. Supplied weather observations are never predictors.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.shared import AIRPORTS, flight_key

HORIZONS = (3, 6, 12)
WEATHER_KEYS = ["airport", "asof_utc", "target_hour_utc", "horizon_hours"]
WEATHER_FEATURES = [
    "crosswind_kt", "tailwind_kt", "wind_speed_kt", "wind_gust_kt",
    "visibility_sm", "ceiling_ft_agl", "temperature_c", "precip_flag", "thunderstorm_flag",
]


@dataclass
class FlightData:
    eligible: pd.DataFrame
    all_flights: pd.DataFrame
    audit: dict


def aware_utc(values):
    """Reject absent timezone evidence; never interpret naive UTC-labelled data."""
    def parse(value):
        if pd.isna(value):
            return pd.NaT
        try:
            parsed = pd.Timestamp(value)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                return pd.NaT
            return parsed.tz_convert("UTC")
        except (ValueError, TypeError, OverflowError):
            return pd.NaT
    return pd.Series([parse(value) for value in values], index=values.index, dtype="datetime64[ns, UTC]")


def local_schedule(dates, hhmm, timezone):
    """BTS local HHMM, including 2400; ambiguous DST times are unknown."""
    numbers = pd.to_numeric(hhmm, errors="coerce").replace([np.inf, -np.inf], np.nan)
    hours, minutes = numbers // 100, numbers % 100
    valid = numbers.eq(numbers.round()) & (
        (hours.between(0, 23) & minutes.between(0, 59)) | numbers.eq(2400)
    )
    naive = pd.to_datetime(dates, errors="coerce") + pd.to_timedelta(hours.where(valid), unit="h") + pd.to_timedelta(minutes.where(valid), unit="m")
    return naive.where(valid).dt.tz_localize(timezone, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")


def _registry(registry=None):
    result = registry or AIRPORTS
    for icao, row in result.items():
        if not row.get("iata") or not row.get("timezone"):
            raise ValueError(f"Airport {icao} requires iata and timezone")
    return result


def _schedule_features(frame, registry):
    out = frame.copy()
    original_utc = out.scheduled_dep_utc
    out["scheduled_dep_utc"] = aware_utc(original_utc)
    out["invalid_or_naive_utc"] = original_utc.notna() & out.scheduled_dep_utc.isna()
    out["scheduled_date_local"] = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns]")
    out["local_hour"] = np.nan
    for icao, config in registry.items():
        mask = out.airport.eq(icao)
        local = out.loc[mask, "scheduled_dep_utc"].dt.tz_convert(config["timezone"])
        out.loc[mask, "scheduled_date_local"] = local.dt.tz_localize(None).dt.normalize()
        out.loc[mask, "local_hour"] = local.dt.hour + local.dt.minute / 60
    if "flight_date_local" in out:
        out["flight_date"] = pd.to_datetime(out.flight_date_local, errors="coerce").dt.normalize()
        out["original_date_derived"] = False
    else:
        out["flight_date"] = out.scheduled_date_local
        out["original_date_derived"] = True
    out["month"] = out.scheduled_date_local.dt.month
    out["day_of_week"] = out.scheduled_date_local.dt.dayofweek
    out["target_hour_utc"] = out.scheduled_dep_utc.dt.floor("h")
    for col in ["scheduled_duration_min", "distance_miles", "dep_delay_min", "cancelled"]:
        if col not in out:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
    for col in ["carrier", "dest"]:
        out[col] = out[col].astype("string").fillna("UNKNOWN").astype(str)
    return out


def prepare_sample(raw, airport_registry=None):
    registry = _registry(airport_registry)
    required = {"FL_DATE", "ORIGIN", "DEST", "OP_UNIQUE_CARRIER", "OP_CARRIER_FL_NUM", "CRS_DEP_TIME", "DEP_DELAY", "CANCELLED"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Sample missing columns: {sorted(missing)}")
    iata_to_icao = {v["iata"]: k for k, v in registry.items()}
    subset = raw[raw.ORIGIN.isin(iata_to_icao)].copy()
    out = pd.DataFrame(index=subset.index)
    out["origin"], out["dest"] = subset.ORIGIN, subset.DEST
    out["airport"] = subset.ORIGIN.map(iata_to_icao)
    out["carrier"] = subset.OP_UNIQUE_CARRIER
    out["flight_number"] = subset.OP_CARRIER_FL_NUM
    out["flight_date_local"] = subset.FL_DATE
    out["scheduled_dep_utc"] = pd.Series(pd.NaT, index=subset.index, dtype="datetime64[ns, UTC]")
    for icao, config in registry.items():
        mask = out.airport.eq(icao)
        out.loc[mask, "scheduled_dep_utc"] = local_schedule(subset.loc[mask, "FL_DATE"], subset.loc[mask, "CRS_DEP_TIME"], config["timezone"])
    out["flight_id"] = None
    valid = out.scheduled_dep_utc.notna() & subset.OP_CARRIER_FL_NUM.notna() & subset.OP_UNIQUE_CARRIER.notna()
    out.loc[valid, "flight_id"] = [
        flight_key(*row) for row in subset.loc[valid, ["FL_DATE", "OP_UNIQUE_CARRIER", "OP_CARRIER_FL_NUM", "ORIGIN", "DEST", "CRS_DEP_TIME"]].itertuples(index=False, name=None)
    ]
    out["dep_delay_min"] = subset.DEP_DELAY
    out["cancelled"] = subset.CANCELLED
    out["scheduled_duration_min"] = subset.get("CRS_ELAPSED_TIME", np.nan)
    out["distance_miles"] = subset.get("DISTANCE", np.nan)
    out["coverage"] = "sample"
    out["source_id"] = "challenge-flight-sample"
    return _finalize(_schedule_features(out, registry), int(len(raw)), "challenge-flight-sample")


def prepare_canonical(raw, airport_registry=None):
    registry = _registry(airport_registry)
    required = {"flight_id", "origin", "dest", "carrier", "scheduled_dep_utc", "dep_delay_min", "cancelled"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Canonical flights missing columns: {sorted(missing)}")
    lookup = {v["iata"]: k for k, v in registry.items()} | {k: k for k in registry}
    out = raw[raw.origin.isin(lookup)].copy()
    out["airport"] = out.origin.map(lookup)
    if "coverage" not in out:
        out["coverage"] = "unknown"
    if "source_id" not in out:
        out["source_id"] = "canonical-flights"
    if "scheduled_elapsed_min" in out:
        if "scheduled_duration_min" not in out:
            out["scheduled_duration_min"] = out.scheduled_elapsed_min
        else:
            out["scheduled_duration_min"] = out.scheduled_duration_min.combine_first(out.scheduled_elapsed_min)
    return _finalize(_schedule_features(out, registry), int(len(raw)), "canonical-flights")


def _finalize(out, input_rows, source):
    invalid_time = out.scheduled_dep_utc.isna() | out.flight_id.isna() | out.flight_date.isna()
    duplicated = out.flight_id.notna() & out.flight_id.duplicated(keep=False)
    # Remove every ambiguous duplicate rather than silently selecting an outcome.
    clean = out[~invalid_time & ~duplicated].copy()
    labelled = clean.cancelled.eq(0) & clean.dep_delay_min.notna()
    eligible = clean[labelled].copy()
    eligible["severe_delay"] = eligible.dep_delay_min.gt(45).astype(int)
    eligible["split"] = temporal_split(eligible.flight_date)
    clean["split"] = temporal_split(clean.flight_date)
    audit = {
        "source_id": source, "input_rows": input_rows, "target_departures": int(len(out)),
        "invalid_schedule_or_key_rows": int(invalid_time.sum()), "duplicate_key_rows": int(duplicated.sum()),
        "invalid_or_naive_utc_rows": int(out.invalid_or_naive_utc.sum()),
        "original_flight_date_derived_rows": int(out.original_date_derived.sum()),
        "unique_valid_schedule_rows": int(len(clean)), "cancelled_rows": int(clean.cancelled.eq(1).sum()),
        "unknown_cancellation_rows": int((~clean.cancelled.isin([0, 1])).sum()),
        "noncancelled_missing_label_rows": int((clean.cancelled.eq(0) & clean.dep_delay_min.isna()).sum()),
        "cancelled_with_delay_label_rows": int((clean.cancelled.eq(1) & clean.dep_delay_min.notna()).sum()),
        "eligible_labelled_rows": int(len(eligible)),
        "split_rows": {str(k): int(v) for k, v in eligible.groupby("split").size().items()},
        "label_rule": "cancelled == 0 and DEP_DELAY is known; severe iff DEP_DELAY > 45",
        "schedule_assumption": "Reconstructed historical schedule, not an archived schedule snapshot; publication/revision timing is unverified.",
    }
    return FlightData(eligible.reset_index(drop=True), clean.reset_index(drop=True), audit)


def temporal_split(dates):
    dates = pd.to_datetime(dates, errors="coerce")
    result = pd.Series("out_of_scope", index=dates.index, dtype="str")
    for name, start, end in [
        ("train", "2023-01-01", "2024-01-01"),
        ("validation", "2024-01-01", "2025-01-01"),
        ("test", "2025-01-01", "2025-08-01"),
    ]:
        result.loc[dates.ge(pd.Timestamp(start)) & dates.lt(pd.Timestamp(end))] = name
    return result


def load_flights(sample_path, canonical_path=None, airport_registry=None):
    if canonical_path is not None:
        canonical_path = Path(canonical_path)
        if not canonical_path.exists():
            raise FileNotFoundError(f"Explicit canonical flights path does not exist: {canonical_path}")
        return prepare_canonical(pd.read_parquet(canonical_path), airport_registry)
    columns = ["FL_DATE", "ORIGIN", "DEST", "OP_UNIQUE_CARRIER", "OP_CARRIER_FL_NUM", "CRS_DEP_TIME", "DEP_DELAY", "CANCELLED", "CRS_ELAPSED_TIME", "DISTANCE"]
    raw = pd.read_csv(sample_path, usecols=lambda name: name in columns)
    return prepare_sample(raw, airport_registry)


def expand_horizons(flights):
    frames = []
    for horizon in HORIZONS:
        frame = flights.copy()
        frame["horizon_hours"] = horizon
        frame["asof_utc"] = frame.target_hour_utc - pd.Timedelta(hours=horizon)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def join_weather(flights, weather):
    required = set(WEATHER_KEYS + ["available_at_utc", "source_id", "status"])
    if missing := required - set(weather.columns):
        raise ValueError(f"Weather features missing columns: {sorted(missing)}")
    weather = weather.copy()
    invalid_timezone = pd.Series(False, index=weather.index)
    for name in ["asof_utc", "target_hour_utc", "available_at_utc"]:
        original = weather[name]
        weather[name] = aware_utc(original)
        invalid_timezone |= original.notna() & weather[name].isna()
    weather["horizon_hours"] = pd.to_numeric(weather.horizon_hours, errors="coerce").replace([np.inf, -np.inf], np.nan)
    duplicate = weather.duplicated(WEATHER_KEYS, keep=False)
    timing = (
        weather.available_at_utc.notna() & weather.asof_utc.notna() & weather.target_hour_utc.notna()
        & weather.available_at_utc.le(weather.asof_utc)
        & weather.asof_utc.eq(weather.asof_utc.dt.floor("h"))
        & weather.target_hour_utc.eq(weather.target_hour_utc.dt.floor("h"))
        & (weather.target_hour_utc - weather.asof_utc).eq(pd.to_timedelta(weather.horizon_hours.where(weather.horizon_hours.isin(HORIZONS)), unit="h"))
        & weather.horizon_hours.isin(HORIZONS)
        & weather.source_id.fillna("").astype(str).str.strip().ne("")
        & weather.airport.fillna("").astype(str).str.strip().ne("")
    )
    numeric_valid = pd.Series(True, index=weather.index)
    ranges = {
        "crosswind_kt": (0, 300), "tailwind_kt": (0, 300), "wind_speed_kt": (0, 300),
        "wind_gust_kt": (0, 300), "visibility_sm": (0, 300), "ceiling_ft_agl": (0, 100000),
        "temperature_c": (-100, 70),
    }
    for feature in WEATHER_FEATURES:
        original = weather[feature] if feature in weather else pd.Series(np.nan, index=weather.index)
        values = pd.to_numeric(original, errors="coerce")
        numeric_valid &= original.isna() | (values.notna() & np.isfinite(values))
        if feature in ranges:
            low, high = ranges[feature]
            numeric_valid &= values.isna() | values.between(low, high)
        else:
            numeric_valid &= values.isna() | values.isin([0, 1])
        weather[feature] = values.replace([np.inf, -np.inf], np.nan)
    usable_values = weather[WEATHER_FEATURES].notna().any(axis=1)
    available = weather.status.eq("available")
    accepted = weather.loc[~duplicate & timing & usable_values & available & numeric_valid, WEATHER_KEYS + ["available_at_utc", "source_id"] + WEATHER_FEATURES]
    accepted = accepted.rename(columns={"source_id": "weather_source_id", "available_at_utc": "weather_available_at_utc"})
    joined = flights.merge(accepted, on=WEATHER_KEYS, how="left", validate="many_to_one")
    joined["weather_available"] = joined.weather_source_id.notna()
    return joined, {
        "input_feature_rows": int(len(weather)), "duplicate_key_rows": int(duplicate.sum()),
        "invalid_timing_or_source_rows": int((~timing).sum()), "no_weather_value_rows": int((~usable_values).sum()),
        "invalid_or_naive_utc_rows": int(invalid_timezone.sum()), "unavailable_status_rows": int((~available).sum()),
        "invalid_numeric_rows": int((~numeric_valid).sum()),
        "accepted_feature_rows": int(len(accepted)), "matched_flight_horizon_rows": int(joined.weather_available.sum()),
    }
