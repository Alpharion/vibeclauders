# Building the portable replay package

Run `python output/delivery/build-package.py` from the repository root. The builder writes `output/delivery/challenge-5-implementation.zip` with matching `.sha256`, `.manifest.json` and `.receipt.json` files.

The archive contains its own generated `BUNDLE_README.md` and `BUNDLE_MANIFEST.json`, reflecting the actual source commit/dirty state, present producer runs, payload hashes and matching execution evidence. The root-level `BUNDLE_MANIFEST.json` is a location guide, not an inventory for a previous package.

The committed `requirements-observed.txt` records the published model environment and is preserved unchanged. Package generation does not install dependencies or prove a clean installation. Data/model/source bytes are preserved; raw caches, old releases and VCS metadata are excluded.

Verify with `python output/delivery/build-package.py --verify output/delivery/challenge-5-implementation.zip`. After extraction, run `python -m src.flight_risk verify` and the checks in `README.md`.

At implementation baseline `737b468`, the reporting-carrier chart has a known Plotly Timestamp annotation failure. Packaging and risk verification can pass while the app remains unsuitable for the final demo. See `output/delivery/VERIFICATION.md`. Optional capacity estimates are only included if actually published; Member 2 does not wait for Member 1.
