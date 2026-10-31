# Arrival scenario inputs

Implemented `src/flight_risk/arrival_inputs.py` and 13 focused regression tests. This supplies the previously missing schedule-demand and initial-backlog inputs to a **separate retrospective scenario**, without weakening the verified operational queue contract or publishing fabricated observations.

API: `build_arrival_inputs(traffic, *, airport, asof_utc, window_hours, warmup_hours=24)` returns `demand`, `initial_backlog`, `status`, `limitations`, `missing_inputs`, `scenario_only` and `known_at_cutoff_verified`. The caller must use hash-verified published traffic. The function does not fetch, modify or publish artifacts.

Demand is consecutive hourly scheduled gate-arrival counts for reporting carriers, including cancellations. Initial backlog is an aggregate imbalance proxy: start at an explicitly assumed zero 24 hours before cutoff, then apply `max(0, prior + scheduled - actual)` through completed hours. Service surplus is not banked. The resulting backlog is separate from newly due future demand. Earlier backlog and identities of waiting flights cannot be identified from these aggregates.

Every prior warmup and future planning hour must be present. Missing hours are never converted to zero; missing prior actuals, duplicates, invalid counts, mixed source runs/populations or non-reporting-carrier coverage produce `unavailable` with reasons. Current/future `actual_count` and cancellation fields are not consulted. Timestamps require explicit timezones and cutoff requires an hour boundary.

Usable output is `status=partial`, with row `status=scenario_estimate`, `coverage=reporting_carriers`, `scenario_only=True` and `known_at_cutoff_verified=False`. Availability and observed-backlog timestamps remain null because the source supplies no historical publication times. Source availability at cutoff and immediate publication of completed-hour observations are disclosed replay assumptions; no verified time is manufactured. These rows intentionally fail the operational queue's complete-demand/facility-AAR/verified-backlog requirements.

Verification: `python -m pytest tests/flight_risk/test_arrival_inputs.py -q --basetemp=tmp/arrival-input-tests --tb=short` with TEMP/TMP in the checkout: **13 passed, exit 0**. Coverage includes temporal boundaries, future-outcome perturbation invariance, zero versus missing hours, conservation assumptions, invalid metadata/counts, duplicates and nonmutation. `git diff --check`: exit 0.

Real published traffic, cutoff `2025-07-12T20:00:00Z`, six-hour scenario, 24-hour warmup:

| Airport | Scheduled demand by hour | Estimated starting imbalance |
|---|---|---:|
| KATL | 46, 39, 54, 59, 53, 36 | 84 |
| KDFW | 68, 26, 67, 46, 81, 32 | 57 |

Both return partial with no missing coverage. These values are scenario inputs, **not measured airport queues**. Gate/runway timing differences, cancellations, diversions, early arrivals and the zero warmup anchor can substantially bias the imbalance. No accuracy or operational-benefit claim follows from producing a complete scenario.
