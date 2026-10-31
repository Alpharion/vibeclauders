"""Byte-preserving, manifest-backed delivery. Standard library only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

PREFIX = "challenge-5-implementation"
ROOT_FILES = ("app.py", "requirements.txt", "requirements-observed.txt", "README.md",
              ".gitattributes", ".gitignore", "implementation-plan.md", "parallel-plan.md",
              ".streamlit/config.toml", "src/dashboard/static/leaflet.js", "src/dashboard/static/leaflet.css")
TREES = ("src", "tests", "tools/delivery", ".streamlit", "handover", "data/processed",
         "data/weather", "data/reference", "reference")
EXCLUDED = {".git", ".aws", ".codex", ".env", "__pycache__", ".pytest_cache", ".venv", "venv", "tmp"}


class PackageError(ValueError):
    pass


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, allow_nan=False, ensure_ascii=False) + "\n").encode("utf-8")


def excluded(path: Path) -> bool:
    return bool(set(path.parts) & EXCLUDED) or path.suffix in {".pyc", ".pyo", ".tmp", ".log"}


def confined(root: Path, base: Path, name: str) -> Path:
    """Allow manifest-relative ../ paths only when their resolved target stays inside root."""
    name = str(name).replace("\\", "/")
    if PurePosixPath(name).is_absolute() or PureWindowsPath(name).drive:
        raise PackageError(f"Absolute manifest path is not portable: {name}")
    target = (base / name).resolve()
    if not target.is_relative_to(root):
        raise PackageError(f"Manifest path escapes repository: {name}")
    if excluded(target.relative_to(root)) or target.is_relative_to(root / "data/public"):
        raise PackageError(f"Manifest refers to excluded content: {name}")
    return target


def collect(root: Path) -> tuple[dict[str, bytes], list[dict]]:
    root = root.resolve()
    files: dict[str, bytes] = {}

    def add(path: Path):
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise PackageError(f"Payload symlink escapes repository: {path}")
        if not path.is_file():
            raise PackageError(f"Missing payload: {path}")
        key = path.relative_to(root).as_posix()
        content = path.read_bytes()
        if key in files and files[key] != content:
            raise PackageError(f"File changed during collection: {key}")
        files[key] = content

    for name in ROOT_FILES:
        add(root / name)
    for name in TREES:
        for path in sorted((root / name).rglob("*")):
            if path.is_file() and not excluded(path.relative_to(root)):
                add(path)
    add(root / "output/delivery/build-package.py")
    for name in ("verification.json", "VERIFICATION.md", "frozen-baseline.json",
                 "controller-brief.json", "CONTROLLER_BRIEF.md"):
        path = root / "output/delivery" / name
        if path.is_file():
            add(path)
    # Small access instructions are useful; raw download caches are not payloads.
    for name in ("README.md", "attempts.json"):
        path = root / "data/public/aspm" / name
        if path.is_file():
            add(path)

    publications = []
    for manifest_path in sorted((root / "artifacts").rglob("*manifest.json")):
        if excluded(manifest_path.relative_to(root)):
            continue
        add(manifest_path)
        key = manifest_path.relative_to(root).as_posix()
        manifest = json.loads(files[key])
        hashes = manifest.get("artifact_hashes")
        if manifest.get("schema_version") != "2.0" or not manifest.get("run_id") or not isinstance(hashes, dict) or not hashes:
            raise PackageError(f"Invalid publication manifest: {key}")
        payloads = []
        for name, expected in hashes.items():
            target = confined(root, manifest_path.parent, name)
            add(target)
            relative = target.relative_to(root).as_posix()
            if digest(files[relative]) != expected:
                raise PackageError(f"Publication hash mismatch: {relative}")
            payloads.append(relative)
        publications.append({"manifest": key, "run_id": manifest["run_id"], "status": manifest.get("status"),
                             "payloads": sorted(payloads), "capabilities": manifest.get("capabilities", {})})
    if not publications:
        raise PackageError("No producer publications found")
    # Frozen inputs are local replay evidence. Original absolute provenance paths are metadata only.
    for directory in sorted((root / "artifacts").rglob("input_snapshots")):
        for path in sorted(directory.rglob("*")):
            if path.is_file() and not excluded(path.relative_to(root)):
                add(path)
    return files, publications


def runtime_fingerprint(files: dict[str, bytes]) -> str:
    """Bind execution evidence to code, tests, dependencies and runtime inputs, excluding prose."""
    selected = {k: digest(v) for k, v in sorted(files.items()) if
                k.startswith(("src/", "tests/", "tools/delivery/", "artifacts/", "data/", ".streamlit/"))
                or k in {"app.py", "requirements.txt", "requirements-observed.txt", "output/delivery/build-package.py"}}
    return digest(json_bytes(selected))


def git_state(root: Path) -> dict:
    def git(*args):
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8")
        return result.stdout.strip() if result.returncode == 0 else None
    if not (root / ".git").exists():
        return {"commit": None, "dirty": None, "status": "not_a_git_checkout"}
    status = git("status", "--porcelain", "--untracked-files=all")
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(status) if status is not None else None,
            "status": status, "branch": git("branch", "--show-current")}


def readme(manifest: dict) -> bytes:
    lines = ["# Portable Challenge 5 replay package", "",
             f"Built: {manifest['created_at_utc']}", f"Source: `{manifest['source']['commit']}`; dirty: `{manifest['source']['dirty']}`.",
             f"Verification status: **{manifest['verification_status']}**.", "",
             "## Run after extraction", "", "Use the model-compatible versions recorded in requirements-observed.txt.",
             "A compatible installed Python environment is required; no environment is bundled.", "", "```text",
             "python -m src.flight_risk verify", "python -m pytest tests/flight_risk tests/delivery -q",
             "python -m streamlit run app.py", "```", "", "## Included publications", ""]
    for pub in manifest["publications"]:
        lines.append(f"- `{pub['manifest']}`: run `{pub['run_id']}`, status `{pub['status']}`, {len(pub['payloads'])} verified payloads.")
    lines += ["", "Runtime source, tests, Leaflet assets, processed inputs, frozen model snapshots, reference data,",
              "current handoffs and model-compatible requirements are included. BUNDLE_MANIFEST.json hashes every payload",
              "except itself. Original source paths in provenance are historical metadata and are not followed.", "",
              "## Verification and limitations", "",
              "The builder checks payload completeness and hashes; it does not run tests or certify frontend behaviour.",
              "Execution evidence, when present, is in output/delivery/verification.json. It is applicable only when",
              "its runtime fingerprint matches this package. Missing/stale evidence never implies a passing release.",
              "A recorded baseline frontend failure is not final demo acceptance. See README.md and the evidence report.",
              "Browser radar/basemap tiles need network access; AppTest does not verify those downloads.",
              "Observed-arrivals forecasts, model-estimated capacity and recorded facility AAR have different meanings.",
              "Only publications listed above are included; optional capacity estimates are not assumed to exist.",
              "Raw public download caches, virtual environments, Git metadata and prior release archives are excluded.",
              "requirements-observed.txt is preserved byte-for-byte; the builder's Python version is metadata, not a model lockfile.", ""]
    return "\n".join(lines).encode("utf-8")


def verify_archive(path: Path) -> dict:
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise PackageError("Duplicate archive paths")
        manifest = json.loads(archive.read(f"{PREFIX}/BUNDLE_MANIFEST.json"))
        expected = {f"{PREFIX}/BUNDLE_MANIFEST.json"}
        for item in manifest["files"]:
            relative = PurePosixPath(item["path"])
            if relative.is_absolute() or ".." in relative.parts or PureWindowsPath(item["path"]).drive or "\\" in item["path"]:
                raise PackageError("Unsafe archive path")
            name = f"{PREFIX}/{relative}"
            if name in expected:
                raise PackageError("Duplicate manifest path")
            expected.add(name)
            data = archive.read(name)
            if len(data) != item["bytes"] or digest(data) != item["sha256"]:
                raise PackageError(f"Archive payload mismatch: {name}")
        if set(names) != expected or archive.testzip() is not None:
            raise PackageError("Archive inventory/CRC mismatch")
        return manifest


def build(root: Path, destination: Path | None = None, reference_pdf: Path | None = None) -> dict:
    root = root.resolve()
    files, publications = collect(root)
    fingerprint = runtime_fingerprint(files)
    evidence = json.loads(files.get("output/delivery/verification.json", b"{}"))
    matched = evidence.get("runtime_fingerprint") == fingerprint
    evidence_status = evidence.get("status") if matched else "unverified_or_stale_execution_evidence"
    allowed = {"baseline_verified_with_known_frontend_failure", "verified", "failed"}
    status = evidence_status if evidence_status in allowed else "unverified_or_stale_execution_evidence"
    if reference_pdf is not None:
        files["reference/" + reference_pdf.name] = reference_pdf.read_bytes()
    manifest = {"package": PREFIX, "schema_version": "1.0", "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "source": git_state(root), "builder_python": platform.python_version(), "runtime_fingerprint": fingerprint,
                "verification_status": status, "execution_evidence_matches": matched, "publications": publications}
    files["BUNDLE_README.md"] = readme(manifest)
    manifest["files"] = [{"path": name, "bytes": len(data), "sha256": digest(data)} for name, data in sorted(files.items())]
    files["BUNDLE_MANIFEST.json"] = json_bytes(manifest)
    destination = (destination or root / "output/delivery" / f"{PREFIX}.zip").resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with ZipFile(temp, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            for name, data in sorted(files.items()):
                archive.writestr(f"{PREFIX}/{name}", data)
        verify_archive(temp)
        temp.replace(destination)
    finally:
        if temp.exists():
            temp.unlink()
    receipt = {"archive": str(destination), "sha256": digest(destination.read_bytes()), "payload_files": len(manifest["files"]),
               "archive_bytes": destination.stat().st_size, "source": manifest["source"], "runtime_fingerprint": fingerprint,
               "verification_status": status, "producer_runs": [p["run_id"] for p in publications]}
    destination.with_suffix(".sha256").write_text(f"{receipt['sha256']}  {destination.name}\n", encoding="ascii")
    destination.with_suffix(".manifest.json").write_bytes(json_bytes(manifest))
    destination.with_suffix(".receipt.json").write_bytes(json_bytes(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reference-pdf", type=Path, help="Optional extra PDF; no personal path is assumed")
    parser.add_argument("--verify", type=Path, help="Verify an existing ZIP without rebuilding")
    args = parser.parse_args()
    if args.verify:
        manifest = verify_archive(args.verify)
        print(json.dumps({"status": "passed", "payload_files": len(manifest["files"]), "runtime_fingerprint": manifest["runtime_fingerprint"]}, indent=2))
    else:
        print(json.dumps(build(args.root, args.output, args.reference_pdf), indent=2))


if __name__ == "__main__":
    main()
