"""Candidate B: fixed temporal windows, serializable correction and honest rejection."""
import json

import numpy as np
import pandas as pd

from src.data_capacity import capacity_calibration as cc


def fixture_rows():
    hours = pd.date_range("2024-01-02", periods=120, freq="h", tz="UTC")
    rows = pd.DataFrame({"airport": "KATL", "horizon_hours": 3, "target_hour_utc": hours,
                         "target_date_local": hours.tz_localize(None).normalize(), "aar_pred": 50.,
                         "observed_arrivals": np.arange(120) % 10 + 50., "scheduled_arrivals": 70.,
                         "status": "available", "baseline_frontier": 50., "backoff_level": "regime",
                         "weather_regime": "vfr"})
    rows["asof_utc"] = rows.target_hour_utc-pd.Timedelta(hours=3)
    rows["available_at_utc"] = rows.asof_utc
    return rows, {"demand_thresholds": {"KATL": 60.}}


def test_residual_quantile_serialization_and_lead_backoff():
    rows, model = fixture_rows()
    correction = cc.fit_correction(rows, model)
    assert correction["fit_end_local"] == "2024-08-31"
    assert correction["selection_end_local"] == "2024-12-31"
    assert correction["model_fitted_data_end_utc"] == "2024-09-01T04:00:00+00:00"
    assert correction["model_selection_end_utc"] == "2025-01-01T05:00:00+00:00"
    cells = correction["cells"]
    assert np.isclose(cells[0]["offset"], 8.1)
    assert cells[0]["support_n"] == 120
    assert cells[1]["offset"] == 0 and cells[1]["backoff"] == "identity_insufficient_support"
    restored = json.loads(json.dumps(correction))
    pd.testing.assert_frame_equal(cc.apply_correction(rows, correction), cc.apply_correction(rows, restored))


def test_selection_and_test_label_perturbation_cannot_change_fit():
    rows, model = fixture_rows()
    later = rows.copy()
    later["target_date_local"] = pd.Timestamp("2024-09-01")
    combined = pd.concat([rows, later], ignore_index=True)
    before = cc.fit_correction(combined, model)
    combined.loc[combined.target_date_local >= "2024-09-01", "observed_arrivals"] = 99999.
    assert cc.fit_correction(combined, model) == before
    combined.loc[combined.target_date_local >= "2024-09-01", "target_date_local"] = pd.Timestamp("2025-01-01")
    assert cc.fit_correction(combined, model) == before


def test_unavailable_future_and_low_demand_rows_do_not_fit():
    rows, model = fixture_rows()
    bad = rows.copy()
    bad["observed_arrivals"] = 9999.
    for modification in ("future", "missing_time", "unavailable", "low_demand", "missing_prediction"):
        invalid = bad.copy()
        if modification == "future":
            invalid["available_at_utc"] = invalid.asof_utc + pd.Timedelta(hours=1)
        elif modification == "missing_time":
            invalid["available_at_utc"] = pd.NaT
        elif modification == "unavailable":
            invalid["status"] = "unavailable"
        elif modification == "low_demand":
            invalid["scheduled_arrivals"] = 1.
        else:
            invalid["aar_pred"] = np.nan
        assert cc.fit_correction(pd.concat([rows, invalid], ignore_index=True), model) == cc.fit_correction(rows, model)


def test_insufficient_unique_support_and_missing_cell_identity():
    rows, model = fixture_rows()
    duplicated = pd.concat([rows.iloc[:20]]*10, ignore_index=True)
    correction = cc.fit_correction(duplicated, model)
    assert correction["cells"][0]["support_n"] == 20
    assert correction["cells"][0]["offset"] == 0.
    unknown = rows.copy()
    unknown["airport"] = "MISSING"
    unknown.loc[0, "aar_pred"] = np.nan
    applied = cc.apply_correction(unknown, correction)
    assert applied.aar_pred.isna().sum() == 1
    assert set(applied.calibration_backoff) == {"identity_missing_cell"}


def test_guardrails_use_six_cells_and_pinball_over_rmse():
    row = {"before": {"n": 100, "pinball": 3., "rmse": 20.},
           "after": {"n": 100, "pinball": 2.9, "rmse": 20.}}
    assert cc.decision([row]*6)["adopt"]
    assert not cc.decision([row]*5)["adopt"]
    worse = {"before": row["before"], "after": {"pinball": 3.1, "rmse": 19.}}
    assert not cc.decision([worse]*6)["adopt"]
    cell_failure = {"before": row["before"], "after": {"pinball": 3.2, "rmse": 20.}}
    assert not cc.decision([row]*5+[cell_failure])["adopt"]
    rmse_failure = {"before": row["before"], "after": {"pinball": 2.9, "rmse": 21.}}
    assert not cc.decision([rmse_failure]*6)["adopt"]


def test_comparison_preserves_identical_eligible_hours():
    rows, model = fixture_rows()
    rows.loc[0, "status"] = "unavailable"
    corrected = cc.apply_correction(rows, cc.fit_correction(rows, model))
    result = cc.compare(rows, corrected, model, pd.Series(True, index=rows.index))[0]
    assert result["before"]["n"] == result["after"]["n"] == 119
    assert result["excluded_snapshots"] == 1
    assert result["before"]["n_unique_hours"] == 119
    assert all(r["before"]["n"] == r["after"]["n"] == 0 for r in result["severe"])
