# Two independent external handoffs: 30-minute sprint

Prepared 31 October 2026 (Singapore). Repository: https://github.com/Alpharion/vibeclauders

**Start both agents from `737b46852c2d4b98e7c01e68ed7e3888f6542c5c`.** Main was fast-forward pulled and inspected. These are handoff instructions, not claims that either external agent has started or completed work.

Give Member 1 `MEMBER-1.md` and Member 2 `MEMBER-2.md`; give both `INTERFACE.md` and `ACCEPTANCE.md`. Copy the files into each checkout before launch, or attach this whole directory. Paths in these instructions are relative to the recipient's repository root; do not depend on the author's Windows path.

GitHub handoff branch: `codex/parallel-handoffs-30min`. Each member can fetch this branch and create its own working branch from it, obtaining the pinned implementation plus these documents in one checkout. The handoff branch adds documentation only to the baseline above. Do not substitute a newer main during the sprint without a supervisor reviewing the changed baseline and both assignments together.

## Outcome and priorities

| Member | P0 deliverable by minute 24 | Independent starting inputs |
|---|---|---|
| 1 | Fix the new traffic-chart crash; publish a documented model-estimated capacity proxy and show it in the existing capacity/Evaluation panels | Main's existing traffic/weather artifacts and risk publication |
| 2 | Repair the complete-package builder, verify an extracted baseline package, and publish accurate risk/delivery evidence | Main's existing code, frozen risk inputs and both published producers |

The organisers do not supply AAR labels. Member 1 must build an estimate rather than wait for an extract. In 30 minutes, the attainable output is an explicitly scoped empirical capacity proxy, not an independently validated operational facility AAR. Do not simply rename the existing mean-arrivals forecast. Full capacity identification, external reference validation and calibrated uncertainty are later work.

Neither member waits for, imports, cherry-picks or requires the other's branch. Member 1 owns the estimator **and its frontend binding**. Member 2's builder works on the current baseline and automatically includes optional new publications when later present. A final combined release is a supervisor action, not unfinished integration code assigned to one agent.

## Preserve current main's frontend

Keep historical/live modes; Overview, Weather, Traffic, Compare and Evaluation tabs; airport/cutoff/hour/lead/planning-window/reveal controls; Leaflet radar/Connections/Flagged flows layers; hub markers; weather frequency heatmap/category bars; reporting-carrier charts and movement cards. No replacement app, new page, new navigation or major interaction change. Small layout adjustments, bug fixes, data binding and truthful model labels in existing panels are allowed.

## Exclusive write ownership

| Owner | Allowed writes |
|---|---|
| Member 1 | `src/data_capacity/**`, `tests/data_capacity/**`, `src/dashboard/**`, `tests/dashboard/**`, **new** `artifacts/capacity_estimate/**`, `handover/status-member-1.json`, `handover/member-1-sprint-results.md` |
| Member 2 | `output/delivery/**`, **new** `tests/delivery/**`, **new** `tools/delivery/**`, `README.md`, `BUNDLE_README.md`, `BUNDLE_MANIFEST.json`, `handover/member-2-results.md`, `handover/status-member-2.json` |
| Frozen for both | `src/shared.py`, root `app.py`, `.streamlit/**`, `requirements*.txt`, `data/reference/**`, `data/processed/**`, `data/public/**`, `data/weather/**`, `artifacts/capacity/**`, `artifacts/risk/**`, `src/flight_risk/**`, `tests/flight_risk/**`, existing shared contract/plans and this sprint contract |

Member 1 owns the whole dashboard directory to avoid shared-file conflicts, but that is not permission for a redesign. Frozen paths are readable. Member 2 must not modify frontend tests to hide the known failure. Both preserve published models and input bytes. Neither changes dependencies or installs a new stack for this sprint.

## Shared 30-minute timeline

| Elapsed | Member 1 | Member 2 | Supervisor |
|---|---|---|---|
| 0-3 min | Check branch, confirm chart regression | Check branch, capture hashes/versions | Launch both; confirm no shared checkout |
| 3-13 min | Fix chart; implement one small capacity-frontier estimator | Repair payload discovery and package metadata | At minute 10 request completed files, command results, next action |
| 13-19 min | Bind estimate to existing panels; add focused checks | Build/extract; verify hashes, risk, static assets and baseline behaviour | Reject scope expansion |
| 19-24 min | Freeze features; run model/dashboard checks | Finish delivery checks and current baseline docs | Collect pass/fail evidence and remaining limits |
| 24-26 min | Commit only owned files; send handoff | Commit only owned files; send handoff | Review ownership and independence |
| 26-30 min | Defects only in own paths if needed | Defects only in own paths if needed | Merge either order, run combined checks, rebuild release, smoke app |

The deadline is an allocation, not a guarantee. At minute 19 stop adding features. Do not conceal failures or mark incomplete work complete to meet the clock. If a critical deliverable is unfinished, report its exact state and keep the last working publication.

## New baseline finding

On `737b468`: **320 passed, 1 failed** in the full suite. Failure: `tests/dashboard/test_additions.py::test_actual_traffic_counts_need_reveal`, in `src/dashboard/plots.py:168`, `reporting_chart()` calling `add_vline` with a pandas Timestamp and annotation. Plotly attempts unsupported Timestamp-plus-integer arithmetic. Risk CLI verification passes. See `ACCEPTANCE.md` for the precise distinction between Member 2's baseline acceptance and final release acceptance.

## Explicitly deferred

- Full airport-wide operational AAR validation, authenticated AAR acquisition, capacity-profile research campaign.
- Risk retraining, new predictors, calibration redesign, all-month downloads or producer republishing.
- Queue-free advice, demand/backlog reconstruction, flight rescheduling and claimed savings.
- Throughput forecast UI expansion beyond the existing panels needed for the capacity estimate.
- New CI, dependency migrations, comprehensive documentation rewrites, broad UI polish.

The earlier documentation chat's edits were based on `a80b265` and remain separate. Do not merge them blindly during this sprint; Member 2's permitted evidence updates cover the sprint baseline only.
