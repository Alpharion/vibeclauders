"""Published-run integrity: manifest hashes, run identity and contract envelope."""
import json

import pandas as pd
import pytest

from src.data_capacity.config import CAPACITY_DIR, REPO_ROOT
from src.data_capacity.io import sha256_file

MANIFEST = CAPACITY_DIR / "manifest.json"
pytestmark = pytest.mark.skipif(not MANIFEST.exists(), reason="no published run")


def load():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_hashes_and_rows_match():
    m = load()
    for o in m["outputs"]:
        p = REPO_ROOT / o["path"]
        assert p.exists(), o["path"]
        assert sha256_file(p) == o["sha256"], f"hash mismatch {o['path']}"
        if o["rows"] is not None:
            assert len(pd.read_parquet(p)) == o["rows"]


def test_artifact_hashes_are_manifest_relative():
    m = load()
    hashes = m["artifact_hashes"]
    assert len(hashes) == len(m["outputs"])
    assert "weather_features.parquet" in hashes and "../../data/processed/flights.parquet" in hashes
    for rel, digest in hashes.items():
        assert sha256_file(CAPACITY_DIR / rel) == digest, rel


def test_single_generation():
    m = load()
    for name in ("evaluation", "data_access"):
        rep = json.loads((CAPACITY_DIR / f"{name}.json").read_text(encoding="utf-8"))
        assert rep["run_id"] == m["run_id"] and rep["schema_version"] == "2.0"
    for name in ("weather_features.parquet", "weather.parquet"):
        assert set(pd.read_parquet(CAPACITY_DIR / name, columns=["run_id"]).run_id) == {m["run_id"]}


def test_envelope_and_capability_honesty():
    m = load()
    for k in ("schema_version", "run_id", "generated_at_utc", "status", "limitations", "missing_inputs"):
        assert k in m
    caps = m["capabilities"]
    if caps["aar_forecast"]["status"] != "available":
        assert m["status"] != "available" and m["missing_inputs"]
    for k in ("arrival_demand", "initial_backlog"):
        if caps[k]["status"] == "unavailable":
            assert not (REPO_ROOT / "data" / "processed" / f"{k}.parquet").exists()
