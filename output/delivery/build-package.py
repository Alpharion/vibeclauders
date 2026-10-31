"""Create a complete, byte-preserving snapshot of the current Challenge 5 work."""
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "output/delivery"
PREFIX = "challenge-5-implementation"
ARCHIVE = DEST / "challenge-5-implementation.zip"
PDF = Path("C:/Users/simho/Downloads/Autonomous SG 2026_Airbus Track.pdf")


def main():
    files = {}
    for name in ["app.py", "requirements.txt", "implementation-plan.md", ".streamlit/config.toml"]:
        path = ROOT / name
        if not path.is_file():
            raise FileNotFoundError(path)
        files[name] = path.read_bytes()
    for folder in ["src", "tests", "handover", "artifacts/risk", "data/weather", "data/reference"]:
        for path in sorted((ROOT / folder).rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or any(x in {"__pycache__", ".pytest_cache"} for x in relative.parts):
                continue
            if path.suffix in {".pyc", ".pyo", ".tmp"}:
                continue
            files[relative.as_posix()] = path.read_bytes()
    concepts = ROOT / "output/dashboard-concepts"
    for pattern in ["challenge-5-*.png", "*-prompt.txt"]:
        for path in sorted(concepts.glob(pattern)):
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    if PDF.is_file():
        files[f"reference/{PDF.name}"] = PDF.read_bytes()
    files["output/delivery/build-package.py"] = Path(__file__).read_bytes()
    libraries = ["streamlit", "pandas", "numpy", "plotly", "scikit-learn", "scipy", "pyarrow", "requests", "pytest", "joblib"]
    observed = "# Observed working environment; not a fresh-install lockfile.\n"
    observed += f"# Python {sys.version.split()[0]}; see BUNDLE_README.md for compatibility notes.\n"
    observed += "\n".join(f"{name}=={version(name)}" for name in libraries) + "\n"
    files["requirements-observed.txt"] = observed.encode("utf-8")
    readme = """# Challenge 5 implementation package

This is a snapshot of all currently available Challenge 5 implementation files.
It includes the local Member 2 implementation and existing dashboard, plus the
revised plan and externally supervised handoffs for Members 1 and 3.

## Start here

- `handover/agent-1-data-capacity.md`: Member 1 copy-ready start prompt and acceptance.
- `handover/agent-3-dashboard-integration.md`: Member 3 start prompt and integration fixes.
- `handover/README.md`: supervisor monitoring, checkpoints and change protocol.
- `handover/shared-contract.md`: authoritative schema version 2.0.
- `implementation-plan.md`: comprehensive approach, scope and priorities.
- `handover/member-2-results.md`: actual local results, tests and external dependencies.
- `handover/agent-2-flight-risk.md`: local subsystem runbook and refresh commands.

## Contents

`src/`, `app.py`, `.streamlit/`: source code and existing Streamlit configuration.
`tests/flight_risk/`: 85 checks passed in the source workspace at packaging time.
`artifacts/risk/`: trained model, held-out predictions, normalized history,
evaluation, manifests and explicit unavailable recommendation/queue artifacts.
`data/weather/`: complete supplied flight CSV and audit.
`data/reference/`: airport metadata.
`reference/`: original challenge PDF supplied by the user.
`output/dashboard-concepts/`: Challenge 5 design references, not screenshots of a completed UI.
`BUNDLE_MANIFEST.json`: SHA256 and size for every payload file except the manifest itself.

The archive excludes Git metadata, Python/test caches, temporary work, unrelated
Challenge 3 SAF data/designs and the mixed historical prompt log. It includes no
virtual environment or installed libraries. Source/artifact bytes are preserved.

## Commands after extraction

Open a terminal inside the extracted `challenge-5-implementation` folder. With a
compatible Python environment, run:

```powershell
python -m src.flight_risk verify
python -m pytest tests/flight_risk -q --basetemp=tmp/pytest-package-review-01
python -m streamlit run app.py
```

To retrain or refresh the selected decision snapshot:

```powershell
python -m src.flight_risk train
python -m src.flight_risk decide --airport KATL --asof 2025-07-15T12:00:00Z --window-hours 6
python -m src.flight_risk verify
```

Use a fresh workspace `--basetemp` for each test run. The decision command
truthfully produces an unavailable result while real capacity/demand/backlog are
missing. Training auto-detects Member 1 inputs; if present, their v2 capacity
manifest and matching hashes are required. Consult the Member 2 runbook.

## Runtime and relocation

`requirements-observed.txt` records the versions actually installed during the
successful run. It is not a complete transitive lockfile or evidence that a new
installation has been tested. The existing `requirements.txt` is preserved: its
pandas<3 constraint differs from the verified pandas 3.0.3 runtime. Member 3 owns
dependency reconciliation. Model manifests record Python and library versions;
use compatible versions or retrain before loading the trusted local model.

Code resolves project paths relative to its location. Some handoff instructions
and provenance reports retain original absolute Windows paths. After relocation,
use the extracted project root for commands; original paths in provenance are
historical metadata. They were not rewritten because artifact hashes must remain
valid. The packaging script's original PDF path may need adjustment to rebuild
on another computer; the PDF itself is already included under `reference/`.

## Capability status

Member 2's implementation is tested, with 10,604 schedule-only predictions from
3,537 held-out flights. It has no verified real weather features yet. Genuine AAR,
complete airport demand and cutoff backlog remain Member 1 dependencies. The
existing dashboard still needs Member 3's v2 target-hour and artifact integration.
The package is complete for the files currently implemented, not a claim that
the whole Challenge 5 application is finished. Read the results and handoffs
before demonstrating it as a weather-aware capacity forecasting system.
"""
    files["BUNDLE_README.md"] = readme.encode("utf-8")
    manifest = {
        "package": PREFIX,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "capability_status": "partial; schedule-only Member 2 outputs; Members 1/3 pending",
        "payload_files": len(files),
        "files": [{"path": name, "bytes": len(content), "sha256": sha256(content).hexdigest()}
                  for name, content in sorted(files.items())],
    }
    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
    files["BUNDLE_MANIFEST.json"] = manifest_bytes
    DEST.mkdir(parents=True, exist_ok=True)
    temp = ARCHIVE.with_suffix(".zip.tmp")
    with ZipFile(temp, "w", ZIP_DEFLATED, compresslevel=6) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(f"{PREFIX}/{name}", content)
    with ZipFile(temp) as archive:
        if bad := archive.testzip():
            raise RuntimeError(f"Archive CRC failed: {bad}")
        for item in manifest["files"]:
            actual = archive.read(f"{PREFIX}/{item['path']}")
            if sha256(actual).hexdigest() != item["sha256"]:
                raise RuntimeError(f"Archive content mismatch: {item['path']}")
    temp.replace(ARCHIVE)
    digest = sha256(ARCHIVE.read_bytes()).hexdigest()
    (DEST / "challenge-5-implementation.sha256").write_text(f"{digest}  {ARCHIVE.name}\n", encoding="ascii")
    (DEST / "package-manifest.json").write_bytes(manifest_bytes)
    (DEST / "PACKAGE_README.md").write_text(readme, encoding="utf-8")
    print(json.dumps({"archive": str(ARCHIVE), "file_count": len(files), "archive_bytes": ARCHIVE.stat().st_size,
                      "uncompressed_bytes": sum(map(len, files.values())), "sha256": digest}, indent=2))


if __name__ == "__main__":
    main()
