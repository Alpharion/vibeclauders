# Challenge 5 implementation package

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
