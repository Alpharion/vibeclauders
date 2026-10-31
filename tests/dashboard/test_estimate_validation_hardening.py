"""Consumer contract regressions; no model fitting or publication changes."""
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from src.dashboard.data import load_bundle
from tests.dashboard.test_capacity_estimate import estimate_table, publish_estimate, no_genuine_aar, snap
from src.dashboard import views


@pytest.mark.parametrize("field,value,message", [
    ("aar_pred", float("inf"), "aar_pred must be finite"),
    ("aar_pred", float("nan"), "aar_pred must be finite"),
    ("aar_pred", -1.0, "aar_pred must be finite"),
    ("support_n", float("inf"), "support_n must be finite"),
    ("support_n", float("nan"), "support_n must be finite"),
    ("support_n", -1, "support_n must be finite"),
    ("support_n", 1.5, "support_n must be finite"),
    ("support_n", True, "support_n must be finite"),
    ("population", "whole airport", "population must identify"),
    ("estimation_method", " ", "estimation_method must be nonempty"),
    ("assumptions_id", None, "assumptions_id must be nonempty"),
    ("model_version", "", "model_version must be nonempty"),
    ("validation_target", "facility_aar", "validation_target must identify"),
    ("uncertainty_kind", "", "uncertainty_kind must be nonempty"),
])
def test_rejects_invalid_usable_metadata(root, field, value, message):
    no_genuine_aar(root)
    publish_estimate(root, estimate_table(**{field: value}))
    bundle = load_bundle(root)
    assert bundle.table("capacity_estimate") is None
    assert message in bundle.problem("capacity_estimate")
    assert views.capacity_row(bundle, snap())[0] is None


@pytest.mark.parametrize("lower,upper", [(None, 100), (10, None), (-1, 100), (90, 100), (10, 50), (10, float("inf"))])
def test_rejects_invalid_claimed_bounds(root, lower, upper):
    publish_estimate(root, estimate_table(uncertainty_kind="claimed_interval", aar_lower=lower, aar_upper=upper))
    bundle = load_bundle(root)
    assert "bounds must be finite" in bundle.problem("capacity_estimate")


@pytest.mark.parametrize("document,field,value", [
    ("model", "model_version", "wrong"),
    ("model", "assumptions_id", "wrong"),
    ("assumptions", "assumptions_id", "wrong"),
    ("assumptions", "population", "whole airport"),
    ("assumptions", "method", {"name": "wrong"}),
    ("evaluation", "method", "wrong"),
    ("evaluation", "validation_target", "facility_aar"),
    ("evaluation", "label_kind", "facility_aar"),
    ("model", "status", "unavailable"),
    ("assumptions", "status", "unavailable"),
    ("evaluation", "status", "unavailable"),
])
def test_rejects_hashed_but_inconsistent_documents(root, document, field, value):
    publish_estimate(root)
    directory = root / "artifacts/capacity_estimate"
    path = directory / f"{document}.json"
    doc = json.loads(path.read_text())
    doc[field] = value
    path.write_text(json.dumps(doc))
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    # Update the fixture manifest declaration after deliberately changing metadata.
    hashes = manifest["outputs"]
    key = next(key for key in hashes if Path(key).name == path.name)
    entry = hashes[key]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if isinstance(entry, dict):
        entry["sha256"] = digest
    else:
        hashes[key] = digest
    manifest_path.write_text(json.dumps(manifest))
    bundle = load_bundle(root)
    assert bundle.table("capacity_estimate") is None
    expected = "is unavailable" if field == "status" else f"{field} differs from forecast"
    assert expected in bundle.problem("capacity_estimate")
    assert bundle.capability("Capacity estimate (proxy)").status == "unavailable"


def test_current_committed_publication_loads():
    bundle = load_bundle(Path(__file__).resolve().parents[2])
    assert bundle.table("capacity_estimate") is not None, bundle.problem("capacity_estimate")
    assert bundle.capability("Capacity estimate (proxy)").status in ("available", "partial")


@pytest.mark.parametrize("field", ["model_version", "assumptions_id", "estimation_method"])
def test_rejects_mixed_forecast_identifiers(root, field):
    table = estimate_table()
    table.loc[0, field] = "other-generation"
    publish_estimate(root, table)
    assert f"{field} differs within forecast" in load_bundle(root).problem("capacity_estimate")


def test_rejects_training_after_selection(root):
    from tests.dashboard import conftest as c
    table = estimate_table(model_train_end_utc=c.ASOF - pd.Timedelta(days=1))
    publish_estimate(root, table)
    assert "model_train_end_utc after model_selection_end_utc" in load_bundle(root).problem("capacity_estimate")


@pytest.mark.parametrize("document", ["model", "assumptions", "evaluation"])
def test_missing_document_withholds_forecast(root, document):
    no_genuine_aar(root)
    publish_estimate(root)
    (root / f"artifacts/capacity_estimate/{document}.json").unlink()
    bundle = load_bundle(root)
    assert bundle.table("capacity_estimate") is None
    assert "missing or rejected" in bundle.problem("capacity_estimate")
    assert views.capacity_row(bundle, snap())[0] is None


def test_unavailable_rows_may_have_null_estimate_and_zero_support(root):
    publish_estimate(root, estimate_table(status="unavailable", aar_pred=float("nan"), support_n=0))
    bundle = load_bundle(root)
    assert bundle.table("capacity_estimate") is not None
    assert views.estimate_row(bundle, snap())[0] is None
