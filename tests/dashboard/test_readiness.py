from pathlib import Path
import json
import pytest

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.dashboard.readiness import capacity_rmse, impact_text, relative_error_reduction
from src.dashboard.views import Snapshot, resolve_airport

ROOT = Path(__file__).resolve().parents[2]
SNAP = Snapshot(resolve_airport("KATL"), pd.Timestamp("2025-07-12T20:00:00Z"), 3)


def test_capacity_table_uses_only_published_test_proxy_rmse():
    doc = json.loads((ROOT / "artifacts/capacity_estimate/evaluation.json").read_text())
    table = capacity_rmse(doc)
    assert len(table) == 6
    assert table.iloc[0]["Model proxy RMSE"] == 22.666040042788282
    assert capacity_rmse(None).empty
    assert capacity_rmse({"metrics": [{"split": "test", "metric": "other"}]}).empty


def test_impact_exact_airport_lead_and_zero_baseline():
    doc = json.loads((ROOT / "artifacts/risk/evaluation.json").read_text())
    text = impact_text(doc, SNAP)
    assert "456 alerts" in text and "52.2%" in text and "43.2%" in text
    assert impact_text(doc, Snapshot(resolve_airport("KATL"), SNAP.asof_utc, 9)) is None
    doc["impact"]["comparisons"][0]["baseline_recall"] = 0
    assert "relative change" not in impact_text(doc, SNAP)


def test_visible_evidence_real_publication():
    script = """
from pathlib import Path
import pandas as pd
from src.dashboard.data import load_bundle
from src.dashboard.views import Snapshot, resolve_airport
from src.dashboard.readiness import render_readiness
render_readiness(load_bundle(Path.cwd()), Snapshot(resolve_airport('KATL'), pd.Timestamp('2025-07-12T20:00:00Z'), 3))
"""
    app = AppTest.from_string(script).run(timeout=30)
    assert not app.exception
    assert len(app.dataframe[0].value) == 6
    assert any("estimate-capacity --from-published" in x.value for x in app.code)
    assert any("No LLM" in x.value for x in app.markdown)
    visible = " ".join(x.value for x in app.markdown)
    assert "not percent accuracy" in visible
    assert "90th-percentile frontier" in visible and "at least 30" in visible
    assert "Pinball loss" in visible and "Brier score" in visible
    assert len(app.latex) == 2
    assert "Acquire distinct populations" in visible and "Publish and validate" in visible
    assert any("--cache-only" in item.value for item in app.code)
    assert any("recorded producer command" in item.value for item in app.caption)
    assert "1.71%" in visible
    assert any("80.0" in x.value and "476" in x.value for x in app.markdown)


def test_relative_rmse_reduction_is_not_percent_accuracy():
    assert relative_error_reduction(8, 10) == pytest.approx(20)
    assert relative_error_reduction(12, 10) == pytest.approx(-20)
    assert relative_error_reduction(0, 10) == pytest.approx(100)
    for model, baseline in [(0, 0), (1, None), (1, float("nan")), (float("inf"), 2), (-1, 2), (True, 2)]:
        assert relative_error_reduction(model, baseline) is None
    doc = {"metrics": [{"split": "test", "metric": "high_demand_throughput_rmse", "airport": "KATL", "horizon_hours": 3, "n": 4, "value": 1, "baseline_value": 0}]}
    assert capacity_rmse(doc)["RMSE reduction vs baseline (%)"].isna().all()
