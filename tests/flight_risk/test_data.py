import pandas as pd
import pytest

from src.flight_risk.data import expand_horizons, join_weather, load_flights, local_schedule, prepare_canonical, prepare_sample, temporal_split
from src.flight_risk.metrics import normalized_delay_metrics


def sample_rows():
    return pd.DataFrame({
        "FL_DATE": ["2025-01-05"] * 5, "ORIGIN": ["ATL"] * 5, "DEST": ["DFW"] * 5,
        "OP_UNIQUE_CARRIER": ["DL"] * 5, "OP_CARRIER_FL_NUM": [1, 2, 3, 4, 5],
        "CRS_DEP_TIME": [800, 900, 1000, 1100, 1200], "DEP_DELAY": [45, 46, 90, None, -5],
        "CANCELLED": [0, 0, 1, 0, 0], "CRS_ELAPSED_TIME": [120] * 5, "DISTANCE": [700] * 5,
        "temp_ORIGIN": [999] * 5, "WEATHER_DELAY": [999] * 5,
    })


def test_label_boundary_cancelled_and_normalized_denominator():
    data = prepare_sample(sample_rows())
    assert data.eligible.severe_delay.tolist() == [0, 1, 0]
    assert data.audit["cancelled_with_delay_label_rows"] == 1
    assert data.audit["noncancelled_missing_label_rows"] == 1
    metrics = normalized_delay_metrics(data.all_flights).iloc[0]
    assert metrics.eligible_departures == 3
    assert metrics.severe_delay_rate == pytest.approx(1 / 3)
    assert metrics.delay_minutes_per_flight == pytest.approx(91 / 3)
    assert metrics.cancelled_departures == 1
    assert "temp_ORIGIN" not in data.eligible


def test_duplicate_ids_are_all_excluded():
    raw = sample_rows()
    data = prepare_sample(pd.concat([raw, raw.iloc[[0]]], ignore_index=True))
    assert data.audit["duplicate_key_rows"] == 2
    assert len(data.eligible) == 2


def test_dst_and_2400():
    dates = pd.Series(["2024-03-10", "2024-11-03", "2024-01-01", "2024-01-01"])
    hours = pd.Series([230, 130, 2400, 1260])
    result = local_schedule(dates, hours, "America/New_York")
    assert pd.isna(result.iloc[0]) and pd.isna(result.iloc[1]) and pd.isna(result.iloc[3])
    assert result.iloc[2] == pd.Timestamp("2024-01-02T05:00:00Z")
    extreme = local_schedule(pd.Series(["2024-01-01"] * 3), pd.Series([float("inf"), 10**30, 800.5]), "America/New_York")
    assert extreme.isna().all()


def test_temporal_splits_keep_whole_local_dates():
    dates = pd.Series(["2023-12-31", "2024-01-01", "2024-12-31", "2025-01-01", "2025-07-31", "2025-08-01"])
    assert temporal_split(dates).tolist() == ["train", "validation", "validation", "test", "test", "out_of_scope"]


def test_future_and_duplicated_weather_never_enter_features():
    flights = expand_horizons(prepare_sample(sample_rows()).eligible)
    keys = ["airport", "asof_utc", "target_hour_utc", "horizon_hours"]
    weather = flights[keys].drop_duplicates().copy()
    weather["available_at_utc"] = weather.asof_utc - pd.Timedelta(minutes=1)
    weather["source_id"] = "test"
    weather["status"] = "available"
    weather["crosswind_kt"] = 3.0
    weather.loc[weather.index[0], "available_at_utc"] = weather.loc[weather.index[0], "asof_utc"] + pd.Timedelta(seconds=1)
    duplicated_key = weather.iloc[[1]].copy()
    joined, report = join_weather(flights, pd.concat([weather, duplicated_key], ignore_index=True))
    assert report["invalid_timing_or_source_rows"] == 1
    assert report["duplicate_key_rows"] == 2
    for i in [0, 1]:
        match = (joined[keys] == weather.iloc[i][keys]).all(axis=1)
        assert joined.loc[match, "weather_available"].eq(False).all()
    assert joined.loc[joined.weather_available, "weather_available_at_utc"].le(joined.loc[joined.weather_available, "asof_utc"]).all()


def test_configurable_airport_registry():
    raw = sample_rows().replace({"ORIGIN": {"ATL": "SIN"}})
    data = prepare_sample(raw, {"WSSS": {"iata": "SIN", "timezone": "Asia/Singapore"}})
    assert data.eligible.airport.unique().tolist() == ["WSSS"]
    assert data.eligible.iloc[0].scheduled_dep_utc == pd.Timestamp("2025-01-05T00:00:00Z")


def test_original_2400_flight_date_controls_split_not_predictor_calendar():
    raw = sample_rows().iloc[[0]].copy()
    raw["FL_DATE"], raw["CRS_DEP_TIME"] = "2023-12-31", 2400
    result = prepare_sample(raw).eligible.iloc[0]
    assert result.flight_date == pd.Timestamp("2023-12-31")
    assert result.scheduled_date_local == pd.Timestamp("2024-01-01")
    assert result.split == "train"
    assert result.month == 1


def test_canonical_preserves_original_date_duration_and_rejects_naive_utc():
    raw = pd.DataFrame({"flight_id": ["a", "b"], "origin": ["ATL"] * 2, "dest": ["DFW"] * 2, "carrier": ["DL"] * 2, "scheduled_dep_utc": ["2024-01-01T05:00:00Z", "2024-01-01T06:00:00"], "flight_date_local": ["2023-12-31"] * 2, "scheduled_elapsed_min": [123, 124], "dep_delay_min": [50, 50], "cancelled": [0, 0]})
    result = prepare_canonical(raw)
    assert result.eligible.flight_id.tolist() == ["a"]
    assert result.eligible.iloc[0].scheduled_duration_min == 123
    assert result.eligible.iloc[0].split == "train"
    assert result.audit["invalid_or_naive_utc_rows"] == 1
    assert result.audit["original_flight_date_derived_rows"] == 0


def test_explicit_missing_canonical_file_cannot_silently_use_sample(tmp_path):
    with pytest.raises(FileNotFoundError, match="Explicit canonical"):
        load_flights("not-read.csv", tmp_path / "missing.parquet")


def test_weather_rejects_status_source_grid_naive_timestamps_and_bad_values():
    flights = expand_horizons(prepare_sample(sample_rows()).eligible)
    keys = ["airport", "asof_utc", "target_hour_utc", "horizon_hours"]
    weather = flights[keys].copy().reset_index(drop=True)
    weather["source_id"], weather["status"], weather["crosswind_kt"] = "verified", "available", 3.0
    weather["available_at_utc"] = pd.Series(list(weather.asof_utc), dtype=object)
    weather.loc[0, "status"] = "unavailable"
    weather.loc[1, "source_id"] = " "
    for key in ["asof_utc", "target_hour_utc"]:
        weather.loc[2, key] += pd.Timedelta(minutes=1)
    weather.loc[3, "available_at_utc"] = weather.loc[3, "asof_utc"].tz_localize(None)
    weather.loc[4, "crosswind_kt"] = -1
    weather.loc[5, "precip_flag"] = 2
    weather.loc[6, "wind_speed_kt"] = float("inf")
    weather["ceiling_ft_agl"] = pd.Series([None] * len(weather), dtype=object)
    weather.loc[7, "ceiling_ft_agl"] = "invalid"
    weather.loc[8, "temperature_c"] = 140
    result, audit = join_weather(flights, weather)
    assert not result.weather_available.any()
    assert audit["unavailable_status_rows"] == 1
    assert audit["invalid_or_naive_utc_rows"] == 1
    assert audit["invalid_numeric_rows"] == 5
    assert audit["accepted_feature_rows"] == 0
