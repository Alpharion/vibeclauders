# Member 1: 15-minute accuracy extension

The user has allocated 15 additional minutes and prioritised model performance, accuracy and Challenge 5 requirements over optional display polish. This is an external Member 1 handoff. The existing implementation at `5805f89b8ae908b330e1e981536f52ae1725c2ee` is already reviewed and merge-ready for its original scope. Preserve that checkpoint; an experiment that does not improve validation is not a reason to replace it.

## Copy-ready assignment

You are Member 1. Use a separate branch such as `codex/member-1-accuracy-15min`, starting from reviewed commit `5805f89b8ae908b330e1e981536f52ae1725c2ee`. You have 15 minutes from starting. Implement a bounded accuracy experiment on the capacity proxy, retain honest evaluation, and push a reviewable result. Do not wait for organiser AAR labels; none will be supplied. Do not redesign the frontend or change Member 2's delivery/readiness tools.

Own `src/data_capacity/**`, `tests/data_capacity/**`, `src/dashboard/**`, `tests/dashboard/**`, `artifacts/capacity_estimate/**`, `handover/member-1-sprint-results.md`, `handover/status-member-1.json`, and a new `handover/member-1-accuracy-results.md`. Keep existing capacity/risk publications, input data, dependencies, shared source, risk code/tests and other members' files unchanged. Existing main/readiness integration continues independently against the reviewed checkpoint.

### Objective and ranking

1. Improve weather-conditioned capacity-proxy performance at both airports and 3/6/12-hour leads.
2. Preserve cutoff safety, runway directionality, sample/population labels and reproducibility.
3. Publish an honest before/after evaluation, including sparse severe-weather cases.
4. Only if the above is complete: unknown-traffic display and minor presentation corrections.

Do not lower the quantile toward the mean just to reduce RMSE: that changes the meaning of the capacity-frontier target. Keep q=0.90 and the training-derived high-demand screen fixed for this comparison. Report both proxy RMSE and quantile pinball loss; neither is independent facility AAR accuracy.

### Timebox

| Minutes | Work | Required output |
|---|---|---|
| 0-2 | Freeze baseline, split and adoption rule | Record source/run hashes, comparable cohorts and a small experiment specification before evaluating candidates |
| 2-7 | Implement at most two bounded candidates | Reproducible parameters and truthful input handling |
| 7-9 | Compare on the designated validation window; select or reject | One frozen choice; keep incumbent if no defensible improvement |
| 9-13 | Evaluate once on 2025, publish only if accepted, run checks | Same-cohort metrics, artifact hashes, regression results |
| 13-15 | Commit/push and hand back | Exact commit/run, measured changes, limitations and any remaining failures |

At minute 7 stop adding model ideas. At minute 9 freeze selection. Never change the acceptance rule after seeing the test comparison. If verification cannot finish, report incomplete and keep the reviewed publication as the release candidate.

### Candidate A: improve the weather signal

Inspect the currently published, cutoff-safe columns before changing ingestion. The existing regime classifier uses prevailing thunderstorm/visibility/ceiling/wind and can miss useful conditional forecast information. Test a single documented regime variant that uses appropriate existing TEMPO/PROB features, gust/crosswind information and frozen precipitation, while distinguishing conditional forecasts from prevailing conditions. Do not blindly interpret every low-probability condition as certain weather.

Keep missing wind components unknown. If a documented upper bound from known wind speed can establish the regime, record that assumption; otherwise use explicit partial/unavailable/backoff handling rather than silently setting unknown direction to calm. Retain fixed challenge headings ATL 080 and DFW 180.

This is a candidate, not a promised improvement. Refit its regime cells using training data only and compare with the incumbent on exactly the same eligible validation hours.

### Candidate B: simple quantile recalibration, only if time permits

The published frontier's empirical coverage varies materially between airports. Test one bounded additive residual-quantile correction per airport/lead, with sufficient support and explicit fallback. Keep it small and serializable in `model.json`; do not introduce a new dependency or a model tournament.

Fit base frontier cells on 2023. If fitting correction parameters on early 2024 (for example January-August), reserve September-December 2024 for selection and score every candidate, including the incumbent, on that same late-validation period. Do not fit and score the correction on the same rows. Model fitting/selection timestamps must disclose the later calibration data; do not continue claiming all fitted parameters came only from 2023.

Use 2025 only for the final frozen comparison. The team's 2025 results have already been inspected, so describe this as an updated held-out backtest, not a new pristine external validation set.

### Fix the decision rule before running candidates

A reasonable bounded engineering rule is:

- Primary: at least 1% lower macro-average q=0.90 pinball loss across the six airport/lead validation cells.
- Guardrails: no more than 2% worse macro-average proxy RMSE and no more than 5% worse pinball loss in any airport/lead cell. Report every cell and its n; these margins are engineering choices, not statistical significance thresholds.
- Same target definition, high-demand screen, available population and comparable timestamps for all models. Report excluded/missing coverage separately so dropping hard cases cannot manufacture a gain.
- Report severe-weather cohort results and support counts. Very small winter/convective cohorts cannot establish reliable skill or justify a fabricated uncertainty interval.
- If no candidate passes, retain the incumbent and publish the negative experiment result. Correctness fixes may still be committed with their effects disclosed and tests passing.

If the validation data cannot support a candidate or an acceptance comparison, do not silently relax these requirements to meet the deadline.

### Challenge-aligned evidence

Provide before/after tables for ATL/DFW x 3/6/12 hours with:

- high-demand-throughput RMSE (explicit proxy target), q0.90 pinball loss and empirical below-frontier share;
- cohort n and unique target-hour counts; do not count three leads as three independent observations;
- severe-weather/sparse-cell performance, backoff and unavailable counts;
- training-only airport quantile baseline and unchanged incumbent;
- exact training/calibration/selection windows and the adopted rule;
- one failure case and a concise explanation of what remains uncertain.

Independent operational AAR accuracy remains unverified because no facility labels are available. A prediction compared with labels generated by the same estimator is not independent accuracy evidence. Do not claim fuel savings or reduced delays without intervention evaluation.

### Verification and publication

Preserve the existing publication schema and optional-loader behaviour. If adopting a changed model, publish a new run/version and consistent assumptions/model/evaluation/forecast files with all hashes and row run IDs updated. Never hand-edit forecast numbers. Keep `aar_observed` null and uncertainty unavailable unless a defensible method is actually implemented and evaluated. The estimates must not enter genuine-AAR curves or the existing operational queue.

Run:

```text
python -m pytest tests/data_capacity/test_capacity_estimate.py tests/dashboard/test_capacity_estimate.py -q
python -m pytest tests -q
python -m src.flight_risk verify
```

Use distinct writable temporary directories where needed. Add meaningful checks for any new regime/calibration behaviour, unavailable/future inputs, model reproduction and held-out-label perturbation. Capture each command's exit code. Recheck the real-artifact app with both airports, all leads and reveal off/on if the publication or frontend binding changes. Supervisor reruns the final combined release gate after accepting a new commit.

### Handback

Return: baseline and result commits; adopted or rejected candidate; validation and 2025 before/after metrics; publication run/hashes if changed; tests and exit codes; frozen-input preservation; remaining limitations. Set `ready_for_review` only after verification. Do not overwrite the original review approval: any new code/publication needs its own review before merging.

The supervisor should retain `5805f89` as the known-good release candidate until this extension is reviewed. The separate readiness chat handles package generation, release evidence, controller review briefing and judging documentation; Member 1 should not duplicate those tasks.
