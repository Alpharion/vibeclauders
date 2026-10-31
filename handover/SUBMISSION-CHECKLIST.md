# Combined release and submission checklist

Current state: **not accepted for submission**. Member 1's completed work and the parallel accuracy/input follow-ups are integrated on `codex/member-1-accuracy-integration`; automated verification is complete, while human acceptance remains pending. Member 1 published the chart fix and capacity proxy at `5805f89b8ae908b330e1e981536f52ae1725c2ee`, run `m1-capest-20261031T072310Z-a27968`; this is a ready-for-review publication, not acceptance. The baseline chart failure must pass the combined gate.

## Automated gate

From the reviewed combined checkout:

```text
python -m tools.delivery.verify_release
```

The command validates publication payload hashes, builds a candidate archive, extracts it into a new directory, runs the risk verifier, full test suite and real-artifact app smoke, and records individual exit codes, environment and runtime fingerprint. It requires the optional capacity-estimate publication and its four declared payloads. A source/extraction mutation during checks also fails the gate. No producer, model or frontend file is changed.

Outputs: `output/delivery/verification.json`, `VERIFICATION.md`, and local logs/candidate ZIP under `output/delivery/logs/`. Failures return exit 1 and preserve the last release ZIP. Only a passing run builds the default release ZIP. `--baseline` is for an independent baseline check, not combined acceptance; it never waives the chart failure.

After freezing documentation and committing the reviewed changes:

```text
python output/delivery/build-package.py
python output/delivery/build-package.py --verify output/delivery/challenge-5-implementation.zip
```

Confirm `execution_evidence_matches` is true and verification status is `verified` with `scope=combined_runtime` in the packaged report. Runtime changes require a new gate run; documentation-only changes require a rebuild/hash check. The final hash is the adjacent `.sha256`, not an intermediate candidate's hash. Runtime verification never records manual acceptance automatically.

## Human checks

- [ ] Review the integration branch against main. Main merge remains a separate supervisor action.
- [ ] Confirm no unexpected changes to frozen risk/model/input bytes.
- [ ] Check ATL/DFW x 3/6/12h x reveal on/off in the actual browser.
- [ ] Verify estimated capacity label, population, assumptions, support and uncertainty statement; no manufactured observed-AAR curve.
- [ ] Confirm missing/rejected optional-publication coverage in Member 1's tests; review those test results, not just publication existence.
- [ ] Confirm the app keeps metering/rescheduling unavailable without supported inputs.
- [ ] Verify map/radar tiles, or explicitly disclose network unavailability.
- [ ] Regenerate the controller review brief for the demonstrated exact snapshot; keep it separate from operational advice.
- [ ] Rehearse `JUDGING-DEMO.md` within three minutes, including the false alarm.
- [ ] Verify final ZIP inventory/hashes, extracted risk verifier and current execution evidence.
- [ ] Confirm submission destination and submit through the team's normal process; record actual time.

## Supervisor record — fill only with observed evidence

| Field | Value |
|---|---|
| Tested runtime commit | `0fe4385` implementation; runtime fingerprint in verification.json; final documentation-frozen commit in archive receipt |
| Member 1 publication run | `m1-capest-20261031T072310Z-a27968` (included and hash-verified) |
| Automated gate result/report | `verified`, `combined_runtime`; 501 passed, risk/app exits 0; `output/delivery/verification.json` |
| Final ZIP SHA256 | Adjacent `challenge-5-implementation.sha256` and receipt after documentation freeze |
| Browser review and reviewer | Pending |
| Rehearsal duration | Pending |
| Submission timestamp and receipt | Pending |
| Outstanding limitations | Capacity accuracy against independent facility AAR is unverified; no operational savings demonstrated |
| Supervisor acceptance | Pending |
