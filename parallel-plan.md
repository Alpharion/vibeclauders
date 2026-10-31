# Challenge 5 remaining work: three parallel workstreams

> Historical work allocation and baseline. The current two-member scope is in `handover/sprint-30min/README.md`; current judging and release steps are in `handover/JUDGING-DEMO.md` and `handover/SUBMISSION-CHECKLIST.md`. Organiser AAR acquisition is not a prerequisite for the separately labelled capacity estimator. Preserve the historical evidence below rather than interpreting its old gates as current blockers.

Baseline: `origin/main` at `783639a` plus the uncommitted dashboard on branch `a`, checked on 31 October 2026. This plan covers remaining work only and replaces the schedule in `implementation-plan.md`. The rules in `implementation-plan.md` and `handover/shared-contract.md` still apply.

Times are hours from the team's restart (T+0). Change them if the submission deadline requires it.

## 1. Where the project stands

**Done, so not repeated here:** canonical flights, decoded weather, cutoff-safe weather features, storm events, the AAR training code, the weather-enhanced risk model (10,604 held-out predictions), normalised history, queue and advisory code, and the 20-character flight IDs on main.

| Remaining problem | Evidence | Rubric effect | Owner |
|---|---|---|---|
| No genuine AAR labels, so no AAR model or RMSE | 0 forecast rows; `data/public/aspm/` holds only a README | Core requirement unmet | M1 |
| Published hashes fail outside Windows | On Linux, `python -m src.flight_risk verify` errors and tests give 125 passed, 2 failed | Reproducibility | M1, M2 |
| Dashboard on `a` is not integrated with main | 10 files collide, including `src/shared.py`, which M1 and M2 depend on | End-to-end build | M3 |
| No storm-event evaluation for risk | `src/flight_risk` does not use `storm_events.parquet` | Honest evaluation | M2 |
| No before/after measure | No impact comparison is published | Impact (10%) | M2 |
| Traffic is a 0.8% sample | Sample median is 1 flight per replay key | Realism, usefulness | M1 |
| No demonstration beyond the two airports | Only KATL and KDFW are configured | Brief: avoid single-airport fit | All, separately |
| Demand and backlog are absent | Not published; a sample cannot supply them | Queue and advice stay unavailable | Reported by M3 |

## 2. Rules that keep the work parallel

### 2.1 One owner per path

Change only paths in your own row. Nothing in this plan needs two members in one file.

| Member | Branch | Owned paths |
|---|---|---|
| **M1: data and AAR** | `zeph` | `src/data_capacity/`, `tests/data_capacity/`, `data/public/`, `data/processed/`, `artifacts/capacity/`, `handover/status-member-1.json`, `handover/member-1-handoff.md` |
| **M2: risk and evaluation** | `hm` | `src/flight_risk/`, `tests/flight_risk/`, `artifacts/risk/`, `handover/status-member-2.json`, `handover/member-2-results.md`, `handover/shared-contract.md`, `handover/README.md`, `implementation-plan.md` |
| **M3: app and delivery** | `a` | `app.py`, `src/dashboard/`, `src/shared.py`, `.streamlit/`, `tests/dashboard/`, `requirements*.txt`, `README.md`, `.gitignore`, `.gitattributes`, `data/reference/`, `parallel-plan.md`, `handover/status-member-3.json` |

Branch names follow existing activity; swap them if the team divides differently.

Before each push, list your changed files and confirm that all of them are in your row:

```bash
git fetch origin && git diff --name-only origin/main...HEAD
```

If another member's file needs a change, send them the exact request. Don't edit it, even with a small fix.

### 2.2 Generated files

Parquet, joblib and hashed JSON files cannot be merged. Only the owner regenerates them. If a generated file conflicts, rerun the producer instead of resolving it by hand.

### 2.3 Interfaces are frozen now

The additions below are the only interface changes. All are optional, so every producer and consumer can start immediately. Consumers test against synthetic fixtures and show "unavailable" until the real field appears.

| Addition | Producer | Consumer | Shape |
|---|---|---|---|
| `aar_observed` in `artifacts/capacity/forecast.parquet` | M1 | M3 | Nullable float, arrivals/hour, held-out rows only, shown only after outcome reveal |
| `artifacts/capacity/traffic_hourly.parquet` | M1 | M3 | Key `(airport, hour_utc, direction)`; columns `scheduled_count`, `actual_count`, `coverage='reporting_carriers'`, `population`, `source_id`, `run_id`. Listed in the capacity manifest. **Never queue demand** |
| `storm_cohorts` in `artifacts/risk/evaluation.json` | M2 | M3 | List of `{cohort, airport, horizon_hours, metric, value, baseline_value, n, severe_n}` |
| `failure_cases` in `artifacts/risk/evaluation.json` | M2 | M3 | List of `{kind, flight_id, airport, horizon_hours, asof_utc, probability, threshold, observed, evidence, explanation, remedy}`; `kind` is `missed`, `false_alarm` or `declined`. Keep existing `failure_case` |
| `impact` in `artifacts/risk/evaluation.json` | M2 | M3 | `{basis, status_quo, comparisons:[{airport, horizon_hours, alert_share, model_recall, baseline_recall, model_precision, baseline_precision, n}], limitations}` |

M2 records these additions in `handover/shared-contract.md`. Anything else needs agreement from the producer and consumer first.

### 2.4 Upstream runs stay pinned

- M2 keeps using its immutable `artifacts/risk/input_snapshots/`. A new M1 publication doesn't require a retrain.
- M2 reruns `decide` only at Gate 3, when real AAR forecasts exist. M2 retrains only if M1 changes the features themselves.
- M3 reads whatever is on main and shows the run IDs. M3 never blocks on a newer run.

### 2.5 Merging

Merge small pull requests to main in any order. Ownership prevents text conflicts, so nobody has to wait for anyone else's merge. Rebase your branch at each gate.

## 3. Member 1: data and AAR

| # | Task | Done when |
|---|---|---|
| 1.1 | Write all JSON with LF line endings (`newline="\n"`) in `src/data_capacity/io.py`, then republish | `pytest tests/data_capacity -q` passes on Windows and Linux |
| 1.2 | Pursue a genuine AAR extract now, through the supervisor and organisers, using `data/public/aspm/README.md`. Record each attempt and reply in `data_access.json` | Extract received, or the refusal is recorded by Gate 2 |
| 1.3 | Ingest all BTS months from 2023-01 to 2025-07 and publish `traffic_hourly.parquet` | Both airports are covered; `population` names the reporting carriers; failed months are listed |
| 1.4 | Fix inverted TAF validity (5,580 rows end before they start because of the 24-hour cap) | No row has `valid_to_utc <= valid_from_utc`; a test covers it; feature values are unchanged or the change is explained |
| 1.5 | Prove a clean automatic run: delete local caches, run `python -m src.data_capacity run`, and record time and failures | Run finishes with no manual step, apart from the AAR export |
| 1.6 | Prove the pipeline is airport-generic with a third-airport test fixture and test-only registry, covering the missing-heading refusal | Test passes; no airport code changes; no third airport in published artifacts |
| 1.7 | **If AAR arrives:** train and publish held-out forecasts with baseline RMSE by airport and lead, storm and weather cohorts, a poor prediction, and `aar_observed` | Metrics are real and split boundaries are read back |
| 1.8 | **If AAR arrives:** publish contiguous leads 0 to W-1 at one cutoff for the queue, if the model supports them | Rows meet the contract's queue-compatibility rules |

**Workload if AAR never arrives:** tasks 1.1 to 1.6 still fill M1's time.

## 4. Member 2: risk and evaluation

| # | Task | Done when |
|---|---|---|
| 2.1 | Write JSON with LF line endings in `src/flight_risk/pipeline.py` and `__main__.py`, then republish | `python -m src.flight_risk verify` passes on Windows and Linux |
| 2.2 | Evaluate held-out predictions on storm cohorts from the committed `storm_events.parquet`. Keep storms out of model features | `storm_cohorts` is published; a test proves storms are not predictors; small cohorts show unavailable metrics |
| 2.3 | Compare with the status quo. At the same alert share, measure model recall and precision against the training-only baseline | `impact` is published as measured model improvement, with no delay-minute, fuel or savings claim |
| 2.4 | Publish at least three explained cases: a missed severe delay, a false alarm and a declined case | `failure_cases` gives cutoff evidence, the likely reason and a remedy, without asserting unproven causes |
| 2.5 | Add alert rate by airport and lead, and confirm confusion counts are in the evaluation | Numerators and denominators are published |
| 2.6 | Prove airport-generic behaviour using the existing registry argument and a third-airport fixture | Test passes without modelling changes |
| 2.7 | Optionally calibrate on validation data only, and keep it only if held-out Brier improves | Result is reported either way; the word "calibrated" appears only if it was done |
| 2.8 | Record section 2.3 in `handover/shared-contract.md` at T+0 | Contract matches this plan |
| 2.9 | **At Gate 3, if AAR forecasts and demand exist:** rerun `decide` | Queue or a reasoned refusal is published |

## 5. Member 3: app and delivery

| # | Task | Done when |
|---|---|---|
| 3.1 | Add `.gitattributes` keeping generated JSON byte-exact (`artifacts/** -text`, `data/processed/*.json -text`) | Merged to main first; M1 and M2 republish without CRLF changes |
| 3.2 | Commit the dashboard on `a`, then merge main. **Keep main's `src/shared.py`, `data/reference/airports.json` and `.streamlit/config.toml`.** Adapt the dashboard to the dict-based `AIRPORTS` | M1 and M2 tests still pass; dashboard tests pass; no `src/flight_risk` or `src/data_capacity` file changed |
| 3.3 | Keep main's live-weather view as a separate tab, and its schematic map only if porting is quick | Live data never affects replay |
| 3.4 | Fix `normalized_metrics` validation: the key must include `split` | The real file loads with 1,891 rows; Trends renders behind reveal |
| 3.5 | Show feature meanings correctly: 6.01 as "over 6 SM", 30000 as "no ceiling", gust equal to wind as "no gust forecast", temperature as observed at cutoff | Tests cover each case |
| 3.6 | Make sparse replay usable: list cutoffs by flights scored, and show the published decision snapshot | Demo reaches a useful cutoff without searching |
| 3.7 | Add a clear weather versus schedule model label per row | Mixed cohorts show both counts (10,599 and 5 in the current run) |
| 3.8 | Render the frozen additions in section 2.3, each with an unavailable state | Fixtures cover present and absent cases |
| 3.9 | Reconcile dependencies: `pandas>=3`, a tested plotly range, and exact versions in `requirements-observed.txt` | Fresh virtual environment installs, launches and passes tests |
| 3.10 | Allow a third airport through registry and fixture only: its data appears, or a missing heading gives a clear refusal | Test passes; ATL and DFW stay the scored demonstration |
| 3.11 | Update the README evidence matrix and status with real run IDs and measured results, naming the user, current workflow and the fact that no LLM is used, with the reason | Every row names an artifact, command and limitation |
| 3.12 | Run the app on real artifacts in a visible browser; review layout, including both airports, all leads, reveal on and off, and a hash-failure case | Findings are recorded and fixed |
| 3.13 | Build and rehearse the three-minute demo: user and status quo, cutoff and forecast, risk against baseline, advice or refusal, failure case | Timed under three minutes; only measured values shown |

## 6. Timeline and gates

Gates are checkpoints. Nobody waits at a gate for another member's work.

| Time | M1 | M2 | M3 |
|---|---:|---|---|
| **T+0 to T+0.5** | 1.1, start 1.2 | 2.1, 2.8 | 3.1, 3.2 |
| **T+0.5 to T+2** | 1.3, 1.4 | 2.2, 2.3 | 3.3 to 3.7 |
| **T+2 to T+3** | 1.5, 1.6, then 1.7 and 1.8 if AAR exists | 2.4 to 2.6, then 2.7 | 3.8 to 3.10 |
| **T+3 to T+3.5** | Defects only | 2.9 if available; defects only | 3.11, 3.12 |
| **T+3.5 to T+4** | Support the rehearsal | Support the rehearsal | 3.13 and submission |

| Gate | Time | Check |
|---|---|---|
| **1** | T+0.5 | `.gitattributes` and LF fixes are merged; M3 has the app running on main's real artifacts; contract updated |
| **2** | T+2 | AAR decision: extract received, or recorded as unmet. Tests pass on each branch |
| **3** | T+3 | Feature freeze. M2 reruns `decide` only if AAR forecasts and demand are both on main |
| **4** | T+3.5 | From a fresh clone: all tests pass, `verify` passes, the app launches, and every README claim is traceable |

## 7. Open decision: if AAR never arrives

AAR RMSE is the brief's named accuracy measure, so this matters most. **Recommendation:** present it as an unmet requirement, with the access evidence and one-command path to results. That earns credit for restraint, while a proxy would break the contract.

As a stretch only, and with all three members agreeing at Gate 2, M1 could forecast observed arrival throughput from `traffic_hourly.parquet`. It would need a separate artifact, its own name, and no AAR label or AAR RMSE.

## 8. Out of scope

Reroute and diversion ranking, ATIS, live traffic, fuel estimates, network optimisation, deployment, a multi-snapshot recommendation index, flight-specific rescheduling without eligibility data, and scoring additional airports.

Without verified arrival demand and cutoff backlog, the queue and metering advice remain explicit refusals. Full BTS counts don't change this, because they are reconstructed rather than known at the cutoff.
