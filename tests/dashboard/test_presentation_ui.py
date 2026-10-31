from streamlit.testing.v1 import AppTest


def test_missing_movement_forecasts_and_schedules_stay_unknown():
    app = AppTest.from_string("""
import pandas as pd
from src.dashboard.replay import traffic_tiles
from src.dashboard.outputs import MovementForecasts
from src.dashboard.views import Snapshot, resolve_airport
traffic_tiles(None, Snapshot(resolve_airport("KATL"), pd.Timestamp("2025-07-12T20:00:00Z"), 3), MovementForecasts())
""").run()
    assert not app.exception
    text = " ".join(x.value for x in app.markdown)
    assert "Needs both incoming and outgoing forecasts" in text
    assert "No schedule at the target hour" in text
    assert ">0<" not in text


def test_component_registration_survives_separate_app_runtimes():
    script = """
from src.dashboard.components import watchlist
watchlist([], "watchlist", lambda: None)
"""
    for _ in range(2):
        app = AppTest.from_string(script).run()
        assert not app.exception
