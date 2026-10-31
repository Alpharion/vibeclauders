# Cutoff-visible delay and congestion features

Implemented `src/flight_risk/cutoff_features.py` without changing the production model feature allowlist or publications. The model experiment can import `add_cutoff_features(snapshots, full_canonical, traffic, capacity_estimate=None)` and `FEATURE_COLUMNS`.

## Features and availability contract

| Feature | Definition | Information boundary |
|---|---|---|
| `recent_departure_count_2h` / `3h` | Number of uniquely identified, noncancelled, labelled gate departures in `[cutoff-window, cutoff)` | Actual gate departure must precede cutoff strictly. This is not a count of all scheduled flights. |
| `recent_severe_delay_share_2h` / `3h` | Share of those observed departures with gate departure delay greater than 45 minutes | No label from a still-pending or future departure enters the count. Empty observed cohorts have unknown share, not zero risk. |
| `scheduled_arrivals_target_hour` | Reporting-carrier scheduled gate arrivals in the target UTC hour | Retrospectively reconstructed schedules are assumed known at cutoff; scheduled cancellations remain included. |
| `scheduled_departures_target_hour` | Reporting-carrier scheduled gate departures in the target UTC hour | Same schedule assumption; actual target-hour throughput is never used. |

The canonical input's population matters. Full BTS event caches were not available to this sprint on this machine. On the supplied canonical challenge sample, recent-event counts and rates are **sample-only observations**, not airport-wide delay state. Hourly traffic coverage proves the monthly source grid exists; it does not make the sample's observed departures complete. The function records input coverage and assumptions in DataFrame attributes; callers must retain those disclosures in their experiment report.

BTS actual gate departure times are reconstructed historical timestamps. The replay assumes a completed event and its delay become observable immediately, but receipt latency is not verified. Gate departure is used because the label is gate departure delay; it is not conflated with wheels-off time. This limitation applies even when the input population is larger.

The proposed demand/capacity ratio is deliberately excluded. The published capacity estimate declares selection ending in January 2025; using it across 2023 training or 2024 selection would violate the model-availability boundary. No future model values are backfilled or relabelled as available. A future experiment could derive a separate strictly training-only proxy with a predeclared design.

## Implementation and performance

Per-airport cumulative severe counts and sorted timestamp searches evaluate each unique cutoff, then map back to flight/horizon rows. No per-flight scan of the historical table is performed. Duplicate flight IDs are excluded conservatively; duplicate traffic hour/direction keys are refused. Missing months or invalid scheduled counts remain unknown. Covered windows with no observed sample events have count zero and share NaN. Inputs are not mutated.

On the existing canonical sample, the builder processed 47,841 eligible flight/horizon rows in approximately 0.15 seconds in the development environment. There were 19,480 rows with at least one observed sampled departure in the prior two hours, and 24,269 for three hours. This sparsity is an important limitation, not evidence that the airport had no departures. No target flight in this sample had already departed before its forecast cutoff.

Demo snapshot ATL, cutoff 12 July 2025 20:00 UTC, +3h: zero observed sampled departures in each recent window, so both delay shares are unknown. Scheduled target-hour arrivals/departures are 59/50. These features do not imply zero airport congestion or zero delay risk.

## Verification

`python -m pytest tests/flight_risk/test_cutoff_features.py -q --basetemp=tmp/cutoff-feature-tests --tb=short`: **10 passed**. Tests cover strict cutoff and lower-window boundaries, future outcome/cancellation perturbation, missing versus zero coverage, unknown target schedules, duplicate events/traffic, nonconsecutive indices, input immutability, timezone rejection, sample-population disclosure and omission of an unavailable capacity ratio.

No model gain is claimed here. Candidate selection and comparable-cohort evaluation belong to the model experiment report. No full-BTS model was trained by this feature-builder task, and no current production artifact was replaced.
