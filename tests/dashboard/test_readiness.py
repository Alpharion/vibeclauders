from pathlib import Path
import json

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.dashboard.readiness import capacity_rmse, impact_text
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
    assert any("80.0" in x.value and "476" in x.value for x in app.markdown)
