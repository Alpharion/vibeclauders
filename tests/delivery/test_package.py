"""Delivery acceptance using small synthetic publications, never production mutation."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from tools.delivery.package import (PREFIX, ROOT_FILES, PackageError, build, collect, digest,
                                    json_bytes, runtime_fingerprint, verify_archive)


def put(root, name, data=b"fixture\n"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def publication(root, name, payloads):
    directory = root / "artifacts" / name
    hashes = {}
    for path, data in payloads.items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        hashes[path] = digest(data)
    return put(root, f"artifacts/{name}/manifest.json", json_bytes({
        "schema_version": "2.0", "run_id": name + "-synthetic", "status": "partial", "artifact_hashes": hashes}))


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "repo"
    for name in ROOT_FILES:
        put(root, name)
    put(root, "output/delivery/build-package.py")
    publication(root, "risk", {"model.joblib": b"synthetic-not-pickle", "../../data/processed/flights.parquet": b"synthetic"})
    put(root, "artifacts/risk/input_snapshots/frozen/flights.parquet", b"frozen")
    return root


def test_complete_portable_payload_preserves_model_requirements(tree, tmp_path):
    publication(tree, "capacity", {"weather.parquet": b"weather", "../../data/processed/provenance.json": b"{}"})
    put(tree, "data/public/raw-cache/secret.bin")
    put(tree, "src/__pycache__/junk.pyc")
    put(tree, "output/delivery/old.zip")
    record = build(tree, tmp_path / "bundle.zip")
    manifest = verify_archive(Path(record["archive"]))
    with ZipFile(record["archive"]) as archive:
        names = {n.removeprefix(PREFIX + "/") for n in archive.namelist()}
        assert {"artifacts/capacity/weather.parquet", "data/processed/flights.parquet",
                "data/processed/provenance.json", "artifacts/risk/input_snapshots/frozen/flights.parquet",
                ".streamlit/config.toml", "src/dashboard/static/leaflet.js", "src/dashboard/static/leaflet.css"} <= names
        assert archive.read(PREFIX + "/requirements-observed.txt") == (tree / "requirements-observed.txt").read_bytes()
        assert not any("raw-cache" in n or "__pycache__" in n or n.endswith("old.zip") for n in names)
    assert manifest["source"]["commit"] is None
    assert manifest["verification_status"] == "unverified_or_stale_execution_evidence"


def test_optional_estimate_is_discovered_without_base_changes(tree, tmp_path):
    initial, _ = collect(tree)
    assert not any("capacity_estimate" in p for p in initial)
    publication(tree, "capacity_estimate", {"forecast.parquet": b"new", "model.json": b"{}", "evaluation.json": b"{}"})
    result = build(tree, tmp_path / "optional.zip")
    manifest = verify_archive(Path(result["archive"]))
    assert any(p["run_id"] == "capacity_estimate-synthetic" for p in manifest["publications"])
    assert "artifacts/capacity_estimate/model.json" in {f["path"] for f in manifest["files"]}


@pytest.mark.parametrize("bad_path", ["../../../outside", "/absolute", "C:\\external\\data", "../../data/public/cache.csv"])
def test_manifest_cannot_import_outside_or_excluded_content(tree, bad_path):
    manifest = tree / "artifacts/risk/manifest.json"
    doc = json.loads(manifest.read_bytes())
    doc["artifact_hashes"] = {bad_path: "a" * 64}
    manifest.write_bytes(json_bytes(doc))
    with pytest.raises(PackageError):
        collect(tree)


@pytest.mark.parametrize("missing", [False, True])
def test_damaged_publication_does_not_replace_good_release(tree, tmp_path, missing):
    output = tmp_path / "release.zip"
    build(tree, output)
    original = output.read_bytes()
    model = tree / "artifacts/risk/model.joblib"
    if missing:
        model.unlink()
    else:
        model.write_bytes(b"corrupted")
    with pytest.raises(PackageError):
        build(tree, output)
    assert output.read_bytes() == original


def test_execution_evidence_is_bound_to_runtime_not_readme(tree, tmp_path):
    fingerprint = runtime_fingerprint(collect(tree)[0])
    put(tree, "output/delivery/verification.json", json_bytes({"runtime_fingerprint": fingerprint, "status": "baseline_verified_with_known_frontend_failure"}))
    put(tree, "README.md", b"new documentation")
    assert build(tree, tmp_path / "verified.zip")["verification_status"] == "baseline_verified_with_known_frontend_failure"
    put(tree, "src/new.py", b"changed code")
    assert build(tree, tmp_path / "stale.zip")["verification_status"] == "unverified_or_stale_execution_evidence"


def test_archive_verifier_rejects_tampering(tree, tmp_path):
    output = tmp_path / "release.zip"
    build(tree, output)
    with ZipFile(output) as original:
        payload = {n: original.read(n) for n in original.namelist()}
    payload[PREFIX + "/app.py"] = b"tampered"
    with ZipFile(output, "w", ZIP_DEFLATED) as altered:
        for name, data in payload.items():
            altered.writestr(name, data)
    with pytest.raises(PackageError, match="payload mismatch"):
        verify_archive(output)
