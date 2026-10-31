# Member 1 consumer-validation hardening results

Base: `3767538` (reviewed estimator checkpoint and accuracy handoff). Branch: `codex/member-1-validation-accuracy`.

## Scope and decision

Consumer-only correctness changes; retain the incumbent model and publication. No candidate fitting, tuning, validation scoring, adoption decision, or 2025 backtest was performed in this workstream. Per-cell before/after performance is therefore unchanged, not independently remeasured here. The model experiment chats own those comparisons. No data, producer code, dependency, publication, queue, or readiness files changed.

## Consumer rules

- Available/partial proxy rows require finite nonnegative estimates and finite nonnegative integer support. Boolean support is rejected. Unavailable rows may retain null estimates and zero support.
- Population, method, assumptions ID, model version, validation target and uncertainty metadata must be nonempty text. Population must identify reporting carriers; validation target must be the existing reporting-carrier high-demand-throughput proxy. Method/version/assumptions/population/target cannot differ within one forecast publication.
- Existing exact label, null observed AAR, contract status, UTC/hour-grid/lead relationship, cutoff and uncertainty-unavailable checks remain. Training end cannot follow selection end.
- Any supplied interval must have two finite nonnegative endpoints and enclose its finite estimate. Unavailable uncertainty still forbids any bounds.
- All three hashed estimate documents (model, assumptions, evaluation) must load and be available/partial before the forecast is usable. Declared model version, assumptions ID, population, label, validation target and method must agree with the forecast. Assumptions' structured method is compared using its name.
- Legacy envelope-only synthetic model/assumptions documents remain supported: absent optional metadata fields are not invented or required. When fields are declared, consistency is mandatory. This is a compatibility limitation, not full semantic proof of a producer's modeling assumptions.

Malformed publications are withheld with explicit loader reasons; optional publication absence remains supported. Genuine AAR preference, exact-key selection, outcome masking, and operational-queue isolation are unchanged. No view/layout changes were needed.

## Verification (actual commands and exit codes)

PowerShell working directory: assigned isolated checkout. For successful pytest runs, `TEMP` and `TMP` were set to `$PWD/tmp`, a newly created local directory.

- `python -m pytest tests/dashboard/test_estimate_validation_hardening.py tests/dashboard/test_capacity_estimate.py -q`: exit 1, one passing real-publication check and 46 fixture setup errors caused by sandbox Windows default temporary-directory permissions.
- Same tests with `--basetemp=tmp/validation-tests-1 --tb=short -x`: exit 1; parent tmp directory did not yet exist.
- Same tests with local TEMP/TMP and `--basetemp=tmp/validation-tests-2 --tb=short -x`: exit 1; 20 passed, one test helper used the wrong manifest section. Corrected helper to use fixture `outputs`.
- Same tests with local TEMP/TMP and `--basetemp=tmp/validation-tests-3 --tb=short`: exit 0; 47 passed.
- `python -m pytest tests/dashboard/test_estimate_validation_hardening.py -q --basetemp=tmp/validation-tests-4 --tb=short`: exit 0; 37 passed after mixed-ID, chronology and missing-document regressions.
- `python -m pytest tests/dashboard -q --basetemp=tmp/validation-dashboard-5 --tb=short`: exit 0; 191 passed, including existing app airport/lead/reveal checks. This run preceded the final document-unavailable status guard.
- `python -m pytest tests/dashboard/test_estimate_validation_hardening.py -q --basetemp=tmp/validation-final-6 --tb=short`: exit 0; 40 passed including the final document-unavailable guard. Includes real committed publication loading.
- Final combined dashboard rerun: `python -m pytest tests/dashboard -q --basetemp=tmp/validation-dashboard-final-7 --tb=short`: exit 0; **194 passed** including all final consumer guards.
- `git diff --check`: exit 0.

Full repository suite and risk verification are reserved for the coordinator's combined gate. No redundant model evaluation or publication regeneration was performed.

## Remaining limitations

This is input-contract hardening, not model accuracy evidence. Carrier-scoped proxy limitations, missing wind/rare weather and absence of independent facility AAR remain. Finite well-formed bounds are checked structurally; the consumer cannot establish the statistical validity of an interval method. No new interval or operational savings claims are introduced.
