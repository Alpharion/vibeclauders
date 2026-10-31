# Current delivery verification

UTC: 2026-10-31T08:01:07.754568+00:00
Status: **verified**; scope: **combined_runtime**; manual acceptance: **pending**.
Runtime fingerprint: `52ecbb7c5a0aacc3ac7889be7a391987cab27f4fabf1a7cb6e038e3996eaec49`.

Checks ran in a fresh package extraction.

| Check | Exit | Result |
|---|---:|---|
| risk_verify | 0 | "See verification.json" |
| full_suite | 0 | {"tests": 501, "failures": 0, "errors": 0, "skipped": 0, "passed": 501} |
| app_smoke | 0 | "passed" |

## Release blockers

- No automated blocker; manual acceptance remains pending.

## Limits

- Runtime verification is not judge/supervisor acceptance or a claim of model accuracy.
- Browser radar/basemap availability and the three-minute presentation require manual review.
- No clean environment install, public data refresh, retraining or operational benefit simulation performed.
- Baseline mode does not require the optional capacity estimate; it cannot certify the combined release.

This report supersedes earlier runtime evidence. The previous Member 2 sprint results remain historical.
Failed checks never replace the last release ZIP. See logs for the tested candidate archive.
After successful checks and documentation freeze, rebuild; its receipt records the final commit and ZIP hash.
