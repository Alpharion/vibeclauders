# Copy-ready prompt: Member 2

You are Member 2, externally supervised. You have a **30-minute shared sprint**, with implementation/checks finished by minute 24 and your commit ready by minute 26. Read the attached sprint README, INTERFACE and ACCEPTANCE first. Implement your assignment; do not start another agent or expand scope.

Start from `737b46852c2d4b98e7c01e68ed7e3888f6542c5c` in your own clean checkout. Suggested branch: `codex/member-2-delivery-30min`. Inspect local AGENTS.md instructions. Preserve unrelated work; do not reset or switch a teammate's dirty checkout.

## P0 deliverable

Deliver a complete, portable package builder and accurate risk/delivery verification using **existing main artifacts**. You do not wait for Member 1's estimator or frontend fix. The builder must automatically include the optional capacity-estimate publication if it exists in a future combined tree, tested with a temporary synthetic fixture now.

Own `output/delivery/**`, new `tests/delivery/**`, new `tools/delivery/**`, `README.md`, `BUNDLE_README.md`, `BUNDLE_MANIFEST.json`, `handover/member-2-results.md`, `handover/status-member-2.json`. No dashboard/model/dependency/shared-contract/data/artifact edits. No risk retraining, new calibration, new recommendation semantics, or new CI this sprint.

## Ordered work

1. **Minutes 0-3: pin evidence.** Record HEAD, dirty status, model-compatible committed requirements and current publication hashes/runs. Risk verification should pass for 10,604 predictions / 3,537 flights. Current main has one known frontend test failure; do not call the baseline fully green or wait for its repair.

2. **Minutes 3-13: repair the builder.** `output/delivery/build-package.py` currently packages risk but omits capacity/processed data, and emits stale 85-test/schedule-only text. Include current code/tests, dashboard static Leaflet assets, root launcher/config/dependency files, README/runbooks, reference metadata, canonical processed inputs, all present producer manifest payloads and risk frozen snapshots. Keep raw download caches, VCS, temporary work, virtual environments and the output archive itself excluded. Discover optional artifact publications, including `artifacts/capacity_estimate`, so a combined release requires no further code change. Validate paths/hashes and payload completeness; do not follow old absolute source paths outside the checkout.

   Remove the personal Downloads/PDF dependency. An optional `--reference-pdf` is acceptable, but absence must not block a working package. Preserve the committed `requirements-observed.txt`; do not overwrite it with your machine's library versions. Record the environment used for verification separately. Metadata/README must be generated from the actual tree, present artifacts, run IDs and performed checks, not hardcoded old completion claims. Record a commit plus dirty state/content hashes when packaging uncommitted changes.

3. **Minutes 13-20: prove portability.** Build the package, extract to a new directory, verify archive manifest hashes and required payload paths, run `python -m src.flight_risk verify` from the extracted root, and run the risk suite plus packaging checks. Confirm `.streamlit/config.toml`, `src/dashboard/static/leaflet.js` and `.css`, capacity/processed inputs and frozen risk snapshots are present. Exercise optional publication discovery with a small synthetic fixture in a temporary copy, not production data. Attempt the full suite and real-artifact app smoke; record the known inherited chart failure honestly. No new failures caused by packaging are acceptable.

4. **Minutes 20-24: document actual progress.** Update your owned README/evidence/status files with baseline SHA, produced archive hash, verified paths/commands, current risk metrics/limitations and the model-estimated AAR direction. Describe Member 1's output as planned/optional unless present and independently checked. Do not claim completed integration, calibration or acceptance from another member. Baseline package status is `baseline_verified_with_known_frontend_failure` while that defect remains. It is not the final demo release.

   Before handoff, freeze the packaged documentation, rebuild the final baseline archive and recheck manifest/archive hashes and required payloads. Report this final archive's hash, not the earlier test archive's hash. Clearly distinguish checks performed on the earlier code-identical extraction from checks performed on the final documentation-complete archive.

5. **Minutes 24-26: handoff.** Commit only owned paths. Report archive location/hash, commit, exact verification results, inherited failure and reproduction, preservation of model/data hashes, and one-command rebuild instructions. The supervisor uses your completed builder after either-order merges; you do not wait for Member 1 or change its files.

## Independent acceptance

- Builder and risk verification pass on the pinned baseline without Member 1's branch or new publication.
- Every included producer manifest payload is present and byte-correct after extraction.
- Optional new publications are included generically when present; absent ones do not break baseline delivery.
- All frozen inputs/models and frontend files remain unchanged in your branch and in the package.
- The known baseline chart failure is reproduced/recorded, not fixed by weakening tests, relabelling results or changing shared dependencies.
- Your result is complete as a delivery-tool/evidence contribution even if Member 1 has not finished. Final combined demo acceptance belongs to the supervisor.

Defer training, queue/advice changes, whole-repo documentation cleanup, environment upgrades and fresh full-source downloads. The existing document-refresh branch is older and not automatically part of this sprint; avoid importing its unreviewed edits.
