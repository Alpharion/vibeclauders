"""Release gates must preserve the previous artifact when checks or inputs change."""
import json
from pathlib import Path

import pytest

from tests.delivery.test_package import tree, put
from tools.delivery import package, verify_release


def install_successful_checks(monkeypatch, callback=None):
    def execute(name, command, cwd, work, env):
        if callback:
            callback(name, cwd)
        return {"name": name, "exit_code": 0}
    monkeypatch.setattr(verify_release, "execute", execute)
    monkeypatch.setattr(verify_release, "version", lambda name: "test")


def test_missing_estimate_preserves_previous_release(tree, monkeypatch):
    output = tree / "output/delivery" / (package.PREFIX + ".zip")
    output.write_bytes(b"previous release")
    install_successful_checks(monkeypatch)
    assert verify_release.verify(tree) == 1
    assert output.read_bytes() == b"previous release"
    report = json.loads((tree / "output/delivery/verification.json").read_bytes())
    assert report["status"] == "failed"
    assert any("capacity_estimate" in b for b in report["blockers"])


@pytest.mark.parametrize("where", ["source", "extracted"])
def test_runtime_mutation_blocks_release(tree, monkeypatch, where):
    def mutate(name, extracted):
        if name == "app_smoke":
            put(tree if where == "source" else extracted, "src/new.py", b"mutated")
    install_successful_checks(monkeypatch, mutate)
    assert verify_release.verify(tree, baseline=True) == 1
    assert not (tree / "output/delivery" / (package.PREFIX + ".zip")).exists()
    report = json.loads((tree / "output/delivery/verification.json").read_bytes())
    assert not report["runtime_unchanged"]


def test_final_build_rechecks_before_replacing_archive(tree, tmp_path, monkeypatch):
    output = tmp_path / "release.zip"
    package.build(tree, output)
    original = output.read_bytes()
    fingerprint = package.runtime_fingerprint(package.collect(tree)[0])
    real_verify = package.verify_archive
    def mutate_after_archive(path):
        result = real_verify(path)
        put(tree, "src/late.py", b"late mutation")
        return result
    monkeypatch.setattr(package, "verify_archive", mutate_after_archive)
    with pytest.raises(package.PackageError, match="changed before release"):
        package.build(tree, output, expected_fingerprint=fingerprint)
    assert output.read_bytes() == original


def test_baseline_success_is_explicitly_scoped(tree, monkeypatch):
    install_successful_checks(monkeypatch)
    assert verify_release.verify(tree, baseline=True) == 0
    report = json.loads((tree / "output/delivery/verification.json").read_bytes())
    assert report["scope"] == "baseline_runtime"
    manifest = package.verify_archive(tree / "output/delivery" / (package.PREFIX + ".zip"))
    assert manifest["verification_status"] == "verified"


def test_final_publication_failure_records_failed_status(tree, monkeypatch):
    install_successful_checks(monkeypatch)
    original_build = verify_release.build
    output = tree / "output/delivery" / (package.PREFIX + ".zip")
    output.write_bytes(b"previous release")
    def fail_final(*args, **kwargs):
        if kwargs.get("expected_fingerprint"):
            raise package.PackageError("late mutation")
        return original_build(*args, **kwargs)
    monkeypatch.setattr(verify_release, "build", fail_final)
    assert verify_release.verify(tree, baseline=True) == 1
    assert output.read_bytes() == b"previous release"
    report = json.loads((tree / "output/delivery/verification.json").read_bytes())
    assert report["status"] == "failed"
    assert "late mutation" in report["blockers"][-1]
    assert "Status: **failed**" in (tree / "output/delivery/VERIFICATION.md").read_text()


def test_failed_check_is_never_waived_by_baseline_mode(tree, monkeypatch):
    install_successful_checks(monkeypatch)
    monkeypatch.setattr(verify_release, "execute", lambda name, *args:
                        {"name": name, "exit_code": 7 if name == "app_smoke" else 0})
    assert verify_release.verify(tree, baseline=True) == 1
    assert not (tree / "output/delivery" / (package.PREFIX + ".zip")).exists()
