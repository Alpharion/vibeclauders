"""In-dashboard review brief: same content as the command-line brief, exact key only."""
from pathlib import Path

import pandas as pd
import pytest

from src.dashboard import outputs, views
from src.dashboard.data import load_bundle

ROOT = Path(__file__).resolve().parents[2]
ASOF = pd.Timestamp("2025-07-12T20:00:00Z")
pytestmark = pytest.mark.skipif(not (ROOT / "artifacts/risk/predictions.parquet").exists(), reason="no risk publication")


@pytest.fixture(scope="module")
def bundle():
    return load_bundle(ROOT)


def snap(lead=3, asof=ASOF, icao="KATL"):
    return views.Snapshot(views.resolve_airport(icao), asof, lead)


def test_dashboard_brief_matches_command_line(bundle):
    from tools.delivery.controller_brief import create_brief

    brief, text, reason = outputs.review_brief(bundle, snap())
    assert reason is None and brief["flagged_flights"] == 2
    cli = create_brief(ROOT, "KATL", ASOF.isoformat(), 3)
    assert brief["review_priorities"] == cli["review_priorities"]
    assert brief["evidence"]["predictions_sha256"] == cli["evidence"]["predictions_sha256"]
    assert text.startswith("# Controller review brief") and "460f3042c18b22443112" in text


def test_brief_has_no_outcomes_or_instructions(bundle):
    _, text, _ = outputs.review_brief(bundle, snap())
    for forbidden in ("dep_delay_min", "arr_delay_min", "cancelled", "severe_delay"):
        assert forbidden not in text
    assert "No capacity reduction, metering rate, flight time, routing or rescheduling is recommended." in text


def test_other_key_is_not_substituted(bundle):
    brief, text, reason = outputs.review_brief(bundle, snap(asof=ASOF + pd.Timedelta(hours=1)))
    assert brief is None and text is None and "exact cutoff" in reason


def test_missing_publication_gives_reason(tmp_path):
    brief, text, reason = outputs.review_brief(load_bundle(tmp_path), snap())
    assert brief is None and text is None and reason
