# Readiness follow-up: combined automated verification

31 October 2026. Branch `codex/challenge5-readiness-reviewed` combines readiness checkpoint `88c708a`, exact Member 1 publication `5805f89b8ae908b330e1e981536f52ae1725c2ee` (cherry-pick `b14c4ae`) and three independently reviewed contributions: release hardening `6929ff7` (`0fe04a6`), briefing validation `be2d176` (`341a44b`), and judging/docs `c0171bd` (`ddc7b24`). No main merge or supervisor acceptance is claimed.

- Fresh package extraction: **395 tests passed**, risk verification **exit 0**, real-artifact app smoke **exit 0** across 13 cases (initial + KATL/KDFW x 3/6/12h x reveal off/on). Gate scope is **combined_runtime**, status **verified**, no automated blockers. The physical-core detection warning is non-failing.
- Runtime fingerprint: `8303c9cb6eb5126446e8af66dd225863ce5cd70bdfae14161bf0784450989c15`. Actual commands, durations, log hashes and package snapshot are in `output/delivery/verification.json`; local logs are under `output/delivery/logs/release-ee2lqzdl`.
- All 97 baseline hashes checked: five Member 1 source files changed exactly as published, 92 unchanged. Member 1-owned files match its exact commit. Frozen risk, producer inputs, models and dependencies are unchanged. No new training or scientific accuracy claim.
- Release builder now checks the executed fingerprint before promoting the final ZIP and preserves the previous archive on runtime mismatch. Tests cover missing estimate, failed app checks, source/extracted/late mutations and publication failures. Package manifest records verification scope.
- Controller brief rejects missing identities/schema and unusable/hash-mismatched publications; exact-cutoff, run, clocks, threshold equality and outcome-invariance tests pass. Regenerated ATL 2025-07-12 20:00Z +3h brief has 2 sampled flights / 2 review priorities; it publishes no observed outcomes or operational actions.
- A preliminary checkpoint run passed 374 tests and app smoke, but was correctly refused promotion because review commits changed the source while it ran. The stable hardened 395-test run supersedes that report.

After documentation freeze, the final archive is rebuilt, hash/manifest verified and extracted; its adjacent `.receipt.json`, `.manifest.json` and `.sha256` are the definitive final source identity and hash. Generated archives and verbose logs are local/ignored. Source and summary evidence are committed and pushed on readiness branches.

Manual browser tiles and proxy-label review, timed three-minute presentation, submission timestamp/receipt, and supervisor acceptance remain pending. The estimate is a reporting-carrier high-demand throughput proxy, not independently observed facility AAR; queue/metering/rescheduling remain unavailable. Existing environment used; no clean install or public-data refresh performed.

# Member 2 verified results and handback

## Historical handback: independent 30-minute delivery sprint

31 October 2026. **Delivery work ready for review; baseline application has a known frontend failure.** Implementation base `737b46852c2d4b98e7c01e68ed7e3888f6542c5c`, handoff base `c01500a3bb247e7ab7882ae3d45e4b266d1b028e`, branch `codex/member-2-delivery-30min`.

- Replaced the stale partial archive builder with portable, manifest-backed packaging. It includes both producers, processed inputs, frozen risk snapshots, current frontend/config/static files, tests and handoffs. It preserves committed model requirements and excludes raw caches, worktrees, environments and prior archives.
- Added 10 delivery tests and a real-artifact AppTest command. Optional `artifacts/capacity_estimate` discovery is verified with a synthetic fixture; no Member 1 sprint output was required or used.
- Fresh extracted runtime: risk verifier **exit 0**; risk plus delivery tests **106 passed, exit 0**; full suite **330 passed / one inherited failure, exit 1**; app smoke **exit 1**, reproducing that same initial chart exception. The airport/lead/reveal matrix is blocked by the initial render.
- Source preservation: **97/97 frozen files unchanged**. Extraction preservation: **96/96 included frozen files unchanged**; raw-cache `data/public/.gitignore` intentionally omitted. No dashboard, model, data, existing test or dependency edits; no retraining.
- Known failure remains `tests/dashboard/test_additions.py::test_actual_traffic_counts_need_reveal`, caused by the Timestamp annotation at `src/dashboard/plots.py:168`. Member 1 owns the fix. It prevents final demo acceptance but does not block independent delivery-tool acceptance.

Detailed commands, environment, intermediate archive hash and limitations are in `output/delivery/VERIFICATION.md` and `verification.json`. The final baseline ZIP is `output/delivery/challenge-5-implementation.zip`; its **final** hash and source commit are in the adjacent `.sha256` and `.receipt.json`, reported in the handback message. Code-identical runtime tests preceded the final documentation rebuild; final payload/hash checks are separate.

Rebuild with `python output/delivery/build-package.py`. Verify with `python output/delivery/build-package.py --verify output/delivery/challenge-5-implementation.zip`. Generated archives and verbose local logs are ignored by Git; the builder, tests and evidence are committed. Supervisors merge both independent member contributions, repair/verify the combined app, refresh execution evidence, and rebuild. Changed runtime bytes invalidate this branch's execution status automatically.

Capacity direction: organisers do not provide genuine AAR labels. Member 1 is implementing a separately labelled model estimate from published inputs; it is planned/absent in this branch. Observed throughput, estimated capacity and recorded facility AAR remain distinct. Queue/advice remain unavailable without complete demand and cutoff backlog. The historical sections below preserve earlier modelling evidence and are not a current release checklist.

## Historical model handback (before this sprint)

## Completion boundary

The local risk-model, normalized-metric, queue-validation and advisory implementation is complete and tested. It has now been refreshed with Member 1's verified canonical flights and cutoff-safe weather features (now capacity run `m1-20261031T062924Z-d9dfcd`, merged from branch `zeph`), and extended with the parallel-plan evaluation additions (storm cohorts, status-quo impact, alert rates, explained failure cases, calibration experiment). Current project capability is still **partial**: no genuine AAR, complete demand or cutoff backlog is published, so queue/advice remain unavailable. Member 3's v2 dashboard is on `main`; its rendering of these outputs was reviewed in `handover/message-to-member-3.md`. This is not a claim that Challenge 5 is fully satisfied.

## Published real outputs

- `artifacts/risk/model.joblib`: selected weather-enhanced histogram gradient-boosting model, schedule-only fallback and historical baseline.
- `artifacts/risk/predictions.parquet`: **10,604** held-out flight/horizon predictions covering **3,537** unique test flights, KATL/KDFW and leads 3/6/12. 10,599 rows are `weather_enhanced`; 5 rows without an accepted weather snapshot fall back to `schedule_only`.
- `artifacts/risk/normalized_metrics.parquet`: daily UTC observed delay/cancellation/missingness cohorts with explicit denominators and outcome-reveal flags.
- `artifacts/risk/evaluation.json`: candidate comparison, thresholds, per-airport/horizon metrics, weather vs schedule matched-cohort comparison, reliability bins, exclusions, plus the frozen contract additions `storm_cohorts`, `impact`, `alert_rates`, `failure_cases` and the `calibration_experiment` record. The legacy single `failure_case` key is kept.
- `artifacts/risk/manifest.json`: schema, runtime, source hashes, artifact hashes, row counts and capability status.
- `artifacts/risk/input_snapshots/571f5ceda96448999f730c4da4203f72/`: immutable copies of the verified upstream flights, weather-feature and storm-event bytes used for training, with provenance pointing to capacity run `m1-20261031T062924Z-d9dfcd`. Superseded snapshots were removed from the tree; they remain in git history.
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
| KDFW | 6h | 1,774 | 0.2570 | 0.2276 | 0.1960 | 0.255 / 0.500 | 0.249 / 0.477 | 0.1219 |
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
| KDFW | 6h | 90 (30) | 0.557 / 0.428 | 0.633 / 0.667 | 0.227 / 0.183 |
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
python -m src.flight_risk train
python -m src.flight_risk decide --airport KATL --asof 2025-07-15T12:00:00Z --window-hours 6
python -m src.flight_risk verify
python -m pytest tests -q --basetemp=tmp/pt-all-6
```

All Member 2 commands exited 0. The full suite, including Member 1's and Member 3's tests, gave **291 passed**. `verify` reported `passed`, model status `partial`, decision status `unavailable`, 10,604 predictions / 3,537 flights / both airports / leads 3, 6, 12. The `tmp/` directory must exist before running pytest with `--basetemp=tmp/...`.

Member 2 test coverage includes storm events never changing predictions, small-cohort withholding, equal-workload baseline ties, alert-rate counts, failure-case kinds, calibration decisions independent of test labels, third-airport scoring through the registry only, LF-only published JSON, leakage under changed test outcomes, original-date/2400 splits, daylight-saving ambiguity, cancelled labels, source/availability/feature validity, queue conservation, stale/mismatched populations, complete hourly windows, capacity target provenance, model selection timing, manifest tampering, generation mismatch, typed unavailable outputs and CLI publication. Test fixtures stay under tests/tmp and are not passed off as real data.

The verifier reads hashes and tables without deserializing model code. A passed integrity check does not change unavailable capability to available.

## Integration fixes applied during refresh

Member 1's first published manifest (`m1-20261031T045159Z-3df67d`) lacked the contract's `artifact_hashes` field, so `train` correctly refused it, and it used provisional 16-character flight IDs because `src/shared.py` was absent in that checkout. With the user's authorization, Member 2 made the following changes in Member 1's scope:

- `src/data_capacity/pipeline.py` now writes `artifact_hashes` (manifest-directory-relative paths, e.g. `weather_features.parquet`, `../../data/processed/flights.parquet`) alongside the existing `outputs` list.
- `tests/data_capacity/test_manifest.py` checks those keys and hashes.
- The Member 1 pipeline was rerun with network downloads. It now uses `src.shared.flight_key` (20-character IDs) and `src.shared.AIRPORTS`. All 3,537 Member 2 test flight IDs join to the canonical flights.

## Runtime and provenance

Model run: `0949771a54bb4e49b4e215528eb5d46b`; generated `2026-10-31T06:38:52.388647+00:00`.
Decision run: `a7b89e44c69449d1a7ecfbf0cb8ff3b5`.
Upstream capacity run: `m1-20261031T062924Z-d9dfcd`.

This run follows Member 1's deterministic weather decoding (commit `20693d7`), which changed 4 model features (`crosswind_kt`, `wind_speed_kt`, `wind_gust_kt`, `temperature_c`) in 3 of 135,786 rows. Retraining changed exactly 3 held-out probabilities (largest change 0.04); thresholds are identical and no alert flipped. The only visible metric changes are KDFW 6h (average precision 0.2567 to 0.2570, Brier 0.12197 to 0.12194) and the KDFW 6h no-storm cohort (AP 0.226 to 0.227). All other values in this document are unchanged.

An earlier retrain (run `b307f1c5…`) followed Member 1's TAF/METAR validity fix (plan 1.4), which changed `weather_features.parquet`. The fix altered only columns Member 2 does not use (`cond_*` conditional-group summaries and `taf_group_valid_to_utc`). The 9 contract features, keys, availability times and statuses are identical across all 135,786 rows. As a result, probabilities, thresholds and every metric in this document matched runs `28ffd143…` and `b3747032…` exactly. Run `9dbee2fd…` (capacity run `m1-20261031T060631Z-6c6e38`, which added `traffic_hourly.parquet` and `aar_observed`) was likewise identical.
Python `3.14.6`; numpy 2.4.6, pandas 3.0.3, scikit-learn 1.9.0, pyarrow 23.0.1.

The old root requirements constrain pandas below 3, while the verified runtime uses pandas 3.0.3. Member 3 owns dependency reconciliation. Serialized model reuse requires compatible versions or retraining.

## Member 1 handback needed

Genuine AAR remains an unmet core requirement: an FAA ASPM hourly/quarter-hour export for ATL/DFW must be placed in `data/public/aspm/` (spec in its README), followed by `python -m src.data_capacity run --cache-only`. For queue/advice also publish contiguous-hour AAR forecasts, complete arrival demand and known cutoff backlog for the same population. Three isolated scored leads are insufficient for a queue.

## Member 3 handback needed

Use the dedicated handoff and runbook. Fix target-hour selection and available replay keys; verify manifests; integrate normalized history with outcome masking; distinguish weather-enhanced, schedule-only fallback and sample coverage. Show the matched-cohort comparison above, not schedule-only numbers as weather-model performance, and do not present weather gains as operationally validated. Render `storm_cohorts`, `impact`, `alert_rates` and `failure_cases` per `handover/shared-contract.md`, each with an unavailable state when absent; storm cohort rows with `status: unavailable` have null values.
