"""Optional outputs from section 2.3: each needs a present and an absent state."""
import pandas as pd
import pytest

from src.dashboard import views
from src.dashboard.data import load_bundle
from src.dashboard.views import resolve_airport
from tests.dashboard import conftest as c
from tests.dashboard.test_app import run, text  # noqa: F401

KATL = resolve_airport("KATL")


def full_evaluation():
    return c.envelope(model="synthetic", split={}, metrics=[], **c.evaluation_additions())


def frames(app):
    return [f.value for f in app.dataframe]


def test_absent_additions_show_unavailable_states(run, root):
    app = run(root)
    app.toggle(key="reveal").set_value(True).run()
    body = text(app)
    for name in ("Impact comparison", "Storm-event cohorts", "AAR trend", "Reporting-carrier traffic"):
        assert f"**{name} unavailable.**" in body


def test_evaluation_additions_render(run, root):
    c.publish_risk(root, evaluation=full_evaluation())
    app = run(root)
    assert "Measured prediction comparison, not an operational saving" in text(app)
    assert any("model_recall" in f.columns for f in frames(app))
    assert any("cohort" in f.columns for f in frames(app))
    assert "False alarm" not in text(app)  # Failure cases hold outcomes.
    app.toggle(key="reveal").set_value(True).run()
    assert not app.exception
    assert "**False alarm**" in text(app)


def test_old_and_new_failure_fields_are_not_repeated():
    case = c.evaluation_additions()["failure_cases"][0]
    document = {"failure_case": {"flight_id": "x", "asof_utc": "t"}, "failure_cases": [case, {"flight_id": "x", "asof_utc": "t"}]}
    assert len(views.failure_cards(document)) == 2


def test_aar_trend_needs_genuine_observed_labels():
    forecast = c.forecast()
    assert views.aar_trend(forecast, KATL, 6).empty  # Column not published.
    assert views.aar_trend(forecast.assign(aar_observed=None), KATL, 6).empty
    assert len(views.aar_trend(forecast.assign(aar_observed=80.0), KATL, 6)) == 1
    relabelled = forecast.assign(aar_observed=80.0, label_kind="throughput")
    assert views.aar_trend(relabelled, KATL, 6).empty


def test_aar_trend_is_behind_reveal(run, tmp_path):
    c.publish_risk(tmp_path)
    c.publish_capacity(tmp_path, forecast_table=c.forecast().assign(aar_observed=80.0))
    app = run(tmp_path)
    app.radio(key="horizon").set_value(6).run()
    assert not any("aar_observed" in f.columns for f in frames(app))
    app.toggle(key="reveal").set_value(True).run()
    assert not app.exception
    assert any("aar_observed" in f.columns for f in frames(app))


def test_actual_traffic_counts_need_reveal(run, root):
    c.publish_capacity(root, traffic_table=c.traffic())
    app = run(root)
    assert "not queue demand" in text(app)
    assert not any("actual_count" in f.columns for f in frames(app))
    app.toggle(key="reveal").set_value(True).run()
    assert any("actual_count" in f.columns for f in frames(app))


def test_traffic_gap_stays_missing():
    table = c.traffic().drop(index=2)
    rows = views.reporting_traffic(table, KATL, c.ASOF, 6, False)
    assert len(rows) == 5 and (rows["scheduled_count"] > 0).all()


def test_sampled_traffic_is_rejected(tmp_path):
    c.publish_capacity(tmp_path, traffic_table=c.traffic().assign(coverage="sample"))
    assert "reporting_carriers" in load_bundle(tmp_path).problem("traffic_hourly")
