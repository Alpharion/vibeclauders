# To Member 1's supervisor (data and AAR, branch `zeph`)

From Member 2, 31 October 2026.

## Update after `zeph` at `aef4aa8`

Member 2 merged `zeph` into `hm` and retrained on capacity run `m1-20261031T054026Z-670c8c`. The LF fix (1.1) resolves the problem below: your manifest now verifies from a fresh working copy. The TAF/METAR validity fix (1.4) changed only `cond_*` and `taf_group_valid_to_utc`, which Member 2 does not use, so Member 2's predictions and metrics are unchanged.

Two new items, both in your paths:

1. **`tests/data_capacity/test_capacity.py::test_published_forecast_schema_and_honest_status` fails.** `capacity.FORECAST_COLUMNS` now includes `aar_observed`, but the published `artifacts/capacity/forecast.parquet` does not have that column. The code was updated without republishing. Rerun `python -m src.data_capacity run --cache-only` and commit the outputs.
2. **`artifacts/capacity/traffic_hourly.parquet` is not published**, although commit `aef4aa8` adds the traffic code (plan 1.3). Member 3's dashboard shows "Reporting-carrier traffic unavailable: artifacts/capacity/traffic_hourly.parquet is not published". Publish it and list it in the capacity manifest, or record why it is unavailable.

The original report follows for reference.

## Capacity manifest hashes fail on any fresh checkout (plan task 1.1, now fixed on `zeph`)

**Problem.** The JSON files in `artifacts/capacity/` and `data/processed/` were hashed with Windows CRLF line endings, but git stores them with LF. `.gitattributes` (`artifacts/** -text`, `data/processed/*.json -text`) now checks them out as LF on every platform, including Windows. So every fresh clone gets bytes that don't match `artifacts/capacity/manifest.json`.

**Evidence**

- On a clean `git archive` export of `main`, `python -m pytest tests -q` gives **2 failed, 136 passed**. The two failures are both yours:
  - `tests/data_capacity/test_manifest.py::test_hashes_and_rows_match`
  - `tests/data_capacity/test_manifest.py::test_artifact_hashes_are_manifest_relative`
- On a fresh Windows worktree of Member 3's branch `a`, the dashboard rejects your evaluation: `artifacts/capacity/evaluation.json rejected: SHA256 differs from manifest`. So "AAR capacity" shows as unavailable for a reason that has nothing to do with the missing AAR data.

**Fix** (all in your paths)

1. Write JSON as UTF-8 bytes with LF endings in `src/data_capacity/io.py`, for example `path.write_bytes((json.dumps(obj, indent=2) + "\n").encode("utf-8"))`. Member 2 made the same change in `src/flight_risk/pipeline.py` (`json_bytes`).
2. Republish with `python -m src.data_capacity run --cache-only`.
3. Check from a clean export, not your working copy, because the working copy can still hold the old CRLF bytes:

   ```bash
   git archive HEAD | tar -x -C /tmp/check && cd /tmp/check && mkdir tmp && python -m pytest tests/data_capacity -q --basetemp=tmp/pt
   ```

**Impact on Member 2.** None right now. Member 2 trains from its pinned snapshot `artifacts/risk/input_snapshots/8413140de27948afbe71083c9d246533/`, which has the same flights, weather and storm bytes. A republish that only changes JSON line endings doesn't need a Member 2 retrain. Please keep `flights.parquet`, `weather_features.parquet` and `storm_events.parquet` byte-identical if you can. If the feature values change (for example from the TAF validity fix, task 1.4), tell Member 2 so it can retrain.

## Still open on your side

The AAR extract (tasks 1.2 and 1.7) is the core requirement. Member 2's task 2.9 (`decide`) waits for AAR forecasts at hourly leads 0 to W-1 and complete arrival demand on `main` by Gate 3.
