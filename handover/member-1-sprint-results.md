# Member 1 sprint results (30-minute sprint)

- Baseline: `737b46852c2d4b98e7c01e68ed7e3888f6542c5c`, via the handoff branch `codex/parallel-handoffs-30min` (`c01500a`). Working branch: `codex/member-1-capacity-30min`.
- Sprint started at 2026-10-31T07:19:14Z. Member 2's branch was not used.
- **State: ready_for_review.** Both P0 items are complete. No supervisor sign-off is implied.

## P0 1: traffic-chart crash fixed

`src/dashboard/plots.py` `reporting_chart` used `add_vline` with a Timestamp and an annotation; Plotly's annotation step does Timestamp + int arithmetic that pandas rejects. The fix draws the same dotted cutoff line as a shape and adds a separately positioned "Cutoff" annotation. Reveal masking and the test assertion are unchanged. `tests/dashboard/test_additions.py::test_actual_traffic_counts_need_reveal` now passes.

## P0 2: model-estimated capacity proxy

`python -m src.data_capacity estimate-capacity --from-published` reads only the committed `traffic_hourly.parquet` and `weather_features.parquet`. It verifies them against the SHA256 values in `artifacts/capacity/manifest.json` (upstream run `m1-20261031T065014Z-eacdd5`) and against the row run IDs, then publishes `artifacts/capacity_estimate/`. The data pipeline isn't called, and nothing is downloaded or retrained.

Published run: **`m1-capest-20261031T072310Z-a27968`** (status `partial`: a proxy, never a complete capability).

| File | Content |
|---|---|
| `forecast.parquet` | 30,477 held-out rows (KATL and KDFW, leads 3/6/12, cutoffs from 2025-01 to 2025-07): 30,147 `available` and 330 `partial` (backed off to the degraded/VFR group cell); 0 `unavailable` |
| `evaluation.json` | Proxy metrics for validation (2024) and test (2025), regime cohorts, status and backoff counts |
| `assumptions.json` | Population, demand screen, method, quantile, backoff, regime definitions, runway headings, no scaling |
| `model.json` | Demand thresholds, every frontier cell with its support, and the baseline frontier; enough to reproduce the estimate |
| `manifest.json` | v2 envelope, SHA256 of all four payloads, row counts, input paths, hashes and upstream run; written last, after the payloads are validated in a sibling temp directory |

**Method (`high_demand_weather_frontier_v1`).** Every parameter was fixed before fitting; nothing was tuned.

1. **Demand screen:** an hour counts as high-demand when its scheduled reporting-carrier arrivals are at or above the airport's 2023 75th percentile. That works out to ATL 57 and DFW 60 arrivals per hour. Thresholds come from one row per (airport, hour), so the three leads don't count an hour three times.
2. **Weather regime:** each snapshot gets a regime from the cutoff-safe features, in this priority order: convective (TS), winter (frozen precipitation), IFR (ceiling < 1000 ft or visibility < 3 SM), wind (crosswind ≥ 15 kt or tailwind ≥ 10 kt, against the challenge headings ATL 080 / DFW 180), MVFR (ceiling < 3000 ft or visibility < 5 SM), then VFR. A missing ceiling or visibility gives "unknown".
3. **Estimate:** the 0.90 quantile of observed arrivals in the high-demand 2023 hours of the cell (airport, lead, regime). Leads are never pooled. `support_n` is the number of unique training hours.
4. **Backoff:** cells with fewer than 30 training hours fall back to the airport's degraded/VFR group, then to all regimes. Each row records its cell and backoff level.

**Measured on held-out 2025.** The target is `high_demand_observed_reporting_carrier_arrivals`, a proxy, not facility AAR.

| Airport | Lead | Pinball loss q0.90 (frontier) | Baseline (airport quantile, no weather) | n |
|---|---|---|---|---|
| KATL | 3 / 6 / 12 | 2.053 / 2.063 / 2.069 | 2.085 / 2.085 / 2.087 | 827 / 827 / 826 |
| KDFW | 3 / 6 / 12 | 2.367 / 2.374 / 2.366 | 2.412 / 2.412 / 2.411 | 1412 / 1412 / 1410 |

`high_demand_throughput_rmse` is about 22 for both the frontier and the baseline. That's expected: an upper-quantile frontier sits well above typical throughput. The share of high-demand test hours at or below the frontier is 0.97 at ATL and 0.86–0.87 at DFW, compared with the nominal 0.90.

Weather does lower the estimate where training data supports it: at DFW +6h, VFR 74.0, wind 71.8, convective 67.4, MVFR 64.0, IFR 61.0. ATL has only 4 convective and 0 winter training hours at high demand, so those snapshots back off to the degraded group.

**Visible failure:** in the winter cohort, the frontier stays around 68–80 while observed throughput is 4–28 (2 ATL hours, 7 DFW hours). Winter storms are too rare in 2023 to support a cell, and mass cancellations aren't capacity.

## Frontend binding (existing panels only)

- **Loader:** a new optional `capacity_estimate` group in `src/dashboard/data.py`, with its own manifest hash verification, run-ID checks and strict row checks. Rows are rejected for a wrong `label_kind`, a non-null `aar_observed`, null or later-than-cutoff timestamps on usable rows, or bounds present while uncertainty is unavailable. The group is included in the cache fingerprint and adds a "Capacity estimate (proxy)" capability (partial).
- **Arrival capacity card:** genuine `facility_aar` at the exact key is preferred. Otherwise it shows the estimate at the same exact key, labelled **Estimated arrival capacity - reporting carriers**, with a caption giving the model-proxy note, method, cell, backoff, support and "uncertainty unavailable".
- **Evaluation panel:** the existing AAR RMSE table and "Genuine FAA AAR labels not loaded" banner are kept. Underneath, a proxy section shows the method, target, run, held-out metrics and limitations. Observed throughput per regime stays hidden until **Reveal outcomes** is on.
- **Separation:** estimates are a separate bundle table. They never enter `forecast`, the AAR trend, the queue or the AAR capability, and the queue and metering refusals are unchanged. No tabs, controls or navigation were added.

## Checks (Windows; each run separately, real exit codes)

| Command | Exit | Result |
|---|---|---|
| `python -m pytest tests/dashboard/test_additions.py::test_actual_traffic_counts_need_reveal -q` | 0 | 1 passed |
| `python -m pytest tests/data_capacity tests/dashboard -q` | 0 | 252 passed |
| `python -m pytest tests/flight_risk -q` | 0 | 96 passed |
| `python -m pytest tests -q` | 0 | 348 passed (baseline: 320 passed, 1 failed) |
| `python -m src.flight_risk verify` | 0 | risk run `0949771a54bb4e49b4e215528eb5d46b` |
| `python -m src.data_capacity estimate-capacity --from-published` | 0 | run above |
| AppTest on the real repository artifacts | – | KATL and KDFW × leads 3/6/12 × reveal off/on: no exceptions; estimate card shown (ATL 81.0; DFW 74.0, or 65.0 at +12h); proxy evaluation shown |

The new tests are `tests/data_capacity/test_capacity_estimate.py` (9) and `tests/dashboard/test_capacity_estimate.py` (18). They cover:

- held-out actuals can't change estimates or thresholds
- future and missing timestamps are rejected
- an input hash mismatch is refused
- regime priority
- support counted per lead
- the published group's integrity, with frozen input hashes rechecked
- genuine-AAR preference and exact-key fallback for both airports and all leads
- five rejection cases and a hash-tamper case
- the app works with the estimate absent, and estimates stay out of the AAR trend and the queue
- AppTest for both airports × 3 leads × reveal

Frozen paths (`artifacts/capacity`, `artifacts/risk`, `data/**`, `src/shared.py`, `app.py`, `.streamlit`, requirements, `src/flight_risk`, `tests/flight_risk`) are byte-unchanged.

## Limitations

- This is a capacity proxy for BTS reporting carriers only. It isn't facility AAR, and it isn't scaled to whole-airport rates.
- It assumes high-demand throughput reflects attainable rates. Flow programmes, demand below capacity and coverage gaps can make it understate physical capacity.
- No uncertainty bounds (`uncertainty_kind='unavailable'`). Rare regimes (ATL convective/winter) back off to group cells.
- The 2025 test throughput sits below the 2023-fitted frontier at ATL (0.97 at or below), so the frontier is conservative there.
- Not done after P0 (both optional): the all-missing traffic-total display fix and layout adjustments.
