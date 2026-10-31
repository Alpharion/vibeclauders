# Member 2 verified results and handback

## Completion boundary

The local risk-model, normalized-metric, queue-validation and advisory implementation is complete and tested. It has now been refreshed with Member 1's verified canonical flights and cutoff-safe weather features (capacity run `m1-20261031T050536Z-89e2f0`), and extended with the parallel-plan evaluation additions (storm cohorts, status-quo impact, alert rates, explained failure cases, calibration experiment). Current project capability is still **partial**: no genuine AAR, complete demand or cutoff backlog is published, so queue/advice remain unavailable. Member 3's dashboard integration has not started in this repository. This is not a claim that Challenge 5 is fully satisfied.

## Published real outputs

- `artifacts/risk/model.joblib`: selected weather-enhanced histogram gradient-boosting model, schedule-only fallback and historical baseline.
- `artifacts/risk/predictions.parquet`: **10,604** held-out flight/horizon predictions covering **3,537** unique test flights, KATL/KDFW and leads 3/6/12. 10,599 rows are `weather_enhanced`; 5 rows without an accepted weather snapshot fall back to `schedule_only`.
- `artifacts/risk/normalized_metrics.parquet`: daily UTC observed delay/cancellation/missingness cohorts with explicit denominators and outcome-reveal flags.
- `artifacts/risk/evaluation.json`: candidate comparison, thresholds, per-airport/horizon metrics, weather vs schedule matched-cohort comparison, reliability bins, exclusions, plus the frozen contract additions `storm_cohorts`, `impact`, `alert_rates`, `failure_cases` and the `calibration_experiment` record. The legacy single `failure_case` key is kept.
- `artifacts/risk/manifest.json`: schema, runtime, source hashes, artifact hashes, row counts and capability status.
- `artifacts/risk/input_snapshots/8413140de27948afbe71083c9d246533/`: immutable copies of the verified upstream flights, weather-feature and storm-event bytes used for training, with upstream run provenance. Its flights and weather bytes are identical to the previous snapshot, which was removed from the tree as a duplicate (it remains in git history).
- `artifacts/risk/recommendations.json`, `queue.parquet`, `decision_manifest.json`: verified unavailable result at KATL / 2025-07-15T12:00:00Z / six-hour window because demand, capacity and initial backlog are missing. Queue is empty with typed columns; no invented benefit or flight action.

The run used 15,947 eligible labels from 25,299 canonical rows (16,151 target departures): 6,064 training, 6,346 validation and 3,537 test departures. All 204 cancelled departures were excluded, including seven with nonmissing delay labels. No invalid schedule, duplicate or naive-UTC rows. Seven test flight/horizon combinations were excluded because their cutoff preceded selection completion (2025-01-01T06:00Z).

Weather consumer audit: 135,786 feature rows offered, 135,735 accepted, 51 rejected for non-available status, 0 rejected for timing/source/duplicate/numeric problems; 47,826 flight/horizon rows matched across all splits.

## Measured held-out test performance (matched cohorts)

Weather-enhanced and schedule-only models are compared on the identical flight/horizon rows that have accepted weather. Each model uses its own validation-selected threshold (weather `0.146025`, schedule `0.157434`).

| Airport | Lead | n | Weather AP | Schedule AP | Baseline AP | Weather precision / recall | Schedule precision / recall | Weather Brier |
|---|---:|---:|---:|---:|---:|---|---|---:|
| KATL | 3h | 1,763 | 0.2620 | 0.2496 | 0.2081 | 0.261 / 0.522 | 0.319 / 0.285 | 0.1063 |
| KATL | 6h | 1,760 | 0.2747 | 0.2496 | 0.2081 | 0.292 / 0.500 | 0.319 / 0.285 | 0.1065 |
| KATL | 12h | 1,758 | 0.2579 | 0.2496 | 0.2082 | 0.312 / 0.320 | 0.319 / 0.285 | 0.1081 |
| KDFW | 3h | 1,774 | 0.2485 | 0.2276 | 0.1960 | 0.235 / 0.489 | 0.249 / 0.477 | 0.1227 |
| KDFW | 6h | 1,774 | 0.2567 | 0.2276 | 0.1960 | 0.255 / 0.500 | 0.249 / 0.477 | 0.1220 |
| KDFW | 12h | 1,770 | 0.2714 | 0.2276 | 0.1961 | 0.263 / 0.498 | 0.249 / 0.479 | 0.1212 |

Baseline AP is the training-only airport/local-hour smoothed severe-delay rate, evaluated on the full test cohort for that airport/lead.

Weather features improve average precision over the schedule-only model in every airport/lead cell (gains of 0.008 to 0.044) and over the historical baseline. The signal remains weak: AP is below 0.28 against a prevalence of about 13-15%. At ATL the weather model's higher recall comes with lower precision than the schedule model. Lead-specific differences are now measured, because weather inputs differ by cutoff, but the sample is small and no lead-time trend should be claimed. The weather capability is reported **partial** because 5 of 10,604 test rows lacked accepted weather and fall back to schedule-only.

No AAR, delay-minute, fuel or causal benefit claims follow from these results.

## Comparison with the status quo (`impact`)

The status quo is the training-only (2023) airport/local-hour severe-delay rate, which a duty officer could consult without a model. At each airport/lead the baseline flags the **same number** of departures as the model (highest historical rates first, ties shared pro rata), so the comparison holds alert workload fixed.

| Airport | Lead | n | Alerts (share) | Model recall | Baseline recall | Model precision | Baseline precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| KATL | 3h | 1,763 | 456 (25.9%) | 0.522 | 0.432 | 0.261 | 0.216 |
| KATL | 6h | 1,763 | 390 (22.1%) | 0.500 | 0.378 | 0.292 | 0.221 |
| KATL | 12h | 1,759 | 234 (13.3%) | 0.320 | 0.247 | 0.312 | 0.241 |
| KDFW | 3h | 1,774 | 548 (30.9%) | 0.489 | 0.451 | 0.235 | 0.217 |
| KDFW | 6h | 1,774 | 518 (29.2%) | 0.500 | 0.424 | 0.255 | 0.216 |
| KDFW | 12h | 1,771 | 499 (28.2%) | 0.496 | 0.407 | 0.263 | 0.215 |

At equal workload the model catches more severe delays than the historical rate in every cell (+4 to +12 percentage points recall). This measures alert quality only. No delay minutes, fuel or savings follow, and no intervention was simulated. Per-cell numerators and denominators are in `alert_rates`.

## Storm cohorts (`storm_cohorts`)

NOAA Storm Events are used only after prediction, never as features; a test proves predictions are identical with and without them. A test row is in the storm cohort when an event for the airport's vicinity overlaps [target hour - 3h, target hour + 1h + 3h): 393 of 10,604 rows.

| Airport | Lead | Storm n (severe) | Storm AP model / baseline | Storm recall model / baseline | No-storm AP model / baseline |
|---|---:|---:|---|---|---|
| KATL | 3h | 41 (10) | 0.361 / 0.248 | 0.500 / 0.600 | 0.262 / 0.208 |
| KATL | 6h | 41 (10) | 0.407 / 0.248 | 0.500 / 0.450 | 0.273 / 0.208 |
| KATL | 12h | 41 (10) | 0.280 / 0.248 | 0.300 / 0.100 | 0.259 / 0.208 |
| KDFW | 3h | 90 (30) | 0.470 / 0.428 | 0.633 / 0.650 | 0.225 / 0.183 |
| KDFW | 6h | 90 (30) | 0.557 / 0.428 | 0.633 / 0.667 | 0.226 / 0.183 |
| KDFW | 12h | 90 (30) | 0.531 / 0.428 | 0.633 / 0.700 | 0.239 / 0.183 |

Baseline recall here also uses equal alert counts. Severe delays are far more common near storms (24-33% vs 13-14%). The model ranks storm-window departures better than the baseline (higher AP in every cell), but at its chosen threshold it does **not** beat the baseline's recall at DFW. The storm cohorts are small (41 and 90 departures per cell), so these differences are not statistically established.

## Explained failure cases (`failure_cases`)

All require outcome reveal. Evidence is cutoff-time weather plus retrospective NOAA and BTS records; explanations do not assert a cause.

- **Missed:** `6bffcd9ede90492913be`, KATL, 3h lead, cutoff 2025-01-10T10:00Z. Probability 0.035 against threshold 0.146; departure delay 442 min. BTS attributes all 442 min to carrier delay; NOAA logged a Winter Storm overlapping the target hour, while the cutoff forecast showed precipitation. Remedy: carrier and upstream-aircraft delays need a cutoff-safe carrier or inbound-aircraft source.
- **False alarm:** `460f3042c18b22443112`, KATL, 3h lead, cutoff 2025-07-12T20:00Z. Probability 0.612; observed delay 21 min. The cutoff forecast indicated thunderstorms and precipitation, but no NOAA event was logged near the target hour. Remedy: treat alerts as prompts for review.
- **Declined:** `c740f6ce903b62f1e869`, KATL, 6h lead, cutoff 2025-03-10T06:00Z. The weather snapshot had status `partial`, so the weather prediction was withheld and the schedule-only model (probability 0.041) was used.

## Calibration experiment (`calibration_experiment`)

Platt scaling was fitted on 2024 validation before September and judged on September-December validation, with a pre-set rule: adopt only if Brier falls by at least 1%. Brier moved from 0.06717 to 0.06713 (0.07% gain), so calibration was **not adopted** and probabilities remain **uncalibrated**. Test Brier (reported only, not used to decide) would have moved from 0.1145 to 0.1139. The larger issue is a base-rate shift: the model's mean probability is 0.109 on test while the observed severe rate is 0.139, and recalibrating on 2024 data cannot fix that.

## Verification performed

```powershell
python -m src.data_capacity run --bts-months 2023-01
python -m src.flight_risk train
python -m src.flight_risk decide --airport KATL --asof 2025-07-15T12:00:00Z --window-hours 6
python -m src.flight_risk verify
python -m pytest tests/flight_risk -q --basetemp=tmp/pt-31
```

**Clean-clone check:** a `git archive` export of commit `707b4d5`, which has the bytes a fresh clone receives on any platform, gives `verify` passed and all Member 2 tests passing. Before the LF fix, the same check failed `verify` with a hash mismatch on `evaluation.json`. The export's full suite gives 136 passed and 2 failed; both failures are Member 1's `tests/data_capacity/test_manifest.py` (CRLF-hashed capacity JSON, plan task 1.1).

All commands exited 0. **96 Member 2 tests passed.** `verify` reported `passed`, model status `partial`, decision status `unavailable`, 10,604 predictions / 3,537 flights / both airports / leads 3, 6, 12. The `tmp/` directory must exist before running pytest with `--basetemp=tmp/...`.

Member 2 test coverage includes storm events never changing predictions, small-cohort withholding, equal-workload baseline ties, alert-rate counts, failure-case kinds, calibration decisions independent of test labels, third-airport scoring through the registry only, LF-only published JSON, leakage under changed test outcomes, original-date/2400 splits, daylight-saving ambiguity, cancelled labels, source/availability/feature validity, queue conservation, stale/mismatched populations, complete hourly windows, capacity target provenance, model selection timing, manifest tampering, generation mismatch, typed unavailable outputs and CLI publication. Test fixtures stay under tests/tmp and are not passed off as real data.

The verifier reads hashes and tables without deserializing model code. A passed integrity check does not change unavailable capability to available.

## Integration fixes applied during refresh

Member 1's first published manifest (`m1-20261031T045159Z-3df67d`) lacked the contract's `artifact_hashes` field, so `train` correctly refused it, and it used provisional 16-character flight IDs because `src/shared.py` was absent in that checkout. With the user's authorization, Member 2 made the following changes in Member 1's scope:

- `src/data_capacity/pipeline.py` now writes `artifact_hashes` (manifest-directory-relative paths, e.g. `weather_features.parquet`, `../../data/processed/flights.parquet`) alongside the existing `outputs` list.
- `tests/data_capacity/test_manifest.py` checks those keys and hashes.
- The Member 1 pipeline was rerun with network downloads. It now uses `src.shared.flight_key` (20-character IDs) and `src.shared.AIRPORTS`. All 3,537 Member 2 test flight IDs join to the canonical flights.

## Runtime and provenance

Model run: `28ffd143d091491fb9a66c8015784263`; generated `2026-10-31T05:54:59.987632+00:00`. Probabilities and thresholds are identical to the previous run `b3747032ae754cc9be967b9e4ab681b9`; only the evaluation additions changed.
Decision run: `cb6148fc59fd46afbe30c5dae43e7c46`.
Upstream capacity run: `m1-20261031T050536Z-89e2f0`.
Python `3.14.6`; numpy 2.4.6, pandas 3.0.3, scikit-learn 1.9.0, pyarrow 23.0.1.

The old root requirements constrain pandas below 3, while the verified runtime uses pandas 3.0.3. Member 3 owns dependency reconciliation. Serialized model reuse requires compatible versions or retraining.

## Member 1 handback needed

Genuine AAR remains an unmet core requirement: an FAA ASPM hourly/quarter-hour export for ATL/DFW must be placed in `data/public/aspm/` (spec in its README), followed by `python -m src.data_capacity run --cache-only`. For queue/advice also publish contiguous-hour AAR forecasts, complete arrival demand and known cutoff backlog for the same population. Three isolated scored leads are insufficient for a queue.

## Member 3 handback needed

Use the dedicated handoff and runbook. Fix target-hour selection and available replay keys; verify manifests; integrate normalized history with outcome masking; distinguish weather-enhanced, schedule-only fallback and sample coverage. Show the matched-cohort comparison above, not schedule-only numbers as weather-model performance, and do not present weather gains as operationally validated. Render `storm_cohorts`, `impact`, `alert_rates` and `failure_cases` per `handover/shared-contract.md`, each with an unavailable state when absent; storm cohort rows with `status: unavailable` have null values.
