# Current delivery verification

UTC: 2026-10-31T07:33:53.422653+00:00
Status: **failed**; scope: **combined_runtime**; manual acceptance: **pending**.
Runtime fingerprint: `1e1f9ec7ef3ca70a8d0ffd8d407ada5248ecec10cb6144460c7729aa26031976`.

Checks ran in a fresh package extraction.

| Check | Exit | Result |
|---|---:|---|
| risk_verify | 0 | "See verification.json" |
| full_suite | 1 | {"tests": 347, "failures": 1, "errors": 0, "skipped": 0, "passed": 346} |
| app_smoke | 1 | "failed" |

## Release blockers

- full_suite exited 1
- app_smoke exited 1
- Usable capacity_estimate publication with all four payloads is required

## Limits

- Runtime verification is not judge/supervisor acceptance or a claim of model accuracy.
- Browser radar/basemap availability and the three-minute presentation require manual review.
- No clean environment install, public data refresh, retraining or operational benefit simulation performed.
- Baseline mode does not require the optional capacity estimate; it cannot certify the combined release.

This report supersedes earlier runtime evidence. The previous Member 2 sprint results remain historical.
Failed checks never replace the last release ZIP. See logs for the tested candidate archive.
After successful checks and documentation freeze, rebuild; its receipt records the final commit and ZIP hash.
