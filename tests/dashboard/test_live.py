import ast
from pathlib import Path

import pandas as pd
import pytest
import requests
from streamlit.testing.v1 import AppTest

from src.dashboard import live
from src.dashboard.app import cached_bundle

ROOT = Path(__file__).resolve().parents[2]
METAR = [
    {
        "icaoId": "KATL", "obsTime": 1793422320, "temp": 17.8, "wdir": 80, "wspd": 6, "visib": "10+",
        "fltCat": "VFR", "rawOb": "METAR KATL 310452Z", "clouds": [{"cover": "SCT", "base": 500}, {"cover": "BKN", "base": 20000}],
    }
]
TAF = [
    {
        "icaoId": "KATL", "issueTime": "2026-10-31T02:53:00.000Z", "rawTAF": "TAF KATL",
        "fcsts": [
            {"timeFrom": 1793415600, "timeTo": 1793426400, "fcstChange": None, "wspd": 5, "visib": "6+", "clouds": None},
            {"timeFrom": 1793426400, "timeTo": 1793430000, "fcstChange": "TEMPO", "probability": 30, "wspd": 9},
        ],
    }
]


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def fake_get(url, **kwargs):
    assert kwargs["timeout"]
    return Response(METAR if "/metar" in url else TAF)


def test_fetch_records_failure_without_raising(monkeypatch):
    def fail(url, **kwargs):
        if "/taf" in url:
            raise requests.ConnectTimeout("timed out")
        return Response(METAR)

    monkeypatch.setattr(requests, "get", fail)
    bundle = live.fetch_live_weather()
    assert bundle["metar"] == METAR and bundle["taf"] == []
    assert "TAF: ConnectTimeout" in bundle["errors"][0]


def test_non_list_response_is_an_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: Response({"error": "x"}))
    assert len(live.fetch_live_weather()["errors"]) == 2


def test_ceiling_ignores_scattered_layers():
    assert live.ceiling_ft(METAR[0]) == 20000
    assert live.ceiling_ft({"clouds": None}) is None


def test_forecast_keeps_conditional_groups_labelled():
    table = live.forecast_table(TAF[0])
    assert list(table["Condition"]) == ["Prevailing", "TEMPO"]
    assert live.forecast_table(None).empty


def test_stale_age():
    now = pd.to_datetime(1793422320 + 7200, unit="s", utc=True)
    assert live.observation_age_minutes(METAR[0], now) == 120
    assert live.observation_age_minutes({}, now) is None


def test_live_module_only_reads():
    calls = {
        node.func.attr
        for node in ast.walk(ast.parse((ROOT / "src/dashboard/live.py").read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name) and node.func.value.id == "requests"
    }
    assert calls == {"get"}


@pytest.fixture
def app(monkeypatch, root):
    monkeypatch.setenv("DASHBOARD_DATA_ROOT", str(root))
    cached_bundle.clear()
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)


def test_no_network_on_load(app, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("replay must not touch the network")

    monkeypatch.setattr(requests, "get", refuse)
    app.run()
    assert not app.exception


def test_live_fetch_leaves_replay_unchanged(app, monkeypatch):
    monkeypatch.setattr(requests, "get", fake_get)
    app.run()
    before = [(m.label, m.value) for m in app.metric]
    app.button(key="live-fetch").click().run()
    assert not app.exception
    after = [(m.label, m.value) for m in app.metric]
    assert after[: len(before)] == before
    assert ("Reported category", "VFR") in after
