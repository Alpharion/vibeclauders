# Challenge 5 delivery plan - contract v2

## 1. Outcome and operating model

Build a local decision-support prototype for an airport flow-management duty officer who must anticipate weather-related capacity reductions and severe departure delays. At an explicit historical cutoff, show the evidence available then, predicted hourly arrival acceptance rate (AAR), departure-delay probabilities, historical context, and recommendations requiring human review. No operational commands are sent.

The scored demonstration uses ATL/KATL and DFW/KDFW, fixed runway headings 080 and 180 degrees, and 3-, 6- and 12-hour forecast leads. Code accepts an airport registry rather than hardcoding these airports throughout the pipeline. Additional airports are a configuration capability, not an expansion of the scored dataset.

Use Python, pandas, scikit-learn, Streamlit and Plotly. Keep acquisition, models and UI as local modules with published artifacts. No separate service or deployment is needed.

**Execution assignment:** Member 2 is implemented in this chat. Members 1 and 3 are handed to external agents, each monitored by another teammate. Their supervisors launch and monitor those agents; this chat does not claim they have started. See `handover/README.md` for launch instructions and review checkpoints.

| Member | Responsibility | Handoff |
|---|---|---|
| 1, external | Public acquisition, canonical flights, weather features, genuine AAR, arrival demand and initial backlog | `handover/agent-1-data-capacity.md` |
| 2, this chat | Departure-risk models, normalized historical metrics, queue validation and human-review advice | `handover/agent-2-flight-risk.md` |
| 3, external | Shared configuration, dashboard, artifact integration, final acceptance and demonstration | `handover/agent-3-dashboard-integration.md` |

`handover/shared-contract.md` is the authoritative interface. No member silently changes paths, keys, units, split dates or semantics. Supervisors route incompatible changes to Member 2, then update producers and consumers together. Existing shared `flight_key` identifiers remain stable.

## 2. Scope and completion levels

### Required core

1. Reproducible public-data acquisition with bounded retries, caching and provenance.
2. Hourly AAR forecasts from genuine facility AAR labels; held-out RMSE versus a train-only baseline.
3. Probability of departure delay strictly greater than 45 minutes; chronological evaluation and calibration diagnostics.
4. Weather features demonstrably available at cutoff, including runway-relative crosswind and tailwind.
5. Airport-specific risk, historical trends and volume-normalized comparisons with explicit denominators.
6. Interactive historical replay with evidence, model limitations and one visible failure case.
7. Human-review recommendations with explicit prerequisites; queue estimates only where inputs are valid.

### Useful degraded deliverable

A schedule-only classifier, sampled historical trends and a working interface are useful while public inputs are pending. Label them **partial Challenge 5 coverage**. They do not establish weather-aware prediction, AAR capability, airport-wide demand or intervention benefits. Missing AAR is an unmet core requirement, not a successful fallback completion.

### Deferred extensions

Reroute/diversion ranking, ATIS transcription, live traffic, fuel estimates, network optimization, map refinement and deployment are outside the four-hour critical path. Existing live-weather UI may remain separate, but receives no work ahead of core acceptance. Geographic connections are schematic, not verified routes.

## 3. Verified starting evidence and first gate

The supplied CSV contains 148,273 records over 2023-01-01 to 2025-07-31; 25,299 touch ATL/DFW. It has no genuine AAR/ADR labels, wind direction, forecast issue/validity timestamps or weather-observation timestamp. Its weather cannot be assumed available at prediction time. Its sparse traffic cannot establish complete airport demand or initial backlog.

For departures, excluding cancelled flights and missing delay labels gives ATL 8,341 labelled flights (779 severe) and DFW 7,606 (990 severe), before timestamp or duplicate exclusions. Seven cancelled target departures have nonmissing departure delay: filtering null labels alone is insufficient. Actual training reports must recompute these counts and explain any additional exclusions.

**By minute 20**, Member 1 publishes a data-access decision: exact genuine AAR source, successful or failed acquisition evidence, label meaning/units, available dates, both-airport coverage, automated export method, and intersection with usable weather. A website URL is not proof that data can be acquired.

If genuine AAR cannot be obtained, its supervisor seeks an organizer-provided extract or target clarification. Do not bypass access controls or invent a proxy target. Continue weather features and explicitly identify the unmet requirement. Record access limits rather than repeatedly waiting on one provider.

## 4. Shared time, modelling and evaluation rules

- Use UTC-aware timestamps. Preserve original local flight date and schedule for stable IDs and whole-local-date splitting. Treat 2400 as next midnight; ambiguous/nonexistent local times are excluded and counted unless authoritatively resolved.
- Target hour is `[target_hour_utc, target_hour_utc + 1h)`. For lead h, `asof_utc = target_hour_utc - h hours`. Score departures inside that hour. A 3-hour lead is not the entire interval from cutoff through cutoff+3h.
- Evaluate leads 3/6/12. Queue simulation separately requires contiguous hourly capacity and arrival demand at one cutoff. Three isolated scored horizons cannot be silently interpolated into a queue forecast.
- For BOTH models: train 2023, validate/select 2024, test January-July 2025; group all horizons of a flight and whole dates in the same split. Fit encoders, imputers, scalers and historical baselines only on training data. Threshold/model selection uses validation only. Exclude replay cutoffs preceding the information used in selection.
- If AAR coverage cannot support those dates, publish a proposed chronological whole-date alternative and common coverage window before training. Candidate and baseline use the same split; never silently switch to random splitting. Insufficient test cohorts have unavailable metrics.
- Only observations available by cutoff and forecasts issued/available by cutoff and valid at target enter features. Preserve amended/conditional TAF groups. Raw CSV weather and post-event NOAA storm logs are not advance predictors.
- NOAA events can define retrospective held-out severe-weather cohorts and failure explanations. Keep annotations outside the inference feature allowlist.
- Test wind components using wind-from direction and fixed runway heading; report crosswind magnitude and nonnegative tailwind. Document degrees, knots, reference convention and missing direction.
- Prediction generation today for a 2025 cutoff is a backtest, not proof it was actually issued in 2025. Historical input availability is separate from generation time.
- Supplied flight schedules are retrospective reconstructions, not verified archived schedules available at cutoff. Disclose this limitation.

### Measures and comparison cohorts

| Output | Required measures and interpretation |
|---|---|
| AAR | RMSE in arrivals/hour, train-only airport/hour baseline RMSE, n, dates, airport and horizon; independently annotated severe-weather subset |
| Departure risk | Precision, recall, PR-AUC/average precision with definition, Brier, confusion counts, reliability bins, threshold, n and prevalence by airport/horizon |
| Normalized historical delay | Severe labelled departures / eligible labelled departures; sum(max(delay_minutes,0)) / eligible labelled departures; explicit sample coverage |
| Cancellation/missingness | Cancellation rate with known-status denominator; missing delay, ambiguous times and duplicate exclusions separately |
| Forecast alert rate | Flagged scored departures / scored departures; distinguish observed severe-delay rate and prediction coverage |
| Queue | Demand, initial/ending/peak backlog, served movements, recovery status and unresolved backlog; hourly discretization assumptions |
| Intervention | No total-delay/fuel savings without a supported counterfactual. Ground metering may redistribute rather than reduce delay. |

Do not replace AAR RMSE with a normalized alternative or convert probability into invented delay minutes. Compare airports on identical cohort definitions/windows and show volumes/coverage. Uncalibrated probabilities may be evaluated with Brier/reliability but must not be described as calibrated.

## 5. Member 1 - data and AAR

1. Publish acquisition decision at 20 minutes; canonical sample flights and representative real weather features by 45 minutes. Empty typed artifacts plus truthful status are acceptable when blocked; fabricated rows are not.
2. Acquire/cache genuine FAA AAR plus IEM historical TAF/METAR; implement public BTS download/preparation and NOAA retrospective ingestion. Log requested/retrieved coverage, schemas, retries, hashes and failures. Prioritize a small overlapping window before expanding years.
3. Publish configurable station mappings, canonical flights, normalized weather and cutoff-safe features. Preserve TAF probability/condition, amendment and validity relationships.
4. Fit pooled modest AAR model and train-only baseline using the common split. Do not substitute throughput for capacity. Time-weight quarter-hour records containing hourly rates rather than summing rates.
5. Publish held-out forecasts, evaluation and provenance. Uncertainty bounds need a stated method and held-out coverage; otherwise null.
6. Publish demand/backlog only with established population, coverage and availability. BTS on-time records are not automatically complete airport demand. Contiguous planning forecasts require validated model support.

## 6. Member 2 - completed locally, refreshed after handoff

1. Build reproducible schedule-only baseline from an explicit predictor allowlist. Exclude actual outcomes, delay causes, cancellation outcomes, realized taxi times and undated weather from predictors.
2. Compare regularized logistic regression and modest boosted trees; select model/threshold on validation only. Export held-out replay predictions, per-airport/horizon evaluation, normalized history and manifest.
3. Consume Member 1 canonical flights and weather features strictly. Reject future-available/duplicated/inconsistent snapshots; report coverage loss. Compare weather and schedule models on matched cohorts. Missing weather retains labelled baseline and unmet weather status.
4. Implement conservation-tested arrival queue simulation. Require genuine AAR provenance, complete matching-population demand, known cutoff backlog, common cutoff and contiguous hours. AAR never acts as departure capacity; unknown backlog is not zero.
5. Supply human-review arrival-metering advice when a forecast deficit supports it. Withhold flight-specific timing when state/eligibility is missing. Never change airborne flights or invent intervention benefits.
6. Publish commands, tests, measured results, compatibility notes and actual Member 2 status. Member 3 refreshes with Member 1 outputs and verifies integration. Local baseline completion does not imply full project completion.

## 7. Member 3 - application and acceptance

1. Own root dependencies, stable shared helpers/configuration and final integration. Preserve `flight_key`; airport additions must not change modelling logic.
2. Validate manifests/schema versions and exact snapshot keys. Cache by run/file identity. Missing or mixed outputs show unavailable states, not plausible defaults.
3. Fix the existing traffic view window mismatch: scored departures belong to the target hour after the lead; queue planning has its own window. Drive controls from available snapshots and disclose partial coverage.
4. Present risk, historical trends and normalized comparisons. History respects cutoff or is explicitly revealed retrospective evaluation. Actual outcomes remain behind Reveal outcomes in replay.
5. Show AAR alongside genuinely comparable arrival demand, queue trajectories and unresolved recovery. Show uncertainty method/source and eligibility limits. Recommendations are for review, not transmitted actions.
6. Integrate success and failure/unavailable scenarios. Verify both airports/leads, stale/missing artifacts, mixed snapshot rejection, outcome masking and inputs beyond the demo.
7. Deliver one launch command, exact environment, runbook, requirement checklist and three-minute demo. Reconcile installed versions with `requirements.txt`; do not assume old constraints match.

## 8. Parallel schedule and supervisor gates

Times are elapsed from coordinated kickoff, not promises that inaccessible data will arrive. A supervisor may cut optional scope; no checkpoint waives a core requirement.

| Time | Member 1 | Member 2 here | Member 3 | Supervisor evidence |
|---|---|---|---|---|
| 0-20m | AAR access proof; audit | Labels; baseline interfaces | Confirm v2 and target hours | Ownership, access decision, version |
| 20-45m | Small canonical/weather handover | Schedule candidates | Load real/empty typed artifacts | Keys, units, availability assertions |
| 45-90m | Common coverage; AAR fit | Weather consumer; normalized metrics; queues | Trends/evidence UI | Actual run or dependency blocker |
| 90-120m | Held-out AAR/evaluation | Baseline/optional weather exports | First replay | Both airports/leads, split readback |
| 120-180m | Coverage/provenance fixes | Advice/failure checks | Core acceptance | Requirements and measured vs simulated |
| 180-210m | Reproducibility | Final regression fixes | Cached demo/docs | No hidden interface changes |
| 210-240m | Defects only | Defects only | Rehearsal/delivery | Valid submission, outputs/limitations |

Supervisors request reports at gates and after blockers: files, tested commands/exit status, coverage, missing prerequisites, next action and owner. Complete without artifact readback is not accepted. Status format and escalation rules are in `handover/README.md`.

## 9. Acceptance checklist

- [ ] Both airports and all three leads have real scoped outputs, or individual unmet capabilities are stated.
- [ ] Authentic AAR target; chronological held-out RMSE and baseline.
- [ ] Departure target >45 minutes; cancellation/missing exclusions reported.
- [ ] Issue/availability/validity checks pass; future data cannot change earlier replay.
- [ ] Fixed runway headings and wind components tested.
- [ ] Automatic public ingestion, cache and failure handling verified.
- [ ] Normalized comparisons show numerator, denominator, cohort and coverage.
- [ ] Historical trends, uncertainty, evidence and human ownership visible.
- [ ] Queue/advice supported by complete inputs or explicitly unavailable.
- [ ] Visible explained failure; no fabricated performance or causal savings.
- [ ] Reproducible app and focused three-minute demo.

Rubric: realism 20%, technical soundness 25%, honest evaluation 20%, trust/traceability 20%, impact 10%, time discipline 5%. Predictive evidence precedes optional UI. This plan specifies work; only measured results and accepted deliverables close its checklist.
