import numpy as np
import pandas as pd
import pytest

from src.flight_risk.cutoff_features import add_cutoff_features, FEATURE_COLUMNS

CUTOFF = pd.Timestamp("2024-10-01T12:00:00Z")


def fixture():
    snapshots = pd.DataFrame({"airport": ["KATL", "KATL"], "asof_utc": [CUTOFF] * 2,
                              "target_hour_utc": [CUTOFF + pd.Timedelta(hours=3)] * 2})
    flights = pd.DataFrame({"flight_id": list("abcdef"), "origin": ["ATL"] * 6,
        "actual_dep_gate_utc": [CUTOFF + pd.Timedelta(hours=h) for h in (-4, -3, -2, -1, 0, 1)],
        "dep_delay_min": [200, 46, 10, 100, 400, 500], "cancelled": [False] * 6,
        "coverage": ["sample"] * 6})
    hours = pd.date_range(CUTOFF-pd.Timedelta(hours=4), CUTOFF+pd.Timedelta(hours=3), freq="h")
    traffic = pd.DataFrame([{"airport": "KATL", "hour_utc": h, "direction": d,
        "scheduled_count": 30 if d == "arrival" else 40, "actual_count": 999,
        "coverage": "reporting_carriers"} for h in hours for d in ("arrival", "departure")])
    return snapshots, flights, traffic


def test_strict_cutoff_and_inclusive_lower_boundary_with_correct_denominator():
    result = add_cutoff_features(*fixture())
    assert result.recent_departure_count_2h.tolist() == [2, 2]
    assert result.recent_severe_delay_share_2h.tolist() == [.5, .5]
    assert result.recent_departure_count_3h.tolist() == [3, 3]
    assert result.recent_severe_delay_share_3h.tolist() == [2/3, 2/3]
    assert result.scheduled_arrivals_target_hour.tolist() == [30, 30]
    assert result.scheduled_departures_target_hour.tolist() == [40, 40]


def test_future_outcomes_and_cancellations_cannot_change_features():
    s, f, t = fixture()
    before = add_cutoff_features(s, f, t)
    f.loc[f.actual_dep_gate_utc >= CUTOFF, "dep_delay_min"] = -999
    f.loc[f.actual_dep_gate_utc >= CUTOFF, "cancelled"] = True
    t["actual_count"] = -999
    after = add_cutoff_features(s, f, t)
    pd.testing.assert_frame_equal(before, after)


def test_missing_coverage_is_not_zero_but_empty_covered_sample_is_zero_count():
    s, f, t = fixture()
    f = f.iloc[0:0]
    covered = add_cutoff_features(s, f, t)
    assert covered.recent_departure_count_2h.eq(0).all()
    assert covered.recent_severe_delay_share_2h.isna().all()
    t = t[t.hour_utc != CUTOFF-pd.Timedelta(hours=1)]
    missing = add_cutoff_features(s, f, t)
    assert missing.recent_departure_count_2h.isna().all()


def test_unknown_scheduled_target_is_not_zero():
    s, f, t = fixture()
    t.loc[t.hour_utc == s.target_hour_utc.iloc[0], "scheduled_count"] = np.nan
    result = add_cutoff_features(s, f, t)
    assert result.scheduled_arrivals_target_hour.isna().all()
    assert result.scheduled_departures_target_hour.isna().all()


def test_unlabelled_or_duplicate_observed_events_do_not_bias_rates():
    s, f, t = fixture()
    f.loc[3, "dep_delay_min"] = np.nan
    f = pd.concat([f, f.iloc[[2]]], ignore_index=True)
    result = add_cutoff_features(s, f, t)
    assert result.recent_departure_count_2h.eq(0).all()
    assert result.recent_severe_delay_share_3h.eq(1).all()


def test_wrong_population_and_duplicate_traffic_are_rejected_or_unknown():
    s, f, t = fixture()
    bad = pd.concat([t, t.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate traffic"):
        add_cutoff_features(s, f, bad)
    t["coverage"] = "sample"
    result = add_cutoff_features(s, f, t)
    assert result[FEATURE_COLUMNS].isna().all().all()


def test_nonconsecutive_indices_scope_and_no_mutation():
    s, f, t = fixture()
    s.index = [8, 3]
    old_s, old_f, old_t = s.copy(), f.copy(), t.copy()
    result = add_cutoff_features(s, f, t)
    pd.testing.assert_frame_equal(s, old_s)
    pd.testing.assert_frame_equal(f, old_f)
    pd.testing.assert_frame_equal(t, old_t)
    assert list(result.index) == [8, 3]
    assert result.attrs["recent_departure_population"] == ["sample"]
    assert any("sample-only" in a for a in result.attrs["cutoff_feature_assumptions"])


@pytest.mark.parametrize("field", ["asof_utc", "target_hour_utc"])
def test_naive_snapshot_timestamps_refused(field):
    s, f, t = fixture()
    s[field] = s[field].dt.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        add_cutoff_features(s, f, t)


def test_capacity_input_is_not_used_for_training_period_ratio():
    s, f, t = fixture()
    result = add_cutoff_features(s, f, t, capacity_estimate=pd.DataFrame({"aar_pred": [999]}))
    assert not any("ratio" in name for name in result.columns)
