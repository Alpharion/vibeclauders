# Member 1 handoff: public data and airport-capacity modelling

## Start prompt

> You are Member 1. Implement the public-data and capacity subsystem described in `implementation-plan.md`, `handover/shared-contract.md` and this handoff, in that order. The shared contract is authoritative for artifact schemas. Member 2 is being implemented in the original chat; Member 3 handles dashboard and integration in a separate team-supervised chat. Your assigned team member monitors this work. Work only in your owned paths, publish real interoperable artifacts early, and report blockers to your supervisor without stopping independent work. Do not implement another member's subsystem or send messages to sponsors or third parties.

Workspace: `C:/Users/simho/OneDrive/Documents/ChatGPT/vibeClaude`.

Read `handover/README.md` for reporting and acceptance. Check existing artifacts and manifests before assuming that a capability is complete or compatible.

## Outcome and ownership

Deliver reproducible public-data acquisition, canonical flights, cutoff-safe weather features and a genuine hourly Airport Arrival Acceptance Rate (AAR) model for KATL/KDFW at scored horizons 3, 6 and 12 hours. Keep airport configuration reusable; the demonstration remains restricted to ATL and DFW.

You own:

- `src/data_capacity/` and `tests/data_capacity/`.
- `data/public/`, `data/processed/` and `artifacts/capacity/`.
- `handover/status-member-1.json` and your final handoff evidence.

Member 3 owns `src/shared.py`, the airport registry, root dependencies and application code. Member 2 owns `src/flight_risk/` and `artifacts/risk/`. Request interface/dependency changes through your supervisor. Preserve raw source files and the existing `src.shared.flight_key` identity algorithm; verify IDs match Member 2 before publishing canonical flights.

## Verified starting evidence

- Brief: `C:/Users/simho/Downloads/Autonomous SG 2026_Airbus Track.pdf`; Challenge 5 on physical pages 5-6, rubric on 7-8.
- `data/weather/Flight_Data_With_Weather_Final.csv` has 148,273 rows and 123 columns, 2023-01-01 through 2025-07-31; 25,299 rows touch ATL or DFW.
- It has no genuine AAR/ADR target, wind direction, or weather issue/validity timestamps. Its historical weather is not automatically safe at an earlier cutoff.
- Traffic is sampled, not complete airport demand. It cannot establish initial backlog or runway capacity.
- Inspect current artifacts and dependencies at startup; do not repeat old claims that a package is installed or that no model exists without checking.

## Critical path

### 1. Verify access and usable overlap first

Within 20 minutes, publish `artifacts/capacity/data_access.json` and a supervisor update with actual source access results, sample schemas, date coverage, retrieval methods and blockers. A useful gate result is a genuine AAR extract overlapping historical forecasts and flight dates, not a provider landing page.

Seek facility-set AAR and verify its definition. Distinguish it from actual arrival throughput and rates reduced by a Ground Delay Program. Record the chosen label definition. If quarter-hour records contain hourly rates, time-weight them according to the source specification rather than summing four rates.

| Source | Use | Evidence to record |
|---|---|---|
| FAA ASPM, `https://www.aspm.faa.gov/` | Genuine AAR; optional ADR, demand and counts | Actual export/access result, field definition, units, coverage and restrictions |
| IEM TAF, `https://mesonet.agron.iastate.edu/request/taf.php` | Archived issued forecasts | Issue/availability/validity times, amendments and condition groups |
| IEM observations, `https://mesonet.agron.iastate.edu/request/download.phtml` | Historical METAR | Observation/availability times, station, units and raw reference |
| BTS, `https://www.transtats.bts.gov/` | Automatic public flight ingestion | Query/download, coverage, stable keys; BTS alone does not prove complete airport demand |
| NOAA, `https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/` | Retrospective storm annotation | Event location/time and provenance; never a post-event predictor |

Use bounded request timeouts, limited retries/backoff, cache reuse and explicit failed/partial-download records. Validate content before replacing a good cache. Record source URL/query, retrieval time, hash, units, publication-latency assumptions and value type. A source labelled automatic must not require manual browser steps.

If genuine AAR is inaccessible, report an unmet core requirement immediately. Give your supervisor a precise requested extract/schema/date window so they can seek sponsor help. Do not contact a sponsor yourself. Continue flights, public weather and features for Member 2. Publish unavailable capacity status; never substitute sampled counts, fixed heuristics or synthetic AAR and claim measured capacity performance.

### 2. Publish an early vertical slice

By minute 45, publish canonical flights and a representative real weather-feature slice for an agreed airport/cutoff/target hour, or explicit unavailable states with specific causes. Do not wait for every source or all years to unblock integration.

- Preserve original local flight dates and scheduled times for identity and temporal splits. Resolve overnight/2400 times conservatively; flag ambiguous/nonexistent local times.
- Use the shared registry for IATA/ICAO/timezone/runway metadata. Missing metadata produces an unsupported-airport result, not a guessed default.
- Separate gate timestamps from runway timestamps.
- Publish duplicate, missing-record and coverage counts; dropped records must not silently change denominators.

### 3. Build cutoff-safe weather features

Use the shared contract's common hourly cutoffs and target keys. A scored horizon of 3 means the target interval starts three hours after cutoff; flights in that hour have three to four hours of lead time. Do not mix this with exact per-flight cutoffs or cumulative traffic windows.

- Select only information available at or before cutoff. Forecast validity must cover the target or the explicitly documented aggregation within it.
- Preserve issuance and availability where known. Disclose publication-latency assumptions when only issuance is archived.
- Select amendments as of cutoff; later amendments must not rewrite earlier snapshots.
- Preserve prevailing/FM/BECMG/TEMPO/PROB groups, conditional probabilities and intervals. Temporary conditions must not silently replace prevailing weather.
- Compute crosswind/tailwind from meteorological direction and fixed challenge headings ATL 080 degrees / DFW 180 degrees. Contract features `crosswind_kt` and `tailwind_kt` are nonnegative magnitudes: use absolute crosswind and zero-clipped tailwind, not signed crosswind/headwind. `precip_flag` and `thunderstorm_flag` are 0/1 when known and null when unknown. Document units, sign convention, calm/variable winds. Missing direction is unknown, not zero crosswind.
- Include visibility, ceiling, gusts and precipitation/thunderstorm indicators when supported, with feature missingness and provenance.
- Use NOAA storms only for retrospective event/evaluation cohorts, never as advance forecasts.

### 4. Fit and evaluate capacity

Use a modest pooled tree model and airport/hour baseline. Both models follow chronological train 2023, validate 2024, test January-July 2025. Fit preprocessing and baseline averages only on training data; model/uncertainty tuning uses validation only. All horizons of a flight stay in the same whole-date split. Exclude replay cutoffs preceding the latest information used in model/threshold selection; a January target can otherwise create a December cutoff that predates selection completion.

If labels cannot support those dates, propose one explicit whole-date chronological fallback to the supervisor and Member 2 before reporting comparable joint results. Record exact dates/coverage. Do not silently use random row splits or claim the original test period was evaluated.

Report genuine-label RMSE in flights/hour by airport/horizon, baseline RMSE, sample counts, label definition, missingness and weather-event cohort results. Show a poor/uncertain prediction with its evidence. For uncertainty bounds, document the method and empirical coverage; otherwise leave bounds unavailable.

Decision support additionally needs a contiguous hourly planning series at one cutoff. Three isolated +3/+6/+12 points cannot drive an hourly queue. Export the necessary series only when supported, without silently filling gaps. AAR serves arrivals; ADR is separate. Queue-compatible capacity includes `label_kind=facility_aar`, `features_available_at_utc<=asof_utc`, `model_train_end_utc<=asof_utc` and `model_selection_end_utc<=asof_utc`; a recent artifact-generation timestamp is permitted for retrospective inference.

Initial backlog must be observed at the cutoff or reconstructed by an explicitly validated method. Do not reuse stale backlog as current or turn unknown backlog into zero. Both demand and backlog require `population` and `coverage='complete'` for the same named traffic population before queue use; sample schedules cannot become complete demand just because every sampled row was processed.

## Required publications

Exact columns, keys, enums and readiness rules are in `handover/shared-contract.md`.

| Artifact | Purpose |
|---|---|
| `data/processed/flights.parquet` | Stable flights, schedules, labels and coverage |
| `data/processed/provenance.json` | Sources, acquisition status and coverage |
| `artifacts/capacity/weather.parquet` | Decoded weather, timing and condition groups |
| `artifacts/capacity/weather_features.parquet` | Cutoff-safe engineered features for both models |
| `artifacts/capacity/forecast.parquet` | Genuine AAR-model predictions when available |
| `artifacts/capacity/evaluation.json` | Measured results, baselines, splits and failure cases |
| `artifacts/capacity/data_access.json` | Access gate and later changes |
| `artifacts/capacity/manifest.json` | Run, schema, files, coverage, readiness and hashes |
| `data/processed/arrival_demand.parquet` | Verified as-of demand and coverage, if obtainable |
| `data/processed/initial_backlog.parquet` | Evidenced cutoff queue state, if obtainable |
| `data/processed/eligible_flights.parquet` | Optional as-of flight state/eligibility |

Demand/backlog/eligibility may be unavailable. Do not manufacture them to unlock advice. Publish schema `2.0`, run ID and generation time. Write complete artifacts atomically and publish the manifest last. Missing numbers are null, not zero; consumers must never load half-written output or mixed runs.

### Manifest linkage required by the implemented Member 2 CLI

`artifacts/capacity/manifest.json` must contain `schema_version="2.0"`, a nonempty `run_id` and an `artifact_hashes` object mapping **manifest-directory-relative paths** to the SHA256 of the exact published bytes. The keys are not relative to the workspace. Every input consumed by Member 2 must be declared. This is a format excerpt, not real evidence; replace placeholders with actual run identity and 64-character SHA256 values, and include the contract's other metadata/row counts:

```json
{
  "schema_version": "2.0",
  "run_id": "actual-member-1-publication-id",
  "artifact_hashes": {
    "../../data/processed/flights.parquet": "actual-sha256-of-canonical-flights",
    "weather_features.parquet": "actual-sha256-of-weather-features",
    "forecast.parquet": "actual-sha256-of-capacity-forecast",
    "../../data/processed/arrival_demand.parquet": "actual-sha256-of-demand",
    "../../data/processed/initial_backlog.parquet": "actual-sha256-of-backlog"
  }
}
```

Declare only files actually published; unavailable optional inputs remain absent with explicit capability reasons. Every published capacity row's `run_id` must equal this manifest's `run_id`. Changing any table requires its hash and publication metadata to be updated before the new manifest is released.

`python -m src.flight_risk train` auto-detects canonical flights and weather features. If either exists, it requires this valid manifest; an unverified present input is an error, not a reason to silently fall back to the sample. `decide` similarly verifies any present demand/capacity/backlog and rejects capacity rows from a different run.

The risk CLI trains from immutable copies of verified bytes in `artifacts/risk/input_snapshots/<snapshot-id>/`. Each copy bundle includes `provenance.json` linking original source paths, upstream manifest/run, snapshot paths and SHA256 values. For example, a flight source may be recorded as a cached `0-flights.parquet` path rather than the original canonical path; follow that provenance instead of treating the cache as a new data provider. Member 2 owns these snapshots; preserve the Member 1 source lineage and do not overwrite the cache.

## Commands and checks

Inspect the selected environment and record the result:

```powershell
python -c "import sys, pandas, numpy, sklearn, pyarrow, requests; print(sys.executable); print(pandas.__version__, sklearn.__version__)"
```

Implement and document a repeatable package CLI for acquisition/preparation/training, with `--help`, configurable airports/date range/cache and cached-data mode. Record actual supported commands in your status/final handoff; do not claim a future CLI already works. Required subsystem check once tests exist:

```powershell
python -m pytest tests/data_capacity -q
```

Acceptance evidence:

- Cache reuse, network timeout/failure, malformed/partial downloads and inaccessible AAR.
- IDs matching Member 2; UTC, overnight and daylight-saving edge cases.
- Fixed-heading wind tests, calm/variable winds and missing direction.
- Future observations/amendments excluded; no test-label contribution to training/baselines.
- Both target airports and all scored horizons, with explicit gaps.
- Genuine AAR definition, aggregation, real RMSE/baselines/sample counts.
- Unique contract keys, atomic publication and missing optional operational inputs.

## Checkpoints and final handoff

Use `handover/status-member-1.json` with the format in `handover/README.md`. Report only checks actually run.

| Elapsed checkpoint | Deliverable |
|---|---|
| 20 minutes | Real AAR access decision, overlap feasibility, schema agreement and blockers |
| 45 minutes | Canonical flights and real feature slice, or precise unavailable evidence |
| 90-120 minutes | First genuine AAR forecasts/results when labels exist; features for Member 2 |
| 180 minutes | Validated artifacts, coverage gaps and repeatable cached run |
| 210 minutes | Feature freeze; defects and evidence only |
| 240 minutes | Final paths, commands, measured results, tests, failure case and blockers |

A blocker report states what failed, the affected requirement, evidence, work continuing and the supervisor's needed action. Final handoff lists changed paths, artifact run IDs, exact commands, real check results and unmet requirements. Do not claim overall challenge completion while AAR prediction is unavailable.
