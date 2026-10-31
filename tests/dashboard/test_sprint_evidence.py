import json
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_available_experiment_is_separate_from_production():
    app = AppTest.from_string("""
from pathlib import Path
from types import SimpleNamespace
from src.dashboard.sprint_evidence import render_sprint_evidence
render_sprint_evidence(SimpleNamespace(root=str(Path.cwd())))
""").run(timeout=30)
    assert not app.exception
    assert len(app.dataframe[0].value) == 6
    text = " ".join(x.value for x in app.markdown)
    report = json.loads((Path.cwd() / "handover/full-bts-model-evidence.json").read_text())
    expected = "Passed experimental selection" if report['decision'].get('adopt') else "Rejected: retain the published model"
    assert expected in text
    assert "Training population:" in text
    assert any("Recent-delay history population:" in x.value for x in app.caption)


def test_invalid_experiment_never_looks_like_success(tmp_path):
    (tmp_path / "handover").mkdir()
    (tmp_path / "handover/full-bts-model-evidence.json").write_text(json.dumps({"decision": {}, "validation": []}))
    code = "from types import SimpleNamespace\nfrom src.dashboard.sprint_evidence import render_sprint_evidence\nrender_sprint_evidence(SimpleNamespace(root=" + repr(str(tmp_path)) + "))"
    app = AppTest.from_string(code).run(timeout=30)
    assert not app.exception
    assert not app.dataframe
    assert "unavailable or incomplete" in app.info[0].value
