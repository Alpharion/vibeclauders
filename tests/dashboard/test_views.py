import pandas as pd
import pytest

from src.dashboard import views
from src.dashboard.data import load_bundle
from src.dashboard.views import Snapshot, resolve_airport
from tests.dashboard import conftest as c

KATL = resolve_airport("KATL")
KDFW = resolve_airport("KDFW")


def snap(horizon=6, asof=c.ASOF, airport=KATL):
    return Snapshot(airport, asof, horizon)


def test_scored_view_uses_target_hour_not_cumulative_window():
    ids = set(views.scored_flights(c.flights(), snap())["flight_id"])
    assert ids == {"f1", "f2"}  # f4 lies in [asof, target) and is not scored.


def test_risk_join_keeps_scored_cohort(root):
    rows = views.risk_rows(load_bundle(root), snap())
    assert list(rows["flight_id"]) == ["f1", "f2"]
    assert list(rows["airport"].unique()) == ["KATL"]


def test_changing_key_changes_rows_without_borrowing(root):
    bundle = load_bundle(root)
    assert set(views.risk_rows(bundle, snap(3))["flight_id"]) == {"f1"}
    assert views.risk_rows(bundle, snap(12)).empty
    assert views.risk_rows(bundle, snap(asof=c.ASOF + pd.Timedelta(hours=1))).empty


def test_replay_index_reflects_published_keys_only(root):
    index = views.replay_index(load_bundle(root))
    row = index[(index.airport == "KATL") & (index.horizon_hours == 6) & (index.asof_utc == c.ASOF)]
    assert row["predictions"].item() == 2
    missing = index[(index.airport == "KATL") & (index.horizon_hours == 12)]
    assert (missing["predictions"] == 0).all()  # Selectable only as the decision cutoff.


def test_movements_reconcile_and_are_labelled_sampled():
    result = views.planning_movements(c.flights(), KATL, c.ASOF, 6)
    assert (result["arrivals"], result["departures"]) == (1, 1)
    assert result["movements"] == 2
    assert result["hourly"][["arrivals", "departures"]].sum().sum() == 2
    assert result["coverage"] == "sampled"


def test_mixed_coverage_cohort_is_not_complete():
    rows = pd.DataFrame({"coverage": ["complete", "sample"]})
    assert views.coverage_label(rows) == "sampled"
    assert views.coverage_label(rows.iloc[:1]) == "complete"


def test_outcomes_hidden_until_reveal():
    table = c.flights().assign(actual_dep_utc=c.ASOF)
    hidden = views.mask_outcomes(table, False)
    assert not set(views.OUTCOME_COLUMNS) & set(hidden.columns)
    assert "actual_dep_utc" not in hidden
    assert "dep_delay_min" in views.mask_outcomes(table, True)


def weather_rows():
    base = {
        "airport": "KATL", "valid_from_utc": c.ASOF, "valid_to_utc": c.ASOF + pd.Timedelta(hours=12),
        "bulletin_id": "b",
    }
    return pd.DataFrame(
        [
            {**base, "bulletin_id": "known", "issued_at_utc": c.ASOF - pd.Timedelta(hours=1), "available_at_utc": c.ASOF},
            {**base, "bulletin_id": "future", "issued_at_utc": c.ASOF + pd.Timedelta(hours=1), "available_at_utc": c.ASOF + pd.Timedelta(hours=1)},
        ]
    )


def test_future_amendment_is_excluded():
    assert list(views.bulletins_as_of(weather_rows(), snap())["bulletin_id"]) == ["known"]


def test_aar_row_without_bounds_has_unknown_uncertainty(root):
    row, reason = views.aar_row(load_bundle(root), snap())
    assert reason is None
    assert views.uncertainty(row) is None


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("label_kind", "observed_arrivals", "not genuine"),
        ("features_available_at_utc", c.ASOF + pd.Timedelta(hours=1), "later than the cutoff"),
        ("model_selection_end_utc", c.ASOF + pd.Timedelta(days=1), "later than the cutoff"),
    ],
)
def test_unsafe_aar_row_is_refused(root, column, value, message):
    bundle = load_bundle(root)
    bundle.tables["forecast"].loc[0, column] = value
    row, reason = views.aar_row(bundle, snap())
    assert row is None and message in reason


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"airport": KDFW}, "published for KATL"),
        ({"asof_utc": c.ASOF + pd.Timedelta(hours=1)}, "cutoff"),
        ({"window_hours": 3}, "6-hour window"),
    ],
)
def test_recommendation_refused_for_other_snapshot(kwargs, fragment):
    call = {"airport": KATL, "asof_utc": c.ASOF, "window_hours": 6, **kwargs}
    assert fragment in " ".join(views.decision_mismatch(c.recommendations(), **call))


def test_recommendation_accepted_for_its_snapshot():
    assert views.decision_mismatch(c.recommendations(), KATL, c.ASOF, 6) == []


def problems(table, window=6):
    return " ".join(views.queue_problems(table, KATL, c.ASOF, window))


def test_valid_queue_passes():
    assert problems(c.queue()) == ""


def test_queue_gap_is_not_filled():
    table = c.queue().drop(index=2)
    assert "contiguous" in problems(table)


def test_queue_empty_and_absent():
    assert "empty" in problems(c.queue().iloc[0:0])
    assert "not available" in problems(None)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("end_backlog", 99, "conservation"),
        ("served", 9, "exceeds capacity"),
        ("capacity", 9, "floored"),
        ("status", "observed", "simulated"),
    ],
)
def test_queue_violation_is_detected(column, value, message):
    table = c.queue()
    table.loc[0, column] = value
    assert message in problems(table)


def test_missing_capacity_measurement_is_not_zero():
    table = c.queue().astype({"capacity": "float64"})
    table.loc[1, "capacity"] = None
    assert "null" in problems(table)


def test_advice_requires_queue_and_human_review():
    items, withheld = views.supported_recommendations(c.recommendations(), False, False)
    assert items == [] and "no valid queue" in withheld[0]
    document = c.recommendations()
    document["recommendations"][0]["human_review_required"] = False
    items, withheld = views.supported_recommendations(document, True, True)
    assert items == [] and "human review" in withheld[0]


def test_basic_advice_is_not_gated_on_routing_or_eligibility():
    items, withheld = views.supported_recommendations(c.recommendations(), True, False)
    assert len(items) == 1 and withheld == []


def test_revised_times_need_eligibility():
    document = c.recommendations()
    document["recommendations"][0]["revised_times"] = [{"flight_id": "f1"}]
    items, withheld = views.supported_recommendations(document, True, False)
    assert items[0]["revised_times"] == [] and "eligibility" in withheld[0]


def test_history_recomputes_from_denominators():
    rollup = views.history_rollup(c.metrics(), "W")
    first, second = rollup.iloc[0], rollup.iloc[1]
    assert first["eligible_departures"] == 56
    assert first["severe_delay_rate"] == 14 / 56
    assert first["delay_minutes_per_flight"] == 560 / 56
    assert first["cancellation_rate"] == 7 / 63  # Unknown status leaves the denominator.
    assert first["missing_label_share"] == 7 / 70
    assert pd.isna(second["severe_delay_rate"])  # Zero denominator is null, not zero.


def test_failure_cases_found_in_nested_reports():
    assert views.find_failure_cases({"a": {"failure_example": 1}}) == [1]
