# Judging figures: Challenge 5

Every number below is read programmatically from the published artifacts (SHA-256 prefixes under Sources); none is hand-typed. The published model artifacts are byte-identical on `main` (`main`) and on the latest integration branch `codex/member-1-accuracy-integration` (`4f6386a`), so these figures apply to both.

Generated 2026-10-31 by the Member 1 agent.

## 1. Build and verification state

| Build | Commit | Tests | Risk verify | App smoke | Presentable? |
|---|---|---|---|---|---|
| `main` | `13c708b` | 410 passed, **31 failed** | exit 0 | **exit 1** | **No.** The Figma rebuild (`a3f3484`) crashes the replay screen: Streamlit v2 component `watchlist` is not registered; older tests call removed `live`/`map_payload` APIs |
| Latest integration (`codex/member-1-accuracy-integration`) | `4f6386a` | **501 passed**, 0 failed (re-run locally) | exit 0 | passed (13 checks, recorded gate) | Runtime yes, but it predates the Figma rebuild and **conflicts with `main` in `src/dashboard/app.py`** |

Integration-branch release gate: `verified`, scope `combined_runtime`, 501 tests, risk verify and app smoke exit 0, run in a fresh package extraction. Manual browser review, rehearsal and supervisor acceptance are still pending.

## 2. Published runs

| Publication | Run ID | Status |
|---|---|---|
| Data and capacity | `m1-20261031T084129Z-f83c9b` | partial (genuine AAR unavailable) |
| Delay-risk model | `0949771a54bb4e49b4e215528eb5d46b` | partial |
| Capacity estimate (proxy) | `m1-capest-20261031T084305Z-940bb8` | partial (model proxy, not AAR) |

## 3. Data coverage (multi-source integration, automatic processing)

| Item | Figure |
|---|---|
| Canonical flights (challenge sample, ATL/DFW) | 25,299 rows: ATL 8,415 departures / 5,429 arrivals; DFW 7,736 / 4,032 |
| Decoded METAR + TAF rows (IEM, automatic) | 147,002 |
| Cutoff-safe weather snapshots (KATL/KDFW x 3/6/12 h) | 135,786 |
| BTS reporting-carrier hourly traffic | 90,524 rows from 31 months; failed months: 0 |
| NOAA storm events near the airports (retrospective only) | 1,839 |
| Held-out delay predictions | 10,604 rows / 3,537 unique flights |
| Clean automatic run (empty caches, `python -m src.data_capacity run`) | 16 min 01 s, exit 0, 0 failed downloads, no manual step |
| Sample share | Challenge flights are 0.8% of full BTS ATL/DFW traffic (Jan 2023 exact match: 726/726 flights) |

## 4. Severe departure-delay classification (>45 min), held-out Jan-Jul 2025

Model: gradient boosting with cutoff-safe weather. Baseline in brackets: training-only airport x local-hour severe-delay rate. Threshold selected on 2024 validation only.

| Airport | Lead | n | Severe (base rate) | Precision | Recall | F1 | PR-AUC | Brier |
|---|---:|---:|---:|---|---|---|---|---|
| ATL | +3h | 1,763 | 228 (12.9%) | 26.1% (21.5%) | 52.2% (57.5%) | 0.348 (0.313) | 0.262 (0.208) | 0.106 (0.112) |
| ATL | +6h | 1,763 | 228 (12.9%) | 29.2% (21.5%) | 50.0% (57.5%) | 0.369 (0.313) | 0.275 (0.208) | 0.106 (0.112) |
| ATL | +12h | 1,759 | 228 (13.0%) | 31.2% (21.5%) | 32.0% (57.5%) | 0.316 (0.313) | 0.258 (0.208) | 0.108 (0.112) |
| DFW | +3h | 1,774 | 264 (14.9%) | 23.5% (19.8%) | 48.9% (73.1%) | 0.318 (0.312) | 0.249 (0.196) | 0.123 (0.125) |
| DFW | +6h | 1,774 | 264 (14.9%) | 25.5% (19.8%) | 50.0% (73.1%) | 0.338 (0.312) | 0.257 (0.196) | 0.122 (0.125) |
| DFW | +12h | 1,771 | 264 (14.9%) | 26.3% (19.8%) | 49.6% (73.1%) | 0.343 (0.312) | 0.271 (0.196) | 0.122 (0.126) |

PR-AUC is roughly twice the severe-delay base rate (0.25-0.27 vs 0.13-0.15). Brier is lower (better) than the baseline in every cell. Recall is below the baseline's because the baseline alerts far more often; the equal-workload comparison below is the fair one. Probabilities are uncalibrated; a Platt-scaling experiment was not adopted under its pre-set rule.

### Weather vs schedule-only, same flights

| Airport | Lead | PR-AUC weather | PR-AUC schedule-only | Recall weather | Recall schedule-only |
|---|---:|---|---|---|---|
| ATL | +3h | 0.262 | 0.250 | 52.2% | 28.5% |
| ATL | +6h | 0.275 | 0.250 | 50.0% | 28.5% |
| ATL | +12h | 0.258 | 0.250 | 32.0% | 28.5% |
| DFW | +3h | 0.249 | 0.228 | 48.9% | 47.7% |
| DFW | +6h | 0.257 | 0.228 | 50.0% | 47.7% |
| DFW | +12h | 0.271 | 0.228 | 49.8% | 47.9% |

### Impact: same alert workload as the status quo

Status quo: Training-only (2023) airport/local-hour severe-delay rate: the historical statistic a duty officer could consult without a model.

| Airport | Lead | Alerts (share) | Model recall | Baseline recall | Model precision | Baseline precision | Extra severe delays caught |
|---|---:|---|---|---|---|---|---:|
| ATL | +3h | 456 (25.9%) | 52.2% | 43.2% | 26.1% | 21.6% | +20.5 |
| ATL | +6h | 390 (22.1%) | 50.0% | 37.8% | 29.2% | 22.1% | +27.9 |
| ATL | +12h | 234 (13.3%) | 32.0% | 24.7% | 31.2% | 24.1% | +16.7 |
| DFW | +3h | 548 (30.9%) | 48.9% | 45.1% | 23.5% | 21.7% | +10.0 |
| DFW | +6h | 518 (29.2%) | 50.0% | 42.4% | 25.5% | 21.6% | +20.0 |
| DFW | +12h | 499 (28.2%) | 49.6% | 40.7% | 26.3% | 21.5% | +23.5 |

This measures alert quality only. No delay-minute, fuel or savings benefit is claimed.

### Severe-weather cohorts (retrospective NOAA storm within 3 h)

| Cohort | Airport | Lead | n (severe) | PR-AUC model | PR-AUC baseline | Status |
|---|---|---:|---|---|---|---|
| storm_within_3h | ATL | +3h | 41 (10) | 0.361 | 0.248 | available |
| storm_within_3h | ATL | +6h | 41 (10) | 0.407 | 0.248 | available |
| storm_within_3h | ATL | +12h | 41 (10) | 0.280 | 0.248 | available |
| storm_within_3h | DFW | +3h | 90 (30) | 0.470 | 0.428 | available |
| storm_within_3h | DFW | +6h | 90 (30) | 0.557 | 0.428 | available |
| storm_within_3h | DFW | +12h | 90 (30) | 0.531 | 0.428 | available |
| no_storm_within_3h | ATL | +3h | 1722 (218) | 0.262 | 0.208 | available |
| no_storm_within_3h | ATL | +6h | 1722 (218) | 0.273 | 0.208 | available |
| no_storm_within_3h | ATL | +12h | 1718 (218) | 0.259 | 0.208 | available |
| no_storm_within_3h | DFW | +3h | 1684 (234) | 0.225 | 0.183 | available |
| no_storm_within_3h | DFW | +6h | 1684 (234) | 0.227 | 0.183 | available |
| no_storm_within_3h | DFW | +12h | 1681 (234) | 0.239 | 0.183 | available |

Small cohorts: treat as indicative, not proof of severe-weather skill.

### Published failure cases

| Kind | Airport | Lead | Cutoff | Probability / threshold | Observed delay |
|---|---|---:|---|---|---|
| missed | ATL | +3h | 2025-01-10T10:00:00+00:00 | 0.035 / 0.146 | 442.0 min |
| false_alarm | ATL | +3h | 2025-07-12T20:00:00+00:00 | 0.612 / 0.146 | 21.0 min |
| declined | ATL | +6h | 2025-03-10T06:00:00+00:00 | 0.041 / 0.157 | -3.0 min |

## 5. Arrival capacity (AAR)

**Genuine facility AAR: unmet.** The organisers supplied none, and FAA ASPM requires credentials (logged in `artifacts/capacity/data_access.json`). No AAR RMSE exists. Two separately labelled substitutes are published.

### 5a. Capacity estimate (proxy): weather-regime high-demand frontier, q = 0.90

Target: `high_demand_observed_reporting_carrier_arrivals`. Baseline in brackets: training-only airport frontier with no weather. Held-out 2025, cutoffs after selection ended. Units: reporting-carrier arrivals/hour.

| Airport | Lead | n | Pinball q0.90 | Proxy RMSE | Share at/below frontier |
|---|---:|---:|---|---|---|
| ATL | +3h | 827 | 2.053 (2.085) | 22.67 (23.06) | 0.972 (0.975) |
| ATL | +6h | 827 | 2.063 (2.085) | 22.76 (23.06) | 0.972 (0.975) |
| ATL | +12h | 826 | 2.069 (2.087) | 22.77 (23.07) | 0.971 (0.975) |
| DFW | +3h | 1,412 | 2.367 (2.412) | 22.29 (22.94) | 0.870 (0.874) |
| DFW | +6h | 1,412 | 2.374 (2.412) | 22.07 (22.94) | 0.865 (0.874) |
| DFW | +12h | 1,410 | 2.366 (2.411) | 21.82 (22.93) | 0.864 (0.874) |

Row status: {'available': 30147, 'partial': 330}; backoff: {'regime': 30168, 'group': 309}. Pinball improves 1.5-2% on the no-weather baseline. Rare regimes (ATL convective/winter) back off to grouped cells; winter hours are a documented failure.

Accuracy experiments, both **rejected** under a rule fixed before scoring (at least 1% macro pinball gain; at most 2% RMSE and 5% per-cell pinball regression; selection on Sep-Dec 2024):

| Candidate | Macro pinball change | Macro RMSE change | Decision |
|---|---:|---:|---|
| Conditional weather / gust / unknown-wind regimes | +0.18% (worse) | -0.53% | Reject (`member-1-weather-accuracy-results.md`, integration branch) |
| Airport/lead residual quantile calibration | +1.29% (worse) | -2.26% | Reject |

### 5b. Observed reporting-carrier arrivals forecast (throughput, not AAR)

Held-out rows: 30,465; mean observed 35.0 arrivals/hour.

| Scope | RMSE weather | RMSE schedule-only | RMSE baseline |
|---|---|---|---|
| All hours | 9.26 | 9.38 | 15.43 |
| thunderstorm_forecast (n=899) | 15.87 | 17.24 | 26.41 |
| frozen_precip_forecast (n=146) | 22.10 | 33.77 | 37.00 |
| low_ceiling_lt_1000ft (n=2,101) | 10.78 | 12.63 | 20.33 |
| low_visibility_lt_3sm (n=279) | 12.34 | 17.72 | 24.89 |
| crosswind_ge_15kt (n=262) | 15.60 | 16.99 | 25.26 |
| peak_schedule_ge_train_p90 (n=2,592) | 11.12 | 11.81 | 12.45 |
| benign (n=24,667) | 8.75 | 8.56 | 13.79 |
| noaa_storm_event_hour_retrospective (n=558) | 21.25 | 25.40 | 31.86 |

Weather minus schedule-only RMSE: weather-impacted hours (n=2,932) **-1.83**, 95% CI [-3.46, -0.46]; all hours -0.13 [-0.40, +0.14] (not significant). Team agreement to present this: **pending**.

## 6. Decision support (latest integration branch only)

Illustrative arrival scenario, KATL cutoff 2025-07-12T20:00:00Z, anchor +3h, six-hour window: scheduled arrivals 287, estimated initial imbalance 84, peak 84, ending 0, constant capacity proxy 80/h. Status `scenario`; operationally eligible: False. Arithmetic on reporting-carrier schedules, not a measured queue.

Departure review priorities at the same snapshot: 2 flagged departures (61.2% and 37.0% against a 14.6% threshold). The operational metering/rescheduling decision remains unavailable (no verified demand, capacity and backlog).

## 7. Sources

| File | SHA-256 (first 16) |
|---|---|
| `artifacts/risk/evaluation.json` | `94a1622ef994054f` |
| `artifacts/risk/manifest.json` | `94e967c743226fe2` |
| `artifacts/capacity/manifest.json` | `9e15d370f639dc7f` |
| `artifacts/capacity_estimate/evaluation.json` | `4f2bc4356322882b` |
| `artifacts/capacity_estimate/manifest.json` | `e2078025cc5e974d` |
| `artifacts/capacity/throughput_evaluation.json` | `fee38eef60d35127` |
| `handover/member-1-calibration-evidence.json` | `39d551b65f085da9` |
| `output/delivery/arrival-scenario.json` (integration branch) | `deadc7022245d3ec` |
