# Supervisor checks and verified starting evidence

## Baseline tested during handoff preparation

Commit `737b46852c2d4b98e7c01e68ed7e3888f6542c5c`, 31 October 2026.

- `git pull --ff-only origin main`: fast-forward from `27bb9d2` to `737b468`.
- New frontend: radar/connection/flagged-flow map, condition heatmap/category frequencies, reporting-carrier charts and movement cards. Previous review's statement that no radar exists is obsolete; its old line reference claiming no traffic forecast is published was removed by this merge.
- `python -m pytest tests -q --basetemp=../handoff-baseline-737b468`: **320 passed, 1 failed, 1 warning**, 50.78 seconds. The failed pytest run was followed by a successful verifier in the same shell, so the shell's final success does not mean pytest passed.
- Failure: `tests/dashboard/test_additions.py::test_actual_traffic_counts_need_reveal`. `src/dashboard/plots.py:168`, `reporting_chart`, `fig.add_vline(x=asof, ..., annotation_text='Cutoff', ...)` raises `TypeError: Addition/subtraction of integers and integer-arrays with Timestamp is no longer supported` inside Plotly shape annotation. Member 1 owns the fix.
- `python -m src.flight_risk verify`: passed; model partial, decisions unavailable; 10,604 prediction rows, 3,537 unique flights, KATL/KDFW and 3/6/12 hours; risk run `0949771a54bb4e49b4e215528eb5d46b`.
- Windows physical-core detection warning and sandbox temporary-directory cleanup PermissionError occurred. The Plotly failure is a separate real application defect and must not be dismissed as the cleanup warning.

## Starting commands (each agent's own clean checkout)

```text
git fetch origin
git status --short
git switch -c codex/member-1-capacity-30min origin/codex/parallel-handoffs-30min
```

Member 2 substitutes branch `codex/member-2-delivery-30min`. The shared handoff branch contains only these documents on top of implementation baseline `737b468`. If the directory is dirty, use a separate checkout instead of resetting it. Do not pull a teammate's branch during the sprint. Both agents receive the handoff files directly from the shared branch; there is no dependency on the other member's working branch.

## Checks to record separately with exit status

Existing commands:

```text
python -m pytest tests/dashboard/test_additions.py::test_actual_traffic_counts_need_reveal -q
python -m pytest tests/data_capacity tests/dashboard -q
python -m pytest tests/flight_risk -q
python -m pytest tests -q
python -m src.flight_risk verify
python -m streamlit run app.py
```

Planned Member 1 command (does not exist at handoff time):

```text
python -m src.data_capacity estimate-capacity --from-published
```

Existing builder command, to be repaired by Member 2:

```text
python output/delivery/build-package.py
```

Use distinct temporary directories for test/extraction runs. Do not concatenate checks in a way that hides an earlier nonzero exit behind a later success.

## Member 1 acceptance

- The inherited chart test passes without weakening outcome masking or removing the cutoff marker.
- Capacity estimates are produced from published inputs for both airports and all leads, with dates/support/coverage disclosed; missing support is unavailable.
- Estimates have a separate publication and truthful scope/method/assumptions; genuine AAR and throughput retain their meaning.
- Prediction parameters never use held-out outcomes; perturbing held-out actuals cannot change estimates. Any metrics state the proxy target explicitly.
- Non-null cutoff/training/selection timestamps and manifest hashes/run IDs are enforced for the new group.
- Existing capacity/Evaluation panels display estimates correctly; genuine AAR curves/queue do not absorb proxy values.
- AppTest covers both airports x three leads x reveal on/off, and absence/rejection of the optional estimate publication. No new tabs, controls or frontend replacement.
- Frozen risk/data/capacity artifacts unchanged. Member 2's branch was not needed.

## Member 2 acceptance

- Packaging tests, archive integrity/payload completeness and extracted risk verification pass using base-main publications.
- No frozen frontend/model/input/dependency bytes change.
- A synthetic optional publication is included correctly without requiring real Member 1 output.
- Full-suite/app result reports the one inherited frontend failure accurately and introduces no new failure. This is acceptable for the independently completed packaging work, **not** for the final demo release.
- Metadata accurately identifies baseline/current tree, runs, hashes and real test scope; model-compatible requirements retained.
- Member 1's branch was not needed.

## Final supervisor release gate (minutes 26-30)

1. Review each diff against the pinned base for ownership violations. Merge both reviewed commits in either order; investigate any conflict because ownership should prevent it. Do not merge generated files by hand.
2. Run the targeted inherited regression, complete suite and risk verifier. Final application release requires no unaccounted failures; do not carry Member 2's baseline exception into the final release.
3. Rebuild with the completed package builder from the combined tree. Verify the package includes new `capacity_estimate` files/run/hashes and all frontend static assets; extract to a fresh folder and run verifier/app smoke.
4. Review both airports/all three leads/outcome masking with the new estimate visible. Confirm scope/proxy labels and missing-uncertainty note; queue remains honestly unavailable.
5. Browser-side radar/basemap availability is not proven by AppTest. If online tiles fail, explain the network limitation; retain the historical model/weather functionality and do not claim received radar evidence.
6. Record combined commit, package SHA256, actual test summary and any unmet P0. No automatic pushing, merging or messaging is performed merely by distributing these handoffs; supervisors carry out their team's normal release actions.

Final reply format for both agents: member, baseline/result commit, owned files changed, artifacts/run IDs, command/exit/result, independent-input evidence, limitations, completion state. Use STATUS-TEMPLATE.json as a blank form; fill it only after work actually begins.
