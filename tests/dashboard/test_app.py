import ast
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard.app import cached_bundle
from tests.dashboard import conftest as c

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def run(monkeypatch):
    def start(root) -> AppTest:
        monkeypatch.setenv("DASHBOARD_DATA_ROOT", str(root))
        cached_bundle.clear()
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        assert not app.exception
        return app

    return start


def text(app) -> str:
    parts = [e.value for kind in ("markdown", "warning", "error", "info", "caption", "title", "success") for e in getattr(app, kind)]
    return "\n".join(map(str, parts))


def test_launch_with_no_artifacts(run, tmp_path):
    body = text(run(tmp_path))
    assert "Unavailable" in body and "No snapshot is published" in body


def test_launch_with_partial_artifacts(run, tmp_path):
    c.publish_risk(tmp_path)
    body = text(run(tmp_path))
    assert "Schedule risk: Available" in body and "AAR forecast: Unavailable" in body
    assert "Schedule-only model" in body


def test_launch_with_malformed_artifacts(run, root):
    (root / "artifacts/risk/predictions.parquet").write_bytes(b"garbage")
    (root / "artifacts/capacity/manifest.json").write_text("{")
    assert "Schedule risk: Unavailable" in text(run(root))


def test_valid_artifacts_and_selection_updates_panels(run, root):
    app = run(root)
    assert "Frozen" not in text(app) and "12:00 UTC" in text(app) and "Flights scored" in [m.label for m in app.metric]
    app.radio(key="horizon").set_value(12).run()
    assert "Unsupported selection" in text(app)
    assert "+12 h." in text(app)
    app.radio(key="horizon").set_value(6).run()
    app.selectbox(key="airport").set_value("KDFW").run()
    body = text(app)
    assert "DFW · Forecast picture" in body and "No decision output" in body


def test_outcomes_locked_until_reveal(run, root):
    app = run(root)
    assert "Turn on **Reveal outcomes**" in text(app)
    assert not any("dep_delay_min" in frame.value.columns for frame in app.dataframe)
    app.toggle(key="reveal").set_value(True).run()
    assert any("dep_delay_min" in frame.value.columns for frame in app.dataframe)


def test_decision_refused_on_window_change(run, root):
    app = run(root)
    app.number_input(key="window").set_value(3).run()
    assert "No decision output" in text(app)


def test_unavailable_decision_shows_missing_reasons(run, root):
    document = c.recommendations(status_note=None)
    document.update(status="unavailable", recommendations=[], missing_inputs=["capacity: unavailable"])
    c.publish_decision(root, table=c.queue().iloc[0:0], document=document)
    body = text(run(root))
    assert "queue is empty" in body and "Missing inputs" in body


def test_reload_after_new_run(run, root):
    app = run(root)
    c.publish_risk(root, table=c.predictions().assign(model_kind="weather_enhanced"))
    app.run()
    assert "Schedule-only model" not in text(app)


def test_app_has_no_transmission_paths():
    forbidden = {"requests", "urllib", "http", "socket", "smtplib", "httpx"}
    # live.py alone may read public weather; test_live.py pins it to GET.
    for path in set((ROOT / "src/dashboard").glob("*.py")) - {ROOT / "src/dashboard/live.py"}:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            assert not {n.split(".")[0] for n in names} & forbidden, path


def test_mixed_models_show_each_threshold_and_counts(run, tmp_path):
    table = c.predictions()
    table.loc[1, ["model_kind", "threshold"]] = ["weather_enhanced", 0.12]
    c.publish_risk(tmp_path, table=table)
    app = run(tmp_path)
    app.radio(key="horizon").set_value(6).run()  # f1 and f2 share only the +6 h key.
    assert "Schedule-only model** for 1 of 2 flights" in text(app)
    assert any(m.value == "0.120 / 0.150" for m in app.metric)
    assert "1 weather enhanced" in text(app)


def test_jump_to_published_decision_sets_cutoff_and_window(run, root):
    app = run(root)
    app.number_input(key="window").set_value(3).run()
    assert "No decision output" in text(app)
    jump = app.selectbox(key="jump-KATL")
    option = next(o for o in jump.options if o.startswith("Published decision"))
    jump.set_value(option).run()
    assert not app.exception
    assert app.number_input(key="window").value == 6
    assert "No decision output" not in text(app)
