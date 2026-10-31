"""A third airport comes from configuration alone. KORD here is a synthetic fixture."""
import pandas as pd
import pytest

from src.dashboard import plots
from src.dashboard.views import Snapshot, resolve_airport, risk_rows
from src.dashboard.data import load_bundle
from src.shared import AIRPORTS, airport_icao
from tests.dashboard import conftest as c
from tests.dashboard.test_app import run, text  # noqa: F401

KORD = {"iata": "ORD", "name": "Chicago", "timezone": "America/Chicago", "heading": 100, "lat": 41.98, "lon": -87.9}


def kord_predictions():
    return c.predictions([("k1", "KORD", c.ASOF, 6, 0.4), ("f1", "KATL", c.ASOF, 6, 0.2)])


@pytest.fixture
def registered(monkeypatch):
    monkeypatch.setitem(AIRPORTS, "KORD", dict(KORD))


def test_codes_resolve_from_the_registry(registered):
    assert airport_icao("ord") == "KORD"
    assert resolve_airport("ORD").heading == 100


def test_unregistered_airport_stays_unsupported():
    assert resolve_airport("ORD") is None


def test_app_serves_configured_airport(run, tmp_path, registered):
    c.publish_risk(tmp_path, table=kord_predictions())
    app = run(tmp_path)
    assert "KORD" in app.selectbox(key="airport").options
    app.selectbox(key="airport").set_value("KORD").run()
    app.radio(key="horizon").set_value(6).run()
    assert not app.exception
    assert "Flights scored" in [m.label for m in app.metric]
    assert "fixed heading 100°" in text(app)


def test_unconfigured_airport_does_not_appear_in_app(run, tmp_path):
    c.publish_risk(tmp_path, table=kord_predictions())
    assert "KORD" not in run(tmp_path).selectbox(key="airport").options


def test_missing_heading_is_refused_not_guessed(run, tmp_path, monkeypatch):
    info = dict(KORD)
    del info["heading"]
    monkeypatch.setitem(AIRPORTS, "KORD", info)
    c.publish_risk(tmp_path, table=kord_predictions())
    app = run(tmp_path)
    app.selectbox(key="airport").set_value("KORD").run()
    assert not app.exception
    assert "no configured runway heading" in text(app)


def test_keys_stay_exact_with_a_third_airport(tmp_path, registered):
    c.publish_risk(tmp_path, table=kord_predictions())
    rows = risk_rows(load_bundle(tmp_path), Snapshot(resolve_airport("KORD"), c.ASOF, 6))
    assert list(rows["flight_id"]) == ["k1"]


def test_trend_colours_hold_when_an_airport_is_added(registered):
    rollup = pd.DataFrame(
        {"airport": list(AIRPORTS), "period": pd.Timestamp("2025-01-06"), "severe_delay_rate": 0.1, "eligible_departures": 10}
    )
    figure = plots.trend_lines(rollup, "severe_delay_rate", "t", "y", True)
    colors = {trace.name: trace.line.color for trace in figure.data}
    assert colors["KATL"] == plots.SERIES[0] and colors["KDFW"] == plots.SERIES[1]
    assert colors["KORD"] == plots.SERIES[2]
