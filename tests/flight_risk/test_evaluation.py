"""Retrospective evaluation: storms, impact, alert rates and explained failure cases."""
import numpy as np
import pandas as pd
import pytest

from src.flight_risk.data import expand_horizons, prepare_sample
from src.flight_risk.evaluation import _top_share, alert_rates, impact, storm_cohorts
from src.flight_risk.pipeline import build_artifacts


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    records = []
    for year in [2023, 2024, 2025]:
        for i in range(80):
            records.append({"FL_DATE": f"{year}-02-{i % 20 + 1:02}", "ORIGIN": "ATL" if i % 2 else "DFW", "DEST": "LAX",
                            "OP_UNIQUE_CARRIER": "DL", "OP_CARRIER_FL_NUM": i + 1, "CRS_DEP_TIME": 800 + i % 8 * 100,
                            "DEP_DELAY": 65 if i % 5 == 0 else 0, "CANCELLED": 0, "CRS_ELAPSED_TIME": 120, "DISTANCE": 700})
    path = tmp_path_factory.mktemp("evaluation") / "sample.csv"
    pd.DataFrame(records).to_csv(path, index=False)
    return path


def storm_file(directory, sample):
    # Synthetic events on every 2025 test date, never exported as real data.
    frame = expand_horizons(prepare_sample(pd.read_csv(sample)).eligible)
    hours = frame[frame.split.eq("test")].drop_duplicates(["airport", "target_hour_utc"])
    events = pd.DataFrame({"airport": hours.airport, "event_type": "Thunderstorm Wind",
                           "begin_utc": hours.target_hour_utc, "end_utc": hours.target_hour_utc + pd.Timedelta(minutes=5),
                           "use": "retrospective_evaluation_only"})
    path = directory / "storms.parquet"
    events.to_parquet(path, index=False)
    return path


def weather_file(directory, sample, drop_test_rows=0):
    frame = expand_horizons(prepare_sample(pd.read_csv(sample)).eligible)
    weather = frame[["airport", "asof_utc", "target_hour_utc", "horizon_hours", "severe_delay", "split"]].copy()
    weather["thunderstorm_flag"] = weather.severe_delay.astype(float)
    weather["precip_flag"] = 0.0
    weather = weather.drop_duplicates(["airport", "asof_utc", "target_hour_utc", "horizon_hours"])
    weather["available_at_utc"] = weather.asof_utc - pd.Timedelta(minutes=1)
    weather["source_id"], weather["status"] = "synthetic-test-fixture", "available"
    test_rows = weather.index[weather.split.eq("test")][:drop_test_rows]
    weather.loc[test_rows, "status"] = "partial"
    path = directory / "weather.parquet"
    weather.drop(columns=["severe_delay", "split"]).to_parquet(path, index=False)
    return path


def test_storm_events_cannot_change_predictions(sample, tmp_path):
    without = build_artifacts(sample)
    with_storms = build_artifacts(sample, storm_events_path=storm_file(tmp_path, sample))
    assert np.array_equal(without.predictions.probability_severe_delay, with_storms.predictions.probability_severe_delay)
    assert np.array_equal(without.predictions.threshold, with_storms.predictions.threshold)
    features = with_storms.manifest["feature_allowlist"] + with_storms.manifest["weather_feature_allowlist"]
    assert not any("storm" in name or "event" in name for name in features)
    assert with_storms.evaluation["storm_annotation"]["status"] == "available"
    assert without.evaluation["storm_annotation"]["status"] == "unavailable"
    assert without.evaluation["storm_cohorts"] == []


def test_small_storm_cohorts_withhold_metrics():
    test = pd.DataFrame({"airport": "KATL", "horizon_hours": 3, "severe_delay": [1, 0, 0, 1] * 10, "_alert": [True, False] * 20})
    flags = np.zeros(40, dtype=bool)
    flags[:6] = True
    rows = storm_cohorts(test, np.linspace(0, 1, 40), np.full(40, .2), .1, flags)
    storm = [row for row in rows if row["cohort"] == "storm_within_3h"]
    assert storm and all(row["status"] == "unavailable" and row["value"] is None for row in storm)
    calm = [row for row in rows if row["cohort"] == "no_storm_within_3h"]
    assert all(row["n"] == 34 for row in calm)


def test_equal_alert_baseline_shares_ties_and_matches_workload():
    labels = np.array([1, 0, 1, 0, 0, 0])
    scores = np.array([.9, .5, .5, .5, .5, .1])
    # One slot above the tie, then one of four tied rows holding one positive.
    assert _top_share(labels, scores, 2) == pytest.approx(1.25)
    assert _top_share(labels, scores, 0) == 0.0
    test = pd.DataFrame({"airport": "KATL", "horizon_hours": 3, "severe_delay": labels, "_alert": [True, True, False, False, False, False]})
    comparison = impact(test, scores)["comparisons"][0]
    assert comparison["alerts"] == 2 and comparison["alert_share"] == pytest.approx(2 / 6)
    assert comparison["model_recall"] == pytest.approx(.5) and comparison["baseline_recall"] == pytest.approx(.625)


def test_alert_rates_publish_numerators_and_denominators():
    test = pd.DataFrame({"airport": ["KATL"] * 4, "horizon_hours": 6, "severe_delay": [1, 0, 0, 0], "_alert": [True, True, False, False]})
    (row,) = alert_rates(test)
    assert (row["alerts"], row["scored"], row["observed_severe"]) == (2, 4, 1)
    assert row["alert_rate"] == .5 and row["observed_severe_rate"] == .25


def test_failure_cases_cover_missed_false_alarm_and_declined(sample, tmp_path):
    result = build_artifacts(sample, weather_features_path=weather_file(tmp_path, sample, drop_test_rows=3),
                             storm_events_path=storm_file(tmp_path, sample))
    cases = {case["kind"]: case for case in result.evaluation["failure_cases"]}
    assert "declined" in cases
    assert cases["declined"]["evidence"]["weather_snapshot_status"] == "partial"
    # Weather keys are per airport/hour, so three rejected snapshots can affect several flights.
    assert result.predictions.model_kind.eq("schedule_only").sum() >= 3
    for case in cases.values():
        assert case["requires_outcome_reveal"] and case["explanation"] and case["remedy"]
        assert case["flight_id"] in set(result.predictions.flight_id)
    if "missed" in cases:
        assert cases["missed"]["observed"]["severe_delay"] == 1 and cases["missed"]["probability"] < cases["missed"]["threshold"]
    if "false_alarm" in cases:
        assert cases["false_alarm"]["observed"]["severe_delay"] == 0 and cases["false_alarm"]["probability"] >= cases["false_alarm"]["threshold"]


def test_schedule_only_run_still_explains_misses_and_false_alarms(sample, tmp_path):
    # The schedule-only fixture cannot separate classes, so both error kinds must occur.
    cases = {case["kind"] for case in build_artifacts(sample, storm_events_path=storm_file(tmp_path, sample)).evaluation["failure_cases"]}
    assert {"missed", "false_alarm"} <= cases and "declined" not in cases


def test_calibration_decision_ignores_test_outcomes_and_adopts_only_material_gains():
    from src.flight_risk.evaluation import calibration_experiment
    rng = np.random.default_rng(27)
    dates = pd.date_range("2024-01-01", "2024-12-31", periods=2000)
    labels = (rng.random(2000) < .1).astype(int)
    overconfident = np.where(labels == 1, .6, .4) + rng.normal(0, .15, 2000).clip(-.35, .35)
    test_probs = rng.random(500)
    first = calibration_experiment("demo", dates, labels, overconfident, rng.integers(0, 2, 500), test_probs)
    second = calibration_experiment("demo", dates, labels, overconfident, 1 - rng.integers(0, 2, 500), test_probs)
    assert first["adopted"] and first["adopted"] == second["adopted"]
    assert first["validation_relative_gain"] == second["validation_relative_gain"]
    # Labels drawn from the stated probabilities, so Platt scaling has nothing material to fix.
    calibrated_already = rng.uniform(.02, .4, 20000)
    calibrated_labels = (rng.random(20000) < calibrated_already).astype(int)
    long_dates = pd.date_range("2024-01-01", "2024-12-31", periods=20000)
    assert not calibration_experiment("demo", long_dates, calibrated_labels, calibrated_already, labels[:500], test_probs)["adopted"]
    one_class = calibration_experiment("demo", dates, np.zeros(2000, dtype=int), overconfident, labels[:500], test_probs)
    assert one_class["status"] == "unavailable" and not one_class["adopted"]
