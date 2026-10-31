"""Capacity proxy estimator. Model tests use SYNTHETIC data; the last test reads the real publication."""
import json

import numpy as np
import pandas as pd
import pytest

from src.data_capacity import capacity_estimate as ce
from src.data_capacity.config import REPO_ROOT, resolve_airports
from src.data_capacity.features import FEATURE_COLUMNS
from src.data_capacity.io import sha256_file

AIRPORTS = resolve_airports(["KATL", "KDFW"])


def synthetic(seed=0):
    rng = np.random.default_rng(seed)
    hours = pd.date_range("2023-01-01 06:00", "2025-07-31 23:00", freq="3h", tz="UTC")
    feats, traffic = [], []
    for ap in AIRPORTS:
        ifr = rng.random(len(hours)) < 0.2
        sched = rng.integers(20, 90, len(hours)).astype(float)
        cap = np.where(ifr, 50, 80)
        actual = np.minimum(sched, cap - rng.integers(0, 6, len(hours)))
        for lead in (3, 6, 12):
            f = pd.DataFrame({"airport": ap.icao, "target_hour_utc": hours, "horizon_hours": lead})
            f["asof_utc"] = f.target_hour_utc - pd.to_timedelta(lead, unit="h")
            for col in FEATURE_COLUMNS:
                f[col] = 0.0
            f["ceiling_ft_agl"] = np.where(ifr, 500.0, 20000.0)
            f["visibility_sm"] = np.where(ifr, 1.0, 10.0)
            f["frozen_precip_flag"] = 0
            f["status"], f["source_id"] = "available", "synthetic"
            f["available_at_utc"] = f.asof_utc
            feats.append(f)
        for direction in ("arrival", "departure"):
            traffic.append(pd.DataFrame({"airport": ap.icao, "hour_utc": hours, "direction": direction,
                                         "scheduled_count": sched, "actual_count": pd.array(actual.astype(int), dtype="Int64")}))
    return {"weather_features": pd.concat(feats, ignore_index=True), "traffic_hourly": pd.concat(traffic, ignore_index=True)}


@pytest.fixture(scope="module")
def built():
    frames = synthetic()
    return frames, ce.build(frames, AIRPORTS, "test-run")


def test_both_airports_all_leads_and_proxy_labels(built):
    _, res = built
    fc = res["forecast"]
    assert {(a, h) for a, h in zip(fc.airport, fc.horizon_hours)} == {(a.icao, h) for a in AIRPORTS for h in (3, 6, 12)}
    assert set(fc.label_kind) == {"model_estimated_capacity"} and fc.aar_observed.isna().all()
    assert set(fc.uncertainty_kind) == {"unavailable"} and fc[["aar_lower", "aar_upper"]].isna().all().all()
    assert (fc.asof_utc >= fc.model_selection_end_utc).all() and ce.validate_forecast(fc) == []


def test_weather_regime_lowers_the_frontier(built):
    _, res = built
    fc = res["forecast"]
    ifr = fc[fc.weather_regime == "ifr"].aar_pred.mean()
    vfr = fc[fc.weather_regime == "vfr"].aar_pred.mean()
    assert ifr < vfr - 20


def test_support_counts_unique_hours_per_lead(built):
    frames, res = built
    cells = pd.DataFrame(res["model"]["cells"])
    all_cells = cells[cells.level == "airport"]
    # identical per lead: leads are never pooled, so no cell can exceed the number of training hours
    train_hours = frames["traffic_hourly"].query("direction == 'arrival' and airport == 'KATL'")
    assert all_cells.groupby("airport").support_n.nunique().eq(1).all()
    assert all_cells.support_n.max() < len(train_hours)


def test_held_out_actuals_cannot_change_estimates(built):
    frames, res = built
    perturbed = {k: v.copy() for k, v in frames.items()}
    t = perturbed["traffic_hourly"]
    test_rows = t.hour_utc >= pd.Timestamp("2024-12-31 12:00", tz="UTC")
    t.loc[test_rows, "actual_count"] = 0
    t.loc[test_rows, "scheduled_count"] = 999
    res2 = ce.build(perturbed, AIRPORTS, "test-run")
    np.testing.assert_allclose(res["forecast"].aar_pred.to_numpy(), res2["forecast"].aar_pred.to_numpy())
    assert res["model"]["demand_thresholds"] == res2["model"]["demand_thresholds"]


@pytest.mark.parametrize("column,value,message", [
    ("features_available_at_utc", pd.Timedelta(hours=1), "after cutoff"),
    ("model_train_end_utc", None, "null model_train_end_utc"),
])
def test_future_or_missing_timestamps_rejected(built, column, value, message):
    fc = built[1]["forecast"].copy()
    fc[column] = pd.NaT if value is None else fc["asof_utc"] + value
    fc[column] = pd.to_datetime(fc[column], utc=True)
    assert any(message in e for e in ce.validate_forecast(fc))


def test_regime_priority_and_unknown():
    f = pd.DataFrame({"thunderstorm_flag": [1, 0, 0, 0, 0, 0], "frozen_precip_flag": [1, 1, 0, 0, 0, 0],
                      "ceiling_ft_agl": [500, 500, 500, 20000, 2000, np.nan], "visibility_sm": [1, 1, 1, 10, 10, 10],
                      "crosswind_kt": [20, 20, 20, 20, 0, 0], "tailwind_kt": [0, 0, 0, 0, 0, 0]})
    assert ce.classify_regime(f).tolist() == ["convective", "winter", "ifr", "wind", "mvfr", "unknown"]


def test_input_hash_mismatch_is_refused(tmp_path):
    cap = tmp_path / "artifacts" / "capacity"
    cap.mkdir(parents=True)
    pd.DataFrame({"a": [1]}).to_parquet(cap / "traffic_hourly.parquet")
    pd.DataFrame({"a": [1]}).to_parquet(cap / "weather_features.parquet")
    (cap / "manifest.json").write_text(json.dumps({"run_id": "r", "artifact_hashes": {
        "traffic_hourly.parquet": "0" * 64, "weather_features.parquet": sha256_file(cap / "weather_features.parquet")}}))
    with pytest.raises(ce.EstimateError, match="SHA256"):
        ce.load_published_inputs(tmp_path)


@pytest.mark.skipif(not (REPO_ROOT / "artifacts/capacity_estimate/manifest.json").exists(), reason="not published")
def test_published_estimate_is_consistent():
    d = REPO_ROOT / "artifacts/capacity_estimate"
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["artifact_hashes"].items():
        assert sha256_file(d / name) == digest, name
    fc = pd.read_parquet(d / "forecast.parquet")
    assert ce.validate_forecast(fc) == [] and set(fc.run_id) == {manifest["run_id"]}
    assert {(a, h) for a, h in zip(fc.airport, fc.horizon_hours)} == {(a, h) for a in ("KATL", "KDFW") for h in (3, 6, 12)}
    for src in manifest["sources"]["inputs"]:
        assert sha256_file(REPO_ROOT / src["path"]) == src["sha256"]  # frozen inputs unchanged
    for name in ("evaluation.json", "assumptions.json", "model.json"):
        doc = json.loads((d / name).read_text(encoding="utf-8"))
        assert doc["run_id"] == manifest["run_id"] and doc["schema_version"] == "2.0"
        assert b"\r" not in (d / name).read_bytes()
