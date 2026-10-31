# Full-BTS delay-risk experiment

The full-BTS candidate passed the prespecified late-2024 selection rule. Production predictions remain unchanged: this is a validated experimental artifact awaiting publication and consumer integration.

## Data and method

The verified 31-month canonical dataset contains 3,255,098 flights, including arrivals. Training uses 614,524 eligible 2023 departures (1,843,390 weather-available flight/horizon snapshots). The incumbent is the same fixed histogram gradient boosting classifier refitted on the original challenge sample in 2023. This comparison isolates training-population expansion; it is not a direct comparison against every published production model.

Both models use identical weather and schedule features and fixed parameters (100 iterations, depth 3, 8 leaves, learning rate 0.08, L2 2, minimum leaf 25, seed 27; no search or calibration). Thresholds are fitted on original-sample January–August 2024 only. September–December 2024 original-sample performance selects the candidate; full-population metrics are secondary. All comparisons use the same original-sample labels and weather-available cohort.

Training and threshold label-availability boundaries exclude earlier prediction cutoffs. The full training boundary is 2024-01-01 14:14 UTC, later than the sample boundary (06:00 UTC). Threshold availability is 2024-09-01 05:00 UTC; 2025 scoring starts after selection-label availability at 2025-01-01 14:02 UTC. Schedules and observation receipt latency remain disclosed replay assumptions.

## Adoption rule and result

Before scoring: equal-weight mean AP over ATL/DFW × 3/6/12 hours must improve by at least 1%; mean Brier may regress by no more than 2%; no cell AP may regress by more than 5%. All six cells are required. Selection is locked before secondary and 2025 scoring.

Result: macro AP 0.148126 → 0.166254 (+12.24% relative); Brier 0.067763 → 0.067110 (-0.96% relative). Worst cell AP regression: 1.96%.

AP/PR-AUC measures ranking of rare severe delays; Brier measures probability error (lower is better). RMSE is appropriate for the separate arrival-count/capacity regressions, not the classifier headline. Equal-workload recall uses exactly the incumbent alert count in each cell, with fractional expected credit for boundary ties.

## Primary: original sample, late 2024

| Airport / lead | Rows | AP incumbent → candidate | Brier incumbent → candidate | Recall at equal alerts incumbent → candidate | Alerts |
|---|---:|---|---|---|---:|
| KATL +3h | 1,124 | 0.1579 → 0.1857 | 0.0559 → 0.0552 | 0.0870 → 0.1159 | 31 |
| KATL +6h | 1,124 | 0.1556 → 0.1872 | 0.0559 → 0.0553 | 0.0870 → 0.1159 | 30 |
| KATL +12h | 1,119 | 0.1461 → 0.1814 | 0.0558 → 0.0550 | 0.0882 → 0.1176 | 26 |
| KDFW +3h | 1,021 | 0.1485 → 0.1456 | 0.0796 → 0.0792 | 0.2222 → 0.1889 | 90 |
| KDFW +6h | 1,021 | 0.1427 → 0.1546 | 0.0796 → 0.0787 | 0.2000 → 0.1778 | 78 |
| KDFW +12h | 1,021 | 0.1380 → 0.1430 | 0.0798 → 0.0793 | 0.1333 → 0.1444 | 68 |

## Secondary: full BTS, late 2024

| Airport / lead | Rows | AP incumbent → candidate | Brier incumbent → candidate | Recall at equal alerts incumbent → candidate | Alerts |
|---|---:|---|---|---|---:|
| KATL +3h | 114,529 | 0.1100 → 0.1201 | 0.0544 → 0.0540 | 0.0962 → 0.0888 | 3,056 |
| KATL +6h | 114,466 | 0.1110 → 0.1206 | 0.0544 → 0.0540 | 0.0914 → 0.0857 | 2,967 |
| KATL +12h | 114,159 | 0.1120 → 0.1246 | 0.0544 → 0.0540 | 0.0844 → 0.0799 | 2,695 |
| KDFW +3h | 103,931 | 0.1280 → 0.1402 | 0.0847 → 0.0834 | 0.1429 → 0.1593 | 9,708 |
| KDFW +6h | 103,924 | 0.1285 → 0.1419 | 0.0846 → 0.0834 | 0.1250 → 0.1409 | 8,184 |
| KDFW +12h | 103,676 | 0.1246 → 0.1377 | 0.0848 → 0.0836 | 0.0990 → 0.1133 | 6,827 |

## Updated backtest: original sample, 2025

| Airport / lead | Rows | AP incumbent → candidate | Brier incumbent → candidate | Recall at equal alerts incumbent → candidate | Alerts |
|---|---:|---|---|---|---:|
| KATL +3h | 1,759 | 0.2620 → 0.2784 | 0.1066 → 0.1053 | 0.4079 → 0.4561 | 343 |
| KATL +6h | 1,756 | 0.2747 → 0.2823 | 0.1067 → 0.1060 | 0.3465 → 0.3991 | 264 |
| KATL +12h | 1,754 | 0.2581 → 0.2706 | 0.1084 → 0.1074 | 0.2412 → 0.2675 | 171 |
| KDFW +3h | 1,771 | 0.2486 → 0.2526 | 0.1229 → 0.1220 | 0.4583 → 0.5076 | 489 |
| KDFW +6h | 1,771 | 0.2570 → 0.2535 | 0.1221 → 0.1217 | 0.4621 → 0.4848 | 456 |
| KDFW +12h | 1,767 | 0.2718 → 0.2661 | 0.1204 → 0.1199 | 0.4521 → 0.4904 | 420 |

## Updated backtest: full BTS, 2025

| Airport / lead | Rows | AP incumbent → candidate | Brier incumbent → candidate | Recall at equal alerts incumbent → candidate | Alerts |
|---|---:|---|---|---|---:|
| KATL +3h | 178,754 | 0.2196 → 0.2462 | 0.1035 → 0.1017 | 0.3892 → 0.4215 | 36,299 |
| KATL +6h | 178,540 | 0.2302 → 0.2540 | 0.1032 → 0.1017 | 0.3460 → 0.3744 | 29,408 |
| KATL +12h | 178,300 | 0.2292 → 0.2546 | 0.1039 → 0.1022 | 0.2323 → 0.2550 | 17,911 |
| KDFW +3h | 178,581 | 0.2379 → 0.2401 | 0.1220 → 0.1207 | 0.4616 → 0.4689 | 49,435 |
| KDFW +6h | 178,395 | 0.2461 → 0.2441 | 0.1214 → 0.1204 | 0.4427 → 0.4473 | 45,405 |
| KDFW +12h | 178,216 | 0.2559 → 0.2488 | 0.1210 → 0.1203 | 0.4295 → 0.4316 | 41,982 |

## Interpretation and remaining work

The 2025 period has been inspected previously and is an updated backtest, not a fresh holdout. Some DFW cells regress in 2025; the gain is not universal. Full-population thresholds retain the sample-derived operating point and are not tuned for that population. No confidence intervals or independent external validation were completed within this deadline.

An earlier sample-only experiment adding recent observed-delay rates and scheduled congestion was rejected (macro AP −6.23%, Brier +0.19%, worst cell AP −12.56%). Its evidence is retained in `sample_fallback_previous_result`; sparse sampled history is not complete airport state. The full-history feature candidate, inbound-tail state, destination weather, probability calibration, and capacity-model upgrades remain separate untested work.

## Reproduce and artifact

```powershell
python -m src.flight_risk.full_bts_experiment --full-bts-manifest tmp/full-bts-experiment/manifest.json
```

The manifest must identify all 31 canonical months and match the canonical SHA-256 before fitting. Source archive/filter hashes, cohort counts, weather coverage, frozen protocol, all cell metrics, thresholds and temporal boundaries are recorded in `handover/full-bts-model-evidence.json`. The monthly builder and its provenance are described in `handover/full-bts-results.md`.

The trained incumbent/candidate pipelines, feature allowlists, thresholds, protocol and source hash are stored in `tmp/full-bts-experiment/full-candidate-models.joblib`. Candidate is index 1. Reload predictions are checked for exact equality against both in-memory pipelines on the primary validation cohort. The artifact path/hash and reload check are recorded in the evidence JSON. This local artifact is not automatically shipped as the production model.

Production follow-up: bind the selected model and threshold into the verified publication contract, regenerate predictions/metrics and hashes, validate all consumers, rerun delivery verification, and rebuild the presentation package. Do not advertise these experimental metrics as the dashboard production predictions until that chain is complete.
