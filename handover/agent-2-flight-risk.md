# Member 2 - local implementation and refresh runbook

Member 2 is owned by the original chat. External handoffs go to Members 1 and 3; this document records the local subsystem and how to refresh it after their work. Read `implementation-plan.md` and `handover/shared-contract.md` first. Actual results are in `handover/member-2-results.md`.

## Scope and delivered code

Owned code: `src/flight_risk/`; checks: `tests/flight_risk/`; generated outputs: `artifacts/risk/`. Do not edit Member 1 acquisition/data or Member 3 shared/UI/dependency files.

- `data.py`: canonical/sample loading, stable flight IDs, original-local-date splits, UTC handling, label exclusions and strict weather joins.
- `model.py`: train-only transformations, logistic regression/gradient boosting comparison, validation-only selection and threshold, historical-rate baseline.
- `metrics.py`: per-cohort classification/calibration diagnostics and daily UTC volume-normalized observed delays.
- `pipeline.py`: real training/evaluation, source/runtime provenance, held-out predictions, immutable run identity, atomic artifacts and manifest-last publication.
- `simulation.py`: arrival-only queue with complete-demand, authentic-capacity, cutoff-backlog, population and timing validation.
- `recommendations.py`: human-review advisory, unsupported flight timings/benefits withheld.
- `__main__.py`: repeatable train/decide/verify commands, exact-byte upstream verification and snapshot caching.

## Verified commands

Run from `C:/Users/simho/OneDrive/Documents/ChatGPT/vibeClaude` using the verified Python environment recorded in `artifacts/risk/manifest.json`.

```powershell
python -m src.flight_risk train
python -m src.flight_risk decide --airport KATL --asof 2025-07-15T12:00:00Z --window-hours 6
python -m src.flight_risk verify
python -m pytest tests/flight_risk -q --basetemp=tmp/pytest-member2-review-01
```

Use a fresh workspace `--basetemp` on each test invocation; the default temporary location has permission issues in this environment. Test fixtures are synthetic and confined to tests/tmp, never operational artifacts.

`train` automatically uses canonical flights and engineered weather if the standard files exist. Otherwise it trains a clearly labelled schedule-only baseline on the supplied CSV. Any external input requires `artifacts/capacity/manifest.json` declaring it in `artifact_hashes` with schema version 2.0 and run ID. Paths are relative to that manifest. Missing explicitly requested files are errors, not silent sample fallback.

The CLI hashes the same upstream bytes it consumes. Training snapshots are retained under `artifacts/risk/input_snapshots/<snapshot-id>/` with original-path and upstream-run provenance so concurrent Member 1 publication cannot change a model run mid-training. `decide` similarly loads verified bytes and requires capacity row run IDs to match the upstream manifest.

Optional flags: `--canonical`, `--weather-features`, `--input-manifest`, `--airport-registry`, `--output`. Registry JSON is an ICAO-keyed object containing at least IATA and timezone (plus heading for shared weather logic). The default demonstration stays KATL/KDFW.

## Temporal/target contract

Target `DEP_DELAY > 45`; exclude cancelled flights even if a numeric delay is present, missing labels, ambiguous schedules and duplicate keys. Train 2023, validate 2024, test January-July 2025 by original local flight date. Calendar features use scheduled local time; 2400 is next midnight but retains original date for splitting.

For departure 14:37Z and lead 6, target hour is 14:00Z and cutoff 08:00Z. Predictions target [14:00,15:00). The dashboard must not select [08:00,14:00) and expect those predictions. Test cutoffs before model selection completion are excluded. Schedules and label publication times are retrospective limitations explicitly recorded.

The weather consumer enforces available status, source IDs, aware timestamps, hourly keys, availability <= cutoff, finite supported measurements and duplicate rejection. Crosswind/tailwind are nonnegative knots; flags are 0/1. Member 1 must establish raw issue/validity/lineage before publishing engineered features. Missing weather does not authorize the use of undated CSV weather.

## Decision contract

For a W-hour queue, supply leads 0..W-1 for [cutoff,cutoff+W), all at one cutoff. Three isolated scored leads do not establish the intervening capacity. Required evidence: genuine facility AAR target/provenance, complete arrival demand, matching traffic population, known backlog at cutoff, model training/selection before cutoff and source availability before cutoff.

AAR serves arrivals only. The simulator conserves movements and floors hourly capacity to integer slots. Recovery outside the window is unresolved. Backlog area is an hourly simulation summary, not real delay minutes or benefit.

Supported advice requests human review of arrival metering or continued monitoring. It never fabricates revised flight times, airborne ground delays, fuel savings, diversion suitability or total-delay reductions. `recommendations.json` and `queue.parquet` have a separate `decision_manifest.json`; a selected decision run does not overwrite the model manifest.

## Refresh and integration handback

1. Member 1 supervisor verifies/publicizes a coherent v2 artifact bundle with hashes and actual coverage.
2. Member 3 runs `train`, then checks weather capability, matched test metrics and any exclusions. A successful command can still report partial capability.
3. Run `decide` for a real supported airport/cutoff/window. Missing queue prerequisites must produce an unavailable report and empty typed queue.
4. Run `verify` and the subsystem tests. Compare exact risk target hours and decision planning windows in the UI.
5. Display model/feature kind, sample coverage, normalized denominators and outcome-reveal flags. Show the held-out failure example only with outcome reveal.
6. Record actual refreshed run IDs/metrics, not numbers copied from the current sample run. Bring contract errors back to Member 2 with failing command/input keys and observed result.

Full Challenge 5 compliance remains dependent on genuine AAR/weather and integrated UI. Completion of this local subsystem does not close those external requirements.
