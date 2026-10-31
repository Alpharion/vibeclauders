# Building the portable replay package

Run `python -m tools.delivery.verify_release` to test a combined snapshot before packaging. It requires Member 1's capacity-estimate publication and passing tests/app smoke. Failed checks return a nonzero exit and preserve the last release ZIP; a passing automated run still requires the human checks in `handover/SUBMISSION-CHECKLIST.md`. The judging script and companion controller brief are included in the package when present.

Run `python output/delivery/build-package.py` from the repository root. The builder writes `output/delivery/challenge-5-implementation.zip` with matching `.sha256`, `.manifest.json` and `.receipt.json` files.

The archive contains its own generated `BUNDLE_README.md` and `BUNDLE_MANIFEST.json`, reflecting the actual source commit/dirty state, present producer runs, payload hashes and matching execution evidence. The root-level `BUNDLE_MANIFEST.json` is a location guide, not an inventory for a previous package.

The committed `requirements-observed.txt` records the published model environment and is preserved unchanged. Package generation does not install dependencies or prove a clean installation. Data/model/source bytes are preserved; raw caches, old releases and VCS metadata are excluded.

Verify with `python output/delivery/build-package.py --verify output/delivery/challenge-5-implementation.zip`. After extraction, run `python -m src.flight_risk verify` and the checks in `README.md`.

At implementation baseline `737b468`, the reporting-carrier chart has a Plotly Timestamp annotation failure. Member 1 separately published a fix and a reporting-carrier capacity proxy in `5805f89b8ae908b330e1e981536f52ae1725c2ee` (run `m1-capest-20261031T072310Z-a27968`). Their inclusion and passing behavior must be established by this package's inventory and current `output/delivery/VERIFICATION.md`, not by that publication claim alone. The proxy is not independently observed facility AAR; browser and supervisor acceptance remain manual.
