import numpy as np
import pandas as pd
import pytest

from src.flight_risk.capacity_scenario import build_capacity_inputs, build_constant_capacity_scenario


CUTOFF = pd.Timestamp("2025-07-12T20:00:00Z")


def frame():
    return pd.DataFrame({
        "airport": ["KATL"] * 3, "asof_utc": [CUTOFF] * 3,
        "target_hour_utc": [CUTOFF + pd.Timedelta(hours=h) for h in (3, 6, 12)],
        "horizon_hours": [3, 6, 12], "aar_pred": [80., 81., 82.], "status": ["partial"] * 3,
        "label_kind": ["model_estimated_capacity"] * 3,
        "population": ["BTS reporting carriers"] * 3,
        "features_available_at_utc": [CUTOFF] * 3,
        "model_train_end_utc": [pd.Timestamp("2024-01-01T06:00:00Z")] * 3,
        "model_selection_end_utc": [pd.Timestamp("2025-01-01T06:00:00Z")] * 3,
        "run_id": ["run1"] * 3, "model_version": ["v1"] * 3, "source_id": ["weather+traffic"] * 3,
    })


def scenario(f=None, **kw):
    return build_constant_capacity_scenario(frame() if f is None else f, airport="KATL",
                                            asof_utc=CUTOFF, window_hours=6, anchor_lead=3, **kw)


def test_sparse_forecasts_do_not_become_complete_window():
    result = build_capacity_inputs(frame(), airport="KATL", asof_utc=CUTOFF, window_hours=6)
    assert result["status"] == "partial"
    assert len(result["capacity"]) == 1
    assert len(result["missing_inputs"]) == 5
    assert not result["operationally_eligible"]


def test_explicit_constant_assumption_keeps_original_anchor_and_sources():
    source = frame()
    original = source.copy(deep=True)
    result = scenario(source)
    rows = result["capacity"]
    assert result["status"] == "partial" and not result["missing_inputs"]
    assert rows.aar_pred.eq(80).all()
    assert rows.target_hour_utc.tolist() == list(pd.date_range(CUTOFF, periods=6, freq="h"))
    assert rows.anchor_target_hour_utc.eq(CUTOFF + pd.Timedelta(hours=3)).all()
    assert rows.features_available_at_utc.eq(CUTOFF).all()
    assert rows.status.eq("scenario_assumption").all()
    assert rows.label_kind.eq("model_estimated_capacity").all()
    pd.testing.assert_frame_equal(source, original)


@pytest.mark.parametrize("column,value", [
    ("aar_pred", np.nan), ("aar_pred", np.inf), ("aar_pred", -1), ("aar_pred", True),
    ("status", "unavailable"), ("label_kind", "facility_aar"), ("population", "all_airport"),
    ("run_id", ""), ("model_version", ""), ("source_id", ""),
    ("features_available_at_utc", CUTOFF + pd.Timedelta(hours=1)),
    ("model_train_end_utc", CUTOFF + pd.Timedelta(hours=1)),
    ("model_selection_end_utc", CUTOFF + pd.Timedelta(hours=1)),
    ("model_selection_end_utc", pd.NaT),
    ("target_hour_utc", CUTOFF + pd.Timedelta(hours=4)),
])
def test_bad_anchor_is_withheld(column, value):
    f = frame()
    f[column] = f[column].astype(object)
    f.loc[0, column] = value
    r = scenario(f)
    assert r["status"] == "unavailable"
    assert r["capacity"].empty and r["missing_inputs"]


def test_duplicate_anchor_and_wrong_cutoff_are_withheld():
    f = frame()
    assert scenario(pd.concat([f, f.iloc[:1]]))["status"] == "unavailable"
    f.asof_utc += pd.Timedelta(hours=1)
    assert scenario(f)["status"] == "unavailable"


@pytest.mark.parametrize("window", [0, -1, 169, True, 3.5])
def test_invalid_window_is_withheld(window):
    r = build_constant_capacity_scenario(frame(), airport="KATL", asof_utc=CUTOFF,
                                         window_hours=window, anchor_lead=3)
    assert r["status"] == "unavailable"


def test_training_after_selection_is_withheld():
    f = frame()
    f.model_train_end_utc = CUTOFF
    assert scenario(f)["status"] == "unavailable"


def test_complete_explicit_proxy_window_still_not_operationally_eligible():
    f = frame()
    f.horizon_hours = [0, 1, 2]
    f.target_hour_utc = pd.date_range(CUTOFF, periods=3, freq="h")
    r = build_capacity_inputs(f, airport="KATL", asof_utc=CUTOFF, window_hours=3)
    assert r["status"] == "available" and not r["operationally_eligible"]
