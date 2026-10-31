"""Test an extracted snapshot and record evidence; never waive failing checks."""
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from tools.delivery.package import (PREFIX, build, collect, digest, git_state, json_bytes,
                                    runtime_fingerprint, verify_archive, PackageError)


def release_blockers(checks, publications, changed, baseline=False):
    blockers = [f"{c['name']} exited {c['exit_code']}" for c in checks if c["exit_code"] != 0]
    if changed:
        blockers.append("Runtime changed during verification; rerun against a stable tree")
    if not baseline:
        expected = {f"artifacts/capacity_estimate/{name}" for name in
                    ("forecast.parquet", "evaluation.json", "assumptions.json", "model.json")}
        estimate = next((p for p in publications if p["manifest"] == "artifacts/capacity_estimate/manifest.json"), None)
        if estimate is None or estimate["status"] not in ("available", "partial") or not expected <= set(estimate["payloads"]):
            blockers.append("Usable capacity_estimate publication with all four payloads is required")
    return blockers


def execute(name, command, cwd, work, env):
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=600)
        code, output = result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired as error:
        code, output = 124, f"Check exceeded 600 seconds: {error}"
    except OSError as error:
        code, output = 125, str(error)
    log = work / f"{name}.log"
    log.write_text(output, encoding="utf-8")
    record = {"name": name, "command": command[1:], "exit_code": code,
              "elapsed_seconds": round(time.monotonic() - started, 2),
              "log": str(log), "log_sha256": digest(log.read_bytes())}
    print(json.dumps(record), flush=True)
    return record


def verify(root, baseline=False):
    root = root.resolve()
    logroot = root / "output/delivery/logs"
    logroot.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="release-", dir=logroot))
    files, publications = collect(root)
    before = runtime_fingerprint(files)
    receipt = build(root, work / "tested.zip")
    manifest = verify_archive(work / "tested.zip")
    if manifest["runtime_fingerprint"] != before:
        raise ValueError("Source changed while building the verification snapshot")
    with ZipFile(work / "tested.zip") as archive:
        archive.extractall(work / "extracted")
    extracted = work / "extracted" / PREFIX
    extracted_files, _ = collect(extracted)
    if runtime_fingerprint(extracted_files) != before:
        raise ValueError("Extracted runtime differs from the source snapshot")
    temp = work / "temp"
    temp.mkdir()
    env = dict(os.environ, TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp), PYTHONIOENCODING="utf-8",
               DASHBOARD_DATA_ROOT=str(extracted))
    # Do not inherit a module override pointing back into the original checkout.
    env.pop("PYTHONPATH", None)
    commands = [
        ("risk_verify", [sys.executable, "-m", "src.flight_risk", "verify"]),
        ("full_suite", [sys.executable, "-m", "pytest", "tests", "-q", "--tb=short",
                        "--basetemp", str(work / "pytest"), "--junitxml", str(work / "pytest.xml")]),
        ("app_smoke", [sys.executable, "-m", "tools.delivery.smoke_app", "--report", str(work / "app.json")]),
    ]
    checks = [execute(name, command, extracted, work, env) for name, command in commands]
    if (work / "pytest.xml").exists():
        suites = ET.parse(work / "pytest.xml").getroot().iter("testsuite")
        counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
        for suite in suites:
            for key in counts:
                counts[key] += int(suite.get(key, 0))
        counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
        checks[1]["test_counts"] = counts
    if (work / "app.json").exists():
        checks[2]["app_result"] = json.loads((work / "app.json").read_bytes())
    after = runtime_fingerprint(collect(root)[0])
    extracted_after = runtime_fingerprint(collect(extracted)[0])
    blockers = release_blockers(checks, publications, before != after or before != extracted_after, baseline)
    report = {"schema_version": "1.0", "status": "failed" if blockers else "verified",
        "scope": "baseline_runtime" if baseline else "combined_runtime",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "source": git_state(root),
        "runtime_fingerprint": before, "runtime_unchanged": before == after == extracted_after,
        "tested_archive": receipt, "checks": checks, "blockers": blockers,
        "publications": publications,
        "environment": {"python": platform.python_version(), "packages": {p: version(p) for p in
            ("streamlit", "pandas", "numpy", "plotly", "scikit-learn", "pytest")}},
        "manual_acceptance": "pending",
        "limitations": ["Runtime verification is not judge/supervisor acceptance or a claim of model accuracy.",
            "Browser radar/basemap availability and the three-minute presentation require manual review.",
            "No clean environment install, public data refresh, retraining or operational benefit simulation performed.",
            "Baseline mode does not require the optional capacity estimate; it cannot certify the combined release."]}
    (root / "output/delivery/verification.json").write_bytes(json_bytes(report))
    lines = ["# Current delivery verification", "", f"UTC: {report['generated_at_utc']}",
             f"Status: **{report['status']}**; scope: **{report['scope']}**; manual acceptance: **pending**.",
             f"Runtime fingerprint: `{before}`.", "", "Checks ran in a fresh package extraction.", "",
             "| Check | Exit | Result |", "|---|---:|---|"]
    for c in checks:
        result = json.dumps(c.get("test_counts", c.get("app_result", {}).get("status", "See verification.json")))
        lines.append(f"| {c['name']} | {c['exit_code']} | {result} |")
    lines += ["", "## Release blockers", ""] + ["- " + b for b in (blockers or ["No automated blocker; manual acceptance remains pending."])]
    lines += ["", "## Limits", ""] + ["- " + x for x in report["limitations"]]
    lines += ["", "This report supersedes earlier runtime evidence. The previous Member 2 sprint results remain historical.",
              "Failed checks never replace the last release ZIP. See logs for the tested candidate archive.",
              "After successful checks and documentation freeze, rebuild; its receipt records the final commit and ZIP hash.", ""]
    (root / "output/delivery/VERIFICATION.md").write_text("\n".join(lines), encoding="utf-8")
    if not blockers:
        try:
            final = build(root, expected_fingerprint=before)
            verify_archive(Path(final["archive"]))
            print(json.dumps({"final_archive": final}, indent=2), flush=True)
        except (PackageError, OSError) as error:
            blockers.append(f"Final release publication failed: {error}")
            report["status"] = "failed"
            report["runtime_unchanged"] = False
            (root / "output/delivery/verification.json").write_bytes(json_bytes(report))
            lines[3] = f"Status: **failed**; scope: **{report['scope']}**; manual acceptance: **pending**."
            lines += ["", "Final publication blocker: " + str(error)]
    (root / "output/delivery/VERIFICATION.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": report["status"], "scope": report["scope"], "blockers": blockers}, indent=2))
    return 1 if blockers else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--baseline", action="store_true", help="Permit absence of the estimate, but never waive test/app failures")
    args = parser.parse_args()
    return verify(args.root, args.baseline)


if __name__ == "__main__":
    raise SystemExit(main())
