# Member 1: rubric-focused model handback

The incumbent capacity estimate is retained. Two bounded experiments reduced proxy RMSE but worsened the fixed q=0.90 pinball objective; neither is an accepted model improvement. The delivered production change strengthens validation of model outputs and publication consistency. No frontend redesign or model publication was introduced. Follow-up parallel work now displays exact-key controller review actions and an explicitly illustrative arrival scenario in the existing Compare panel.

Integration branch: `codex/member-1-accuracy-integration`, incorporating main `a075bf6`, weather experiment `a970fe5`, calibration experiment `a05882b`, and validation hardening `9014bfb`. The coordinator also corrected the weather experiment's test-window handling. This branch is for review; this sprint does not merge it to main.

## Deliverables against the official rubric

Source: *Autonomous SG 2026 — Airbus Track*, Challenge 5 and judging rubric, pages 5–8. Weights below are rubric weights, not predicted marks.

| Criterion | Weight | Concrete deliverable and evidence | Remaining limitation |
|---|---:|---|---|
| Problem realism | 20% | Flow-planner replay for ATL/DFW; hourly estimates and >45-minute departure-delay risk at 3/6/12 hours. Existing dashboard and `JUDGING-DEMO.md`. | Reporting-carrier coverage cannot establish whole-airport capacity. |
| Technical soundness | 25% | Weather/flight joins available at cutoff; runway-relative wind using ATL 080/DFW 180; frozen capacity frontier; separate estimates and genuine AAR; automated extracted-release verification. | Capacity is inferred from high-demand throughput, not independently measured physical capacity; no estimated uncertainty bounds. |
| Honest evaluation | 20% | Baseline comparisons, per-airport/per-lead RMSE below, fixed selection criteria, two reproducible rejected experiments, rare-weather and false-alarm examples. | Proxy error is not independently validated facility AAR error; 2025 has already been inspected. |
| Trust and traceability | 20% | Hash-bound publications, source/model identifiers, visible support and assumptions, cutoff/reveal protections; stricter numeric, interval, metadata and document consistency checks. | Loader validation establishes structural consistency, not scientific validity of assumptions. |
| Impact | 10% | Existing equal-alert-workload evaluation: ATL +3h recall 52.2% versus historical-rate baseline 43.2%; controller review priorities in Compare and a companion brief; a separately labelled arrival scenario. | Precision is 26.1%; no measured delay/fuel savings, intervention trial or validated operational queue. |
| Time discipline | 5% | Three-minute demonstration script and bounded parallel experiment scope; reproduce with commands below. | Submission time and human rehearsal/sign-off must be recorded by the team; not inferred from automated checks. |

## Accuracy deliverable

Organisers do not provide genuine AAR labels. The model supplies an explicitly labelled capacity estimate for reporting carriers. Its validation target is high-demand observed throughput. This is a useful measurable proxy with disclosed assumptions; it is not a reason to wait for organiser labels or relabel throughput as verified facility AAR.

Existing published January–July 2025 replay results from `artifacts/capacity_estimate/evaluation.json` (cutoffs after selection ended). Baseline is the train-only airport frontier. Units: reporting-carrier arrivals/hour. These are the retained model's results, not gains from this optional sprint.

| Airport | Lead | Hours | Proxy RMSE | Baseline RMSE | q0.90 pinball | Baseline pinball |
|---|---:|---:|---:|---:|---:|---:|
| ATL | 3 | 827 | 22.6660 | 23.0610 | 2.0526 | 2.0855 |
| ATL | 6 | 827 | 22.7643 | 23.0610 | 2.0627 | 2.0855 |
| ATL | 12 | 826 | 22.7747 | 23.0733 | 2.0686 | 2.0870 |
| DFW | 3 | 1412 | 22.2868 | 22.9356 | 2.3669 | 2.4120 |
| DFW | 6 | 1412 | 22.0678 | 22.9356 | 2.3736 | 2.4120 |
| DFW | 12 | 1410 | 21.8248 | 22.9261 | 2.3662 | 2.4114 |

Do not substitute the separate arrivals-throughput forecast RMSE (9.26 versus 15.43) for these capacity-proxy metrics. Repeated leads are not independent target hours. No significance claim is made.

## Optional experiment decisions

The primary objective was fixed before observing results: at least 1% reduction in equal-weight six-cell q0.90 pinball, with at most 2% macro RMSE regression and 5% per-cell pinball regression. Training is 2023; calibration alone uses January–August 2024; common selection is September–December 2024. The high-demand screen remains the 2023 75th percentile. Each experiment scores the same 5,325 eligible snapshots / 1,775 distinct airport target-hours.

| Candidate | Proxy RMSE change | Pinball change | Decision |
|---|---:|---:|---|
| Conditional weather / gust / unknown-wind treatment | -0.5302% | +0.1794% | Reject |
| Airport/lead quantile residual calibration | -2.2597% | +1.2932% | Reject |

Lower RMSE alone does not justify changing the capacity-quantile estimator. Neither candidate is imported by the production pipeline. Full cell/cohort/support evidence and source hashes are in `member-1-weather-accuracy-results.json` and `member-1-calibration-evidence.json`; accompanying Markdown records methods and failures. The weather report now excludes its initial invalid pre-selection-cutoff test comparison and discloses that earlier inspection; its selection result is unchanged.

## Reproduction and release acceptance

1. `python -m src.data_capacity.weather_accuracy`
2. `python -m src.data_capacity.capacity_calibration`
3. `python -m tools.delivery.verify_release`
4. Read `output/delivery/VERIFICATION.md`, `verification.json` and the final ZIP receipt. A failed gate blocks release. Automated checks do not replace manual browser/map checks or the timed rehearsal.

Validation hardening details: `member-1-validation-results.md`. The original Member 1 status/check results are historical; current combined checks are recorded in the generated release evidence and the sprint status update. Published model/data/risk artifacts remain unchanged.

## Implemented missing-input follow-up

The user requested implementation in parallel after confirming the old decision publication had zero actions. Three independent modules now supply schedule-derived arrival demand/backlog, capacity scenario inputs, and visible exact-key flight review priorities. The coordinator combines them in `src/flight_risk/arrival_scenario.py` and exposes the same result through `python -m tools.delivery.arrival_scenario --airport KATL --asof 2025-07-12T20:00:00Z --lead 3 --window 6`.

Compare → Proposed actions now shows ranked departure review priorities and an illustrative arrival scenario. Demand uses reconstructed scheduled reporting-carrier arrivals. Backlog is an aggregate imbalance over 24 completed hours, starting from an explicit zero warmup assumption. Future actual arrivals do not affect it. Scheduled gate times, runway counts and cancellations differ, so this is not identified waiting aircraft. Schedule/observation availability is assumed in replay and not verified.

Capacity is held constant across the scenario window using the exact-cutoff selected 3/6/12h model estimate. The original forecast target remains visible; unscored hourly rates are scenario assumptions. The strict adapter still reports missing hours. No existing operational decision publication, physical AAR validator, risk model or capacity model was changed. Missing/invalid inputs withhold the scenario. The operational recommendation block still reports its original prerequisites separately.

At ATL 2025-07-12 20:00 UTC, +3h anchor, six-hour scenario: scheduled demand 287, estimated initial imbalance 84, assumed rate 80/hour, ending imbalance 0. These are arithmetic scenario outputs, not measured queue recovery or delay savings. Exact-key departure review priorities remain based only on published probabilities and thresholds, with no future outcomes exposed.

Implementation details and focused tests: `arrival-inputs-results.md`, `capacity-scenario-results.md`, `dashboard-review-actions-results.md`. The first combined gate's tests and app checks passed, but correctly rejected release because the newly requested follow-up changed runtime during verification. A stable-tree gate supersedes it.

## Follow-up priority

Present the working model, actual baseline comparisons, a failure case and provenance first. Next model work should test a predeclared better capacity proxy or severe-weather treatment with chronological evaluation and adequate support; sparse severe regimes and missing uncertainty remain real gaps. Any whole-airport scaling needs independent coverage assumptions/evidence. Demonstrating operational delay savings requires a separately validated intervention simulation. These are follow-ups, not claims of this 15-minute delivery.
