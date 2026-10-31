# ATL/DFW flow-planning replay

A local Streamlit decision-support prototype for an airport flow planner (Airbus Challenge 5). At a historical cutoff it displays available weather, severe departure-delay probabilities, traffic context and retrospective evaluation. Advisories require human review; the application sends no operational instructions.

## Current delivery baseline

Implementation baseline: `737b468` (31 October 2026); original delivery contribution: `24d834b`. The readiness follow-up adds automated release verification, a separate controller review briefing and judging instructions. It does not consume Member 1's new work or modify the frontend, producers or published models.

**Known frontend regression:** the new reporting-carrier chart uses an annotated Plotly line with a pandas Timestamp and can raise a TypeError. Member 1 owns the fix. A verified package of this baseline is **not a fully working demo release**. See `output/delivery/VERIFICATION.md` and `verification.json` for measured results and verification scope.

The interface on main includes Overview, Weather, Traffic, Compare and Evaluation tabs, historical/live modes, radar/connections/flagged-flow map layers, condition-frequency heatmaps and reporting-carrier traffic charts. Those source files are preserved by Member 2.

## Run

Use a compatible Python environment; the model was published with Python 3.14.6 and the exact versions in `requirements-observed.txt`. That file is preserved, not regenerated from the packaging machine. A clean install was not performed during the delivery verification.

```text
python -m pip install -r requirements-observed.txt
python -m src.flight_risk verify
python -m streamlit run app.py
```

`DASHBOARD_DATA_ROOT` can select another artifact root. Replay predictions are historical backtests, not evidence that a forecast was issued in 2025. Live weather is separate. Browser map tiles require network access even when the local code and artifacts are packaged.

## Current capabilities and evidence

| Capability | Published evidence | Boundary |
|---|---|---|
| Canonical flights | `data/processed/flights.parquet`, 25,299 rows | Challenge sample, not complete airport demand |
| Weather and runway-relative wind | 147,002 decoded weather rows; 135,786 feature snapshots | Explicit availability assumptions; ATL heading 080, DFW 180 |
| Departure delay >45 min | 10,604 held-out predictions / 3,537 flights; 10,599 weather-enhanced and 5 schedule-only | Both airports, 3/6/12-hour leads; probabilities uncalibrated |
| Risk evaluation | `artifacts/risk/evaluation.json` | Chronological splits; matched weather comparison, alert workload, storm cohorts, failure cases |
| Normalised history | `artifacts/risk/normalized_metrics.parquet`, 1,891 rows | Sample cohorts; observed outcomes require reveal |
| Reporting-carrier traffic | `artifacts/capacity/traffic_hourly.parquet`, 90,524 rows / 31 BTS months | Reconstructed schedules; not complete cutoff demand |
| Observed-arrivals forecast | 30,465 rows in `throughput_forecast.parquet` | Forecast of reporting-carrier arrivals, not measured facility AAR; baseline UI does not load this forecast |
| Capacity/AAR estimation | Separate optional `artifacts/capacity_estimate/` publication planned by Member 1 | Absent on this branch; user expects model estimation, not waiting for organiser labels |
| Recorded facility AAR | Existing `forecast.parquet` is empty | No independent AAR observations/RMSE; do not relabel throughput as observed AAR |
| Queue, metering and flight rescheduling | Explicit unavailable decision; typed empty queue | Missing complete demand and cutoff backlog; no operational savings claimed |

At +3h, published risk precision/recall are 26.1%/52.2% for ATL and 23.5%/48.9% for DFW. Weather versus schedule-only average precision is 0.2620 versus 0.2496 (ATL), 0.2485 versus 0.2276 (DFW), on matched cohorts. Alert quality improvement does not establish reduced delays or fuel savings.

Capacity/data run: `m1-20261031T065014Z-eacdd5`. Risk run: `0949771a54bb4e49b4e215528eb5d46b`. Its frozen inputs refer to the earlier compatible upstream run; the current weather additions do not change the nine risk features. No retraining was performed for packaging.

## Build and verify a portable package

```text
python output/delivery/build-package.py
python output/delivery/build-package.py --verify output/delivery/challenge-5-implementation.zip
```

The builder includes runtime source/tests, Leaflet assets, configuration, both producer publications, processed inputs, frozen snapshots and current handoffs. It discovers optional new producer manifests automatically. Raw download caches, environments, Git metadata and previous release archives are excluded. Source provenance paths are retained as metadata; they are never followed outside the repository.

Outputs are ZIP, SHA256, payload manifest and receipt under `output/delivery/`. `--output PATH` changes the destination. `--reference-pdf PATH` optionally includes an additional reference PDF; no personal Downloads path is required. The repository reference directory is included when present.

Each archive contains a newly generated `BUNDLE_MANIFEST.json` and `BUNDLE_README.md`. Payload hashes identify content even for a dirty source tree. The builder validates bytes, not model accuracy or application acceptance. Execution evidence is tied to a runtime fingerprint and becomes stale when code/tests/dependencies/data change.

After extraction, from its `challenge-5-implementation` directory:

```text
python -m src.flight_risk verify
python -m pytest tests/flight_risk tests/delivery -q --basetemp=tmp/release-tests-01
python -m tools.delivery.smoke_app
```

Choose a fresh writable `--basetemp` per test invocation on restricted Windows environments. The full suite is `python -m pytest tests -q`; retain and report every failure, including the inherited chart defect. AppTest does not verify remote radar/basemap tiles.

## Work ownership and release

Use `handover/sprint-30min/README.md`, the two member prompts, `INTERFACE.md` and `ACCEPTANCE.md`. Older plans and handoffs are historical checkpoints where they conflict with that clarified sprint. Member 1 owns model estimation plus its existing-panel integration; Member 2 owns packaging/evidence. Supervisors merge in either order, rerun combined checks and rebuild the final package. No estimate or frontend fix is claimed complete by this branch.

## Controller review and judging

Generate a separate evidence-backed review brief without changing dashboard or queue outputs:

```text
python -m tools.delivery.controller_brief --airport KATL --asof 2025-07-12T20:00:00Z --lead 3
```

Read `output/delivery/CONTROLLER_BRIEF.md` and its JSON evidence. It ranks sampled departures crossing their own published risk thresholds and suggests human review of weather and airline/inbound-aircraft status. It reads no observed delay labels, requires exact snapshot matches, and does not issue metering, routing or rescheduling instructions. Empty coverage is unavailable; zero flags is not an airport all-clear.

The [three-minute demo](handover/JUDGING-DEMO.md) includes a real false alarm, measured baseline comparison and explicit capacity-estimation limitations. The [submission checklist](handover/SUBMISSION-CHECKLIST.md) records release and manual review requirements without invented sign-off.

## Repeatable combined verification

```text
python -m tools.delivery.verify_release
```

This tests a fresh package extraction and requires the capacity-estimate publication. It records actual results in `output/delivery/verification.json` and `VERIFICATION.md`; failed tests, app errors or changing runtime inputs return a nonzero exit and do not replace the last release ZIP. `--baseline` permits absence of the estimator but never waives failures. Successful automatic checks still require browser review and supervisor acceptance. A clean dependency install is not tested by this command.
