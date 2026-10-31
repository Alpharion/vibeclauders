# Copy-ready prompt: Member 1

You are Member 1, externally supervised. You have a **30-minute shared sprint**, with implementation/checks finished by minute 24 and your commit ready by minute 26. Read the attached sprint README, INTERFACE and ACCEPTANCE first. Implement your assignment; do not start another agent or expand scope.

Start from `737b46852c2d4b98e7c01e68ed7e3888f6542c5c` in your own clean checkout. Suggested branch: `codex/member-1-capacity-30min`. Inspect local AGENTS.md instructions. Preserve unrelated work; do not reset or switch a teammate's dirty checkout. Main's frontend is the fixed product: no new tabs, navigation or replacement UI. Corrective data bindings/labels and small layout changes are allowed.

## P0 deliverable

Fix the current traffic-chart crash, then create a reproducible, honest **weather-conditioned empirical arrival-capacity estimate** using already published traffic and weather. Show it in the existing capacity/Evaluation panels. No organiser AAR labels will arrive; do not spend this sprint requesting them. No network ingestion or retraining the existing throughput/risk models.

You own `src/data_capacity/**`, `tests/data_capacity/**`, all `src/dashboard/**` and `tests/dashboard/**`, new `artifacts/capacity_estimate/**`, `handover/status-member-1.json`, and new `handover/member-1-sprint-results.md`. Frozen source/data/dependencies listed in the README remain untouched. You do not need Member 2's changes.

## Ordered work

1. **Minutes 0-4: fix the known crash.** Reproduce `tests/dashboard/test_additions.py::test_actual_traffic_counts_need_reveal`. `reporting_chart` uses an annotated Plotly vertical line with a Timestamp at `plots.py:168`. Keep the same visible cutoff marker and label, but use a timestamp-safe shape plus separately positioned annotation, or an equivalent supported implementation. Preserve reveal masking; do not delete the assertion, hide the chart or weaken the test.

2. **Minutes 4-13: implement one small estimator.** Add a command such as `python -m src.data_capacity estimate-capacity --from-published` that validates current manifest/input hashes and reads only committed `traffic_hourly.parquet` and `weather_features.parquet`. Write only the separate publication in INTERFACE.md. Do not call the full data pipeline.

   Recommended bounded method: one deterministic training-only high-demand, weather-regime frontier. Deduplicate target-hour outcomes before estimating demand thresholds; for each airport derive a high-scheduled-demand screen from 2023 (for example its 75th percentile). Use observed arrival counts in screened hours to fit a fixed upper quantile (for example 0.90) by airport and a small, documented weather-regime classification built from existing cutoff-safe ceiling/visibility, crosswind/tailwind and precipitation/thunderstorm features. Estimate lead-specific cells or explicitly document pooling; do not count three leads as three independent observed hours. Use an explicit minimum support and deterministic backoff, recording support and backoff in outputs. Fix hyperparameters in advance; no model tournament. A small quantile model is acceptable if it fits the timebox, but a stable lookup model is sufficient.

   This method is a **capacity proxy for reporting carriers under the assumption that high-demand throughput is informative about attainable rates**. Low demand, restricted coverage and flow programmes prevent automatic identification of physical airport capacity. State that limitation visibly. Do not divide by the challenge sample fraction to invent whole-airport rates; do not relabel the existing mean-throughput predictions. Use fixed challenge headings already encoded in the wind features. An estimated number is the objective; no claim of independently verified operational AAR is warranted.

   Keep 2023 training / 2024 validation / Jan-Jul 2025 held-out replay. Thresholds, cells, backoffs and any model choice must not use test outcomes. Emit only cutoffs after the latest training/selection information. Test outcomes can evaluate the frozen proxy against observed high-demand throughput; name that metric precisely. Include the train-only airport high-demand quantile baseline. If no defensible uncertainty method fits the sprint, publish null bounds with `uncertainty_kind='unavailable'`, not a fabricated interval.

3. **Minutes 13-19: bind and test.** Add the optional loader group, strict hashes/run/snapshot/cutoff checks and exact-key fallback into existing capacity/Evaluation panels. Preserve real facility AAR support. Keep `aar_observed` null and queue refusal intact. Publish model parameters and assumptions so the estimate can be reproduced. The baseline app must still launch when the optional group is absent. Keep every new-main map/heatmap/traffic feature intact.

4. **Minutes 19-24: freeze and verify.** Run focused estimator tests, all dashboard tests and risk verification. Test both airports/all leads with reveal off/on. Use the existing real risk publication unchanged. Checks must show changed held-out labels cannot change predictions, missing/future timestamps are rejected, estimates do not enter genuine-AAR curves or queue logic, and the baseline without estimates still works.

5. **Minutes 24-26: handoff.** Commit only owned paths. Report source commit, result commit, generated run, output rows/cohorts, commands with real exit codes, screenshots if captured, and limitations. Set ready_for_review only when P0 is complete; do not invent supervisor sign-off.

## Stop rules and deferred work

At minute 13 prefer a working simple documented estimator over a more complex unfitted model. At minute 19 stop features. Do not fabricate numbers or silently relax leakage checks to finish. If insufficient data support prevents an estimate at a key, publish unavailable there and report incomplete coverage. If the estimation deliverable is incomplete at the deadline, preserve the chart fix and report the shortfall clearly.

Only after P0 passes may you fix the all-missing traffic-total display (`sum()` must not show zero for wholly unknown coverage) or adjust cramped layout. Defer radar fetch redesign, broad consumer hardening, calendar/frequency methodology changes, throughput UI expansion, calibrated intervals, external capacity studies, queue/advice redesign and new airports.

Your output must work before Member 2 merges. Member 2 does not own your loader, tests, estimator or artifacts and must not be needed to finish them.
