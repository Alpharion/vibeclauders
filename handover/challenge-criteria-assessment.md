# Challenge 5: implementation and evidence assessment

This assessment concerns the merged dashboard plus presentation follow-up, not the older build assessed by `presentation-readiness-review.md`. Requirement/rubric wording is directly checked against `reference/Autonomous SG 2026_Airbus Track.pdf`, Challenge 5 and rubric (PDF pages 5–8), extracted with pypdf in the clean environment; the repository presentation review provides additional context. The original PDF was supplied by the user; this assessment does not reinterpret document text as user instructions. Implementation claims below come from source code and committed publication manifests/evaluations. This was a text-content check, not a visual-layout audit of the source PDF.

The outcome is a working historical decision-support prototype with explicit model-estimated capacity, delay classification, controller review priorities, illustrative arrival scenarios and visible processing evidence. Independent whole-airport AAR validation and operational benefit remain unproved. AAR estimates are delivered despite the absence of organiser labels; missing labels are a validation boundary, not a reason to leave the estimator absent.

## Required deliverables and where to demonstrate them

| Challenge deliverable | Current implementation and frontend | Assessment and evidence boundary |
|---|---|---|
| Multi-source weather/flight integration | Weather and Traffic join airport/time keys; Evaluation explains processing and provenance, including the expanded “How datasets become forecasts” panel. `src/data_capacity/pipeline.py`, `features.py`, `flights.py`; capacity manifest binds outputs. | Implemented with explicit latency/validity assumptions. IEM issue times are not actual receipt timestamps. |
| Hourly AAR prediction at 3/6/12 hours, evaluated by RMSE | Capacity card plus Evaluation's model evidence table show a weather-conditioned reporting-carrier frontier and proxy-target RMSE at all six airport/lead cells. `capacity_estimate.py` and its four published payloads. | Model estimate delivered. Independent facility-AAR accuracy is not established; this target is high-demand observed reporting-carrier throughput. |
| Departure delay over 45 minutes classification | Traffic risk and Compare review priorities; Evaluation precision/recall/average precision/Brier, baseline and failures. `src/flight_risk/` and risk publication. | Implemented on held-out sampled departures. Modest precision and uncalibrated probabilities remain material. |
| Interactive risk, trends and controller recommendations | Existing tabs, airport/lead/cutoff selection, outcome reveal, normalised history; Compare ranks threshold-crossing departures and recommends review of weather and airline/inbound-aircraft state. | Visible human review aid; no transmitted flight instructions. Outcome labels are hidden until reveal. |
| Automatic public-data processing | Evaluation explains steps and exposes reproduction commands; README documents acquisition through publication. | Implemented scripted workflow with cached downloads and manifests. Viewing the UI does not launch processing. This reassessment did not repeat public downloads or publish newly trained models; the capacity fit was reproduced in memory. |

## What the capacity model means

The published estimator fits a high-demand weather frontier using 2023 reporting-carrier arrivals. The high-demand screen is the airport's training-period 75th percentile of scheduled arrivals. Within each airport/lead/weather cell it takes the 90th percentile of observed arrival throughput, requiring at least 30 distinct training target hours. Sparse cells back off through broader weather groups to the airport frontier. The baseline is a training-only airport frontier without weather stratification.

This is an assumption about attainable throughput, not a measured runway/facility limit. Demand below physical capacity, flow programmes, carrier coverage and rare-weather support can distort it. There is no whole-airport scaling and no estimated uncertainty interval. At the demo cutoff (ATL, 12 July 2025 20:00 UTC, +3h), the estimate is 80/hour, partial: a degraded-weather fallback supported by 476 training hours. +6h/+12h yield 81/hour with available status in that publication; neither status establishes independently verified AAR.

### RMSE, calculated and interpreted

For the same eligible held-out hours, `RMSE = sqrt(sum((prediction - observed_proxy)^2) / n)`. The unit is reporting-carrier arrivals per hour. Squaring penalises large errors; RMSE is not average absolute error, a percentage, or an uncertainty interval. For errors 2 and 4, RMSE is sqrt(10), about 3.16. Lower is better on an identical target and cohort.

A value around 22 here means roughly that scale of squared-error discrepancy against the proxy; it does not establish a 22-flight error against true facility AAR. The model deliberately targets an upper quantile rather than the conditional mean. Therefore RMSE is reported to satisfy an interpretable accuracy comparison, while the fixed model-selection objective also considers q0.90 pinball loss: for residual u = observed minus predicted, loss is `max(0.90*u, -0.10*u)`. Lower pinball is better for the specified frontier objective.

The table is generated from `artifacts/capacity_estimate/evaluation.json`, test split January–July 2025, emitted cutoffs after selection ended. Percentage improvement is `1 - model_RMSE / baseline_RMSE`; it is descriptive, not a significance result.

| Airport | Lead h | Eligible hours | Proxy RMSE | Baseline RMSE | Relative RMSE improvement |
|---|---:|---:|---:|---:|---:|
| KATL | 3 | 827 | 22.6660 | 23.0610 | 1.71% |
| KATL | 6 | 827 | 22.7643 | 23.0610 | 1.29% |
| KATL | 12 | 826 | 22.7747 | 23.0733 | 1.29% |
| KDFW | 3 | 1412 | 22.2868 | 22.9356 | 2.83% |
| KDFW | 6 | 1412 | 22.0678 | 22.9356 | 3.78% |
| KDFW | 12 | 1410 | 21.8248 | 22.9261 | 4.80% |

These six rows reuse target hours across leads; their counts must not be added as independent observations. The separate arrivals-throughput forecasting model is a different target and its 9.26/15.43 result is not substituted into this capacity table or the presentation. Genuine-AAR fields remain separate.

Two optional experiments were evaluated with a fixed late-2024 selection protocol. Weather changes reduced proxy RMSE 0.5302% but worsened pinball 0.1794%; residual calibration reduced RMSE 2.2597% but worsened pinball 1.2932%. Both failed the predefined adoption rule, so neither replaced the incumbent. This is negative experimental evidence, not a claimed accuracy gain. See `member-1-accuracy-results.md` and machine-readable experiment evidence.

### Independent reproducibility reassessment

The coordinator rebuilt the estimator in memory from hash-verified published inputs. All 30,477 forecast rows matched, the fitted model matched exactly, and all reproduced validation/test metrics matched the publication. No publication changed and no public dataset was downloaded. `handover/model-reassessment-evidence.json` records the source hashes, run, equality checks and test metrics. This proves reproducibility of the committed estimator/results; it does not convert proxy validation into independent facility-AAR accuracy.

## Delay model: performance and interpretation

The published risk model is histogram gradient boosting, with schedule-only fallback where weather cannot be supported. Airport-local flight dates define 2023 training, 2024 selection and January–July 2025 test periods. Features use information available by the forecast cutoff; realised delay/cancellation labels are not forecast features. The publication contains 10,604 horizon predictions for 3,537 unique test flights. No post-hoc probability calibrator was adopted.

Precision = true severe alerts / alerts; recall = detected severe departures / all eligible severe departures. Average precision summarises the precision–recall ranking; the published `pr_auc` field uses average precision, not a trapezoidal curve area. Brier is mean `(probability - binary outcome)^2`, so lower is better. A well-ranked model can still have imperfect calibration; these probabilities are not guarantees.

Values below are model/baseline. The baseline is the smoothed training-only airport/local-hour severe-delay rate, with its own validation-selected threshold. This table is not the equal-alert-budget comparison.

| Airport | Lead h | Departures | Precision M/B | Recall M/B | Average precision M/B | Brier M/B |
|---|---:|---:|---:|---:|---:|---:|
| KATL | 3 | 1763 | 0.261/0.215 | 0.522/0.575 | 0.262/0.208 | 0.106/0.112 |
| KATL | 6 | 1763 | 0.292/0.215 | 0.500/0.575 | 0.275/0.208 | 0.106/0.112 |
| KATL | 12 | 1759 | 0.312/0.215 | 0.320/0.575 | 0.258/0.208 | 0.108/0.112 |
| KDFW | 3 | 1774 | 0.235/0.198 | 0.489/0.731 | 0.249/0.196 | 0.123/0.125 |
| KDFW | 6 | 1774 | 0.255/0.198 | 0.500/0.731 | 0.257/0.196 | 0.122/0.125 |
| KDFW | 12 | 1771 | 0.263/0.198 | 0.496/0.731 | 0.271/0.196 | 0.122/0.126 |

The thresholded baseline has higher recall in these cells, but lower precision and a different alert workload. Do not claim the model improves every metric. For the separate equal-alert-workload experiment at ATL +3h, both are evaluated at 456 alerts among 1,763 departures: model recall 52.19% versus baseline expected recall 43.18%, and precision 26.10%. The baseline tie handling produces expected counts (98.45 versus model 119 true alerts), not a fabricated integer intervention outcome. This is about 9.01 percentage points or 20.87% relative more severe cases detected at the same alert budget. No delay-minute, fuel or causal savings follow from this result.

## How automatic processing actually works

1. **Acquire inputs.** The supplied BTS-derived flight sample is read locally. Public BTS On-Time PREZIP monthly archives provide reporting-carrier traffic. IEM METAR and TAF archives supply weather; NOAA storm-event files supply retrospective evaluation cohorts. FAA ASPM genuine-AAR acquisition is separate and currently unavailable. Network acquisition is scripted; sources record URL, retrieval time, hash, coverage and failures.
2. **Canonicalise flights and traffic.** Flight identities and airport metadata are standardised. Local schedules are converted to UTC with explicit airport timezones, `2400` handling and DST ambiguity flags. Unresolvable times are audited. Hourly scheduled counts and actual runway counts retain their different definitions: schedules include cancellations, actual counts exclude cancelled/diverted arrivals. Missing download months remain absent, not zero. The supplied flight sample and fuller reporting-carrier traffic are distinct populations.
3. **Decode weather and make cutoff-aware features.** Weather is aligned by station, issue/validity time, airport and target hour. METAR/TAF availability adds a declared ten-minute publication-latency assumption. TAF maximum age is 12 hours, METAR maximum age 2 hours, and the configured TAF validity assumption is 30 hours because archived headers are incomplete. Conditional weather is not treated as certain realised weather. Wind is resolved relative to the challenge headings ATL 080 and DFW 180. Embedded undated daily weather in the supplied flight CSV is not used as a forecast feature. NOAA storms remain retrospective annotations.
4. **Fit and evaluate without replacing the target.** The capacity pipeline publishes capability-specific outputs; missing genuine AAR produces an explicit unavailable genuine-AAR forecast. The separate estimator reads hash-verified published weather/traffic and emits model-estimated capacity. Risk training auto-detects canonical flights/weather/storm annotations, verifies their upstream manifest and trains from immutable byte snapshots. Chronological splits and selection boundaries are retained.
5. **Publish and consume evidence.** Payloads are written with run IDs, row counts, source metadata and SHA256 values; the producer manifest is published last. The dashboard verifies hashes and contracts before using a publication, rejecting inconsistent or unavailable optional groups. Failed downloads, insufficient support, missing coverage and rejected publications remain visible, not filled with plausible-looking numbers.

Reproduce from the repository root:

```text
python -m src.data_capacity run
python -m src.data_capacity estimate-capacity --from-published
python -m src.flight_risk train
python -m src.flight_risk verify
python -m tools.delivery.verify_release
```

`run --cache-only` reuses cached public inputs; `run --flights-csv PATH` and `train --sample PATH` select a supplied sample. These commands can create new publications, so rerun in a separate experiment checkout and reverify before replacing the presentation build. Availability of code and a previous publication do not prove a fresh network run succeeded today. The current publication evidence is capacity/data run `m1-20261031T065014Z-eacdd5`, capacity estimate `m1-capest-20261031T072310Z-a27968`, and risk `0949771a54bb4e49b4e215528eb5d46b`.

No LLM is used. Statistical estimation/classification and deterministic review templates provide reproducible numerical predictions and traceable wording. This is the explicit LLM/non-LLM design rationale rather than an omitted component.

## Scenarios, trust and the pitfalls to avoid

Compare's illustrative arrival scenario reconstructs schedule demand, estimates a backlog imbalance over 24 completed hours starting from an explicit zero warmup anchor, and assumes one exact-key 3/6/12h capacity estimate stays constant through the planning window. Future actual arrivals cannot affect the calculation. Historical schedule/observation receipt times are not verified, gate schedules differ from runway counts, and warmup backlog may be wrong. It is a scenario, not identified waiting aircraft. The displayed conservation is `end = max(0, start + demand - floor(capacity_proxy))`; it is not an optimisation or evidence of recovery caused by an intervention. Operational metering/rescheduling still requires verified prerequisites.

| Challenge pitfall | Safeguard | Remaining qualification |
|---|---|---|
| Time leakage | Cutoff filters, chronology checks, whole-date splits, selection-end cutoffs, outcome reveal separation | Archive receipt times and reconstructed schedules require declared replay assumptions; 2025 has already been inspected and is not pristine external validation. |
| Ignoring runway direction | Crosswind/tailwind from ATL 080 / DFW 180 | Fixed challenge headings are not live runway configuration or joint-runway capacity. |
| Single-airport overfit | Both ATL/DFW reported; registry-based code; synthetic third-airport tests | Configurability does not establish generalisation accuracy elsewhere. |
| Raw delay comparisons across airports | Normalised severe-delay rates and delay-per-flight with denominators | Sample representativeness and cancellation/missing-label exclusions still matter. |

## Judging rubric and final acceptance

| Criterion | Weight | Evidence to show | Assessment |
|---|---:|---|---|
| Problem realism | 20% | Flow planner, forecast lead, visible review priority and failure example | Concrete problem/user; historical prototype rather than live ATC deployment. |
| Technical soundness | 25% | Working frontend, model/RMSE explanation, automated processing, explicit no-LLM rationale | Implemented; verify the actual final runtime and dependency environment. |
| Honest evaluation | 20% | Six-cell baselines, same-cohort comparisons, negative experiments, false alert | Strong transparency; modest accuracy and proxy-target validation remain. |
| Trust/traceability | 20% | Cutoffs, source/run hashes, support/backoff, assumptions before scenario metrics, unavailable states | Structural safeguards, not proof that modelling assumptions are true. |
| Impact | 10% | Equal-alert-workload detection improvement | Demonstrated alert quality only; no tested operational intervention. |
| Time discipline | 5% | Three-minute script, recorded rehearsal and actual submission receipt | Human timing and submission remain to be recorded. |

No judge score or supervisor sign-off is inferred. Current automated results belong in `output/delivery/verification.json`, matched to the final runtime fingerprint and archive receipt. The coordinator is rerunning the fresh-environment release gate after the explanation changes; this assessment does not preclaim its test count or outcome. Real browser/map checks, rehearsal duration, submission and human acceptance remain separate entries in `SUBMISSION-CHECKLIST.md`.
