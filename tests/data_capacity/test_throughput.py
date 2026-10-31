"""Observed-arrivals forecast (NOT AAR). Model tests use SYNTHETIC data only."""
import json

import numpy as np
import pandas as pd
import pytest

from src.data_capacity import capacity, throughput
from src.data_capacity.config import CAPACITY_DIR, resolve_airports
from src.data_capacity.features import FEATURE_COLUMNS

AIRPORTS = resolve_airports(["KATL", "KDFW"])


def synthetic(seed=0):
    """Arrivals follow the schedule, minus a large cut in forecast storm hours."""
    rng = np.random.default_rng(seed)
    hours = pd.date_range("2023-01-01 06:00", "2025-07-31 23:00", freq="5h", tz="UTC")
    feats, traffic = [], []
    for ap in AIRPORTS:
        storm = rng.random(len(hours)) < 0.15
        sched = rng.integers(10, 80, len(hours))
        for h in (3, 6, 12):
            f = pd.DataFrame({"airport": ap.icao, "target_hour_utc": hours, "horizon_hours": h})
            f["asof_utc"] = f.target_hour_utc - pd.to_timedelta(h, unit="h")
            for c in FEATURE_COLUMNS + capacity.EXTRA_FEATURES:
                f[c] = rng.uniform(0, 10, len(f))
            f["thunderstorm_flag"] = storm.astype(int)
            f["frozen_precip_flag"] = 0
            f["ceiling_ft_agl"], f["visibility_sm"] = 5000.0, 6.0
            f["status"], f["source_id"], f["taf_bulletin_id"] = "available", "synthetic", "synthetic"
            f["available_at_utc"] = f.asof_utc
            feats.append(f)
        actual = np.round(sched * np.where(storm, 0.4, 0.97) + rng.normal(0, 1.5, len(hours))).clip(0)
        for direction, s, a in (("arrival", sched, actual), ("departure", sched, sched)):
            traffic.append(pd.DataFrame({"airport": ap.icao, "hour_utc": hours, "direction": direction,
                                         "scheduled_count": s, "actual_count": pd.array(a, dtype="Int64")}))
    return pd.concat(feats, ignore_index=True), pd.concat(traffic, ignore_index=True)


@pytest.fixture(scope="module")
def result():
    f, t = synthetic()
    return (f, t) + throughput.fit_evaluate(f, t, AIRPORTS, "test-run")


def test_label_is_never_aar(result):
    _, _, fc, rep = result
    assert set(fc.label_kind) == {"observed_reporting_carrier_arrivals"}
    assert not any(c.startswith("aar") for c in fc.columns)
    assert "NOT the facility Airport Arrival Rate" in rep["not_aar"]
    assert rep["team_agreement"]["status"] == "agreed"


def test_contract_split_and_cutoff_rules(result):
    _, _, fc, rep = result
    assert set(fc.coverage) == {"held_out_test"}
    assert (fc.asof_utc >= fc.model_selection_end_utc).all()
    assert (fc.features_available_at_utc <= fc.asof_utc).all()
    assert {(m["airport"], m["horizon_hours"]) for m in rep["metrics"]} == {(a.icao, h) for a in AIRPORTS for h in (3, 6, 12)}


def test_weather_signal_is_measured_against_schedule_only(result):
    _, _, _, rep = result
    impacted = rep["weather_value"]["weather_impacted_hours"]["weather_minus_schedule_only"]
    assert impacted["ci95"][1] < 0  # storm cut is only visible to the weather model
    storm = next(c for c in rep["cohorts"] if c["cohort"] == "thunderstorm_forecast")
    assert storm["rmse_weather"] < storm["rmse_schedule_only"]


def test_test_labels_do_not_change_predictions(result):
    f, t, fc, _ = result
    t2 = t.copy()
    test_rows = (t2.direction == "arrival") & (t2.hour_utc >= pd.Timestamp("2025-01-01 06:00", tz="UTC"))
    t2.loc[test_rows, "actual_count"] = t2.loc[test_rows, "actual_count"] + 500
    fc2, _ = throughput.fit_evaluate(f, t2, AIRPORTS, "test-run")
    for c in ("arrivals_pred", "arrivals_pred_schedule_only", "arrivals_baseline"):
        np.testing.assert_allclose(fc[c].to_numpy(), fc2[c].to_numpy())


def test_intervals_are_group_calibrated(result):
    _, _, fc, rep = result
    groups = rep["uncertainty"]["half_width_by_group"]
    assert {g["weather_impacted"] for g in groups} == {True, False}
    assert (fc.arrivals_lower <= fc.arrivals_pred).all() and (fc.arrivals_upper >= fc.arrivals_pred).all()
    assert (fc.arrivals_lower >= 0).all()


def test_masked_actuals_are_excluded():
    f, t = synthetic(seed=1)
    t.loc[t.direction == "arrival", "actual_count"] = pd.NA
    with pytest.raises(throughput.ThroughputError):
        throughput.fit_evaluate(f, t, AIRPORTS, "r")


def test_failure_case_carries_evidence(result):
    _, _, _, rep = result
    fail = rep["failure_case"]
    assert fail["evidence"] and fail["explanation"] and fail["taf_bulletin_id"]


@pytest.mark.skipif(not (CAPACITY_DIR / "throughput_forecast.parquet").exists(), reason="not published")
def test_published_throughput_is_labelled_not_aar():
    fc = pd.read_parquet(CAPACITY_DIR / "throughput_forecast.parquet")
    rep = json.loads((CAPACITY_DIR / "throughput_evaluation.json").read_text(encoding="utf-8"))
    assert set(fc.label_kind) <= {"observed_reporting_carrier_arrivals"}
    assert "NOT the facility Airport Arrival Rate" in rep["not_aar"]
    aar = pd.read_parquet(CAPACITY_DIR / "forecast.parquet")
    assert "observed_reporting_carrier_arrivals" not in set(aar.get("label_kind", pd.Series(dtype=str)))
