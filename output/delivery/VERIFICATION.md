# Member 2 delivery verification — 31 October 2026

Status: **baseline_verified_with_known_frontend_failure**. The delivery contribution is ready for review; the combined application is not accepted for a final demo.

Implementation baseline: `737b46852c2d4b98e7c01e68ed7e3888f6542c5c`. Handoff-only base: `c01500a3bb247e7ab7882ae3d45e4b266d1b028e`. Branch: `codex/member-2-delivery-30min`. No Member 1 sprint changes or new publication were used.

## Execution results

These commands ran in a fresh extraction of the earlier `member2-tested.zip`, outside the source checkout, using the model-compatible installed environment recorded in `verification.json`.

| Check | Exit | Result |
|---|---:|---|
| `python -m src.flight_risk verify` | 0 | 10,604 predictions / 3,537 flights; KATL/KDFW; leads 3/6/12; model partial, decisions unavailable |
| `python -m pytest tests/flight_risk tests/delivery -q --basetemp=<fresh writable directory>` | 0 | 106 passed, one physical-core detection warning |
| `python -m pytest tests -q --tb=short --basetemp=<fresh writable directory>` | 1 | 330 passed, one inherited failure, one warning |
| `python -m tools.delivery.smoke_app` | 1 | Real-artifact initial app render reproduces that same inherited chart error |

The 10 new delivery tests also passed independently in the source checkout. They cover optional `capacity_estimate` discovery using synthetic bytes, missing/corrupted producer payloads, path confinement, cache/output exclusions, unchanged requirements, stale runtime evidence and archive tampering. The synthetic fixture was never written into production artifacts.

Inherited failure: `tests/dashboard/test_additions.py::test_actual_traffic_counts_need_reveal`. At `src/dashboard/plots.py:168`, Plotly's annotated `add_vline` attempts integer addition on a pandas Timestamp. Member 1 owns the repair. The real-artifact app smoke stops at this initial exception, so its airport × lead × reveal matrix was **not** reached. The baseline handoff reported 320 passes and this same failure; this branch adds 10 passing delivery tests.

Windows temporary-directory cleanup errors and the physical-core warning were recorded separately. They do not explain away the chart failure. A writable `--basetemp` resolved the initial delivery-test setup error. No tests were weakened, skipped or changed outside `tests/delivery/`.

## Payload and preservation

All producer manifests and their 17 declared payload references were validated: capacity/data run `m1-20261031T065014Z-eacdd5`, risk run `0949771a54bb4e49b4e215528eb5d46b`, and unavailable decision run `a7b89e44c69449d1a7ecfbf0cb8ff3b5`.

The archive contains `.streamlit/config.toml`, Leaflet JS/CSS, processed flights/provenance/storm events, published capacity/traffic/weather outputs and frozen risk input snapshots. Missing or incorrect producer bytes abort generation without replacing a good archive. Historical absolute provenance paths are retained as metadata and never followed.

`frozen-baseline.json` captures the initial hashes of 97 tracked frontend/model/data/existing-test/dependency/configuration files. All 97 remain unchanged in the source tree. All 96 included frozen files match after extraction. The intentionally omitted file is `data/public/.gitignore`, a raw-cache rule with no runtime role.

## Tested archive versus final archive

The earlier runtime-tested archive has SHA256 `4960726d4423c995a3e640d8f7604f9fbe1875ebfbed4d82c2cf4abb61989e9f`. It is an intermediate archive, **not the final handoff ZIP**.

Runtime fingerprint: `11cd243b0efb97228cdc58733266123f26acfbd86454ee0013b85e3702796bb6`. It binds code, tests, dependencies, configuration and runtime data. Documentation/evidence updates do not change that fingerprint; the final archive hashes each included document independently.

After committing the documentation, build the final baseline ZIP with:

```text
python output/delivery/build-package.py
python output/delivery/build-package.py --verify output/delivery/challenge-5-implementation.zip
```

The final archive's SHA256 and exact source commit are in `challenge-5-implementation.sha256` and `.receipt.json` beside the ZIP. Its full inventory is `.manifest.json` and the embedded `BUNDLE_MANIFEST.json`. The final hash is kept outside the archive to avoid a self-referential hash. The handback message reports the final hash and final-extraction checks separately from the earlier execution above.

## Supervisor release gate

Merge reviewed member commits in either order. Run the complete suite, risk verifier and app smoke from the combined tree; then rebuild and recheck a fresh extraction. The old execution evidence will become stale after Member 1's code/data changes and must be replaced with actual combined-run results. Verify the new optional publication/run ID is included. Do not promote this baseline exception to final demo acceptance.

No clean environment installation, model retraining, fresh public-data acquisition, browser radar/basemap tile check, queue activation or benefit simulation was performed. Model-estimated capacity is planned separately; missing organiser AAR labels are not a reason to wait for organiser data, and estimates must not be described as recorded facility AAR.
