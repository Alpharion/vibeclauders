# Full-BTS canonical training input: deadline follow-up

## Delivered

`src/flight_risk/full_bts.py` provides an opt-in builder for the existing monthly filtered BTS caches. It validates SHA-256 against each sidecar, original-archive hash presence, ATL/DFW scope, row count, date/month membership and unique chronological month selection. All requested caches must exist before an output is opened. Defaults cover all 31 months from January 2023 through July 2025.

The existing canonical flight builder handles local-time conversion, midnight rollover, DST flags, flight identity including carrier, exact duplicate collapse and conflicting-key exclusion. One month is decoded at a time and written to Parquet row groups using the existing canonical sample schema, limiting raw-frame memory. Labels and all retrospective outcome columns remain present as labels/evidence; the existing model's explicit feature allowlist must remain in force.

Output population is explicitly `reporting_carriers` from `bts_ontime_prezip`, rather than the original canonical builder's sample label. The output manifest audits monthly source hashes, canonical rows, departures/eligible/severe labels by airport and chronological split, and original sample flight-key overlap. An ATL–DFW leg is one unique canonical row; touching-airport row counts must not be claimed as eligible training departures. No prediction or accuracy improvement is claimed by this builder.

Run on a machine with the caches:

```text
python -m src.flight_risk.full_bts --cache-dir <repo>/data/public/bts/filtered --output tmp/full-bts-experiment
```

Outputs: `tmp/full-bts-experiment/flights.parquet` and `manifest.json`. This is separate experiment input, never a replacement production publication. The existing `prepare_canonical` accepts this schema. Training must fit only 2023; early 2024 can select thresholds, late 2024 chooses the candidate under the coordinator's frozen protocol. Score both the full population and original sample on matched cohorts after selection. The table itself does not perform training or adoption.

## Actual data build after the GitHub upload

The first local search correctly found no raw caches: earlier provenance pointed to another team member's machine. Following the user's instruction to check GitHub, a fresh fetch found commit `18d8338` on main containing all 31 filtered monthly Parquet files and sidecars under `data/public/bts/filtered/`. Binary blobs were extracted to `tmp/full-bts-source/filtered` and verified against their sidecar hashes. No BTS network redownload was needed.

At **16:26:17 Singapore time on 31 October 2026**, the builder completed all months. Output: `tmp/full-bts-experiment/flights.parquet`; SHA-256 `e001ed4f942d975902959e7af6fbe5638c0f0886c090ab1b03e650ea5d98d3e6`. Full source hashes and monthly audits are in its adjacent `manifest.json`. The model agent was notified immediately.

| Population | Count |
|---|---:|
| Canonical flights touching ATL/DFW | 3,255,098 |
| Departures originating at ATL/DFW | 1,644,369 |
| Eligible noncancelled labelled departures | 1,618,808 |
| Severe departure delays (>45 min) | 178,371 |
| 2023 eligible training departures | 614,524 |
| 2024 eligible validation departures | 646,245 |
| 2025 Jan–Jul eligible backtest departures | 358,039 |

The existing sample has 25,299 unique canonical keys: 25,297 match the full table. The two missing keys are incoming CLT→ATL DL3002 flights on 18 and 29 April 2024; neither exists in the corresponding filtered raw month. All **16,151 original sample ATL/DFW departure keys match**. These are identity-overlap checks, not model accuracy or a label-equality claim.

The 3.255-million touching-airport count must not be presented as eligible training examples: 2023 has 614,524 eligible target departures, and remaining dates are held out according to the protocol. This builder does not fit or adopt a model. The model agent owns measured comparison and selection.

## Verification

`python -m pytest tests/flight_risk/test_full_bts.py -q --basetemp=tmp/full-bts-tests --tb=short`: **7 passed**, exit 0. Checks cover missing coverage before publication, tampered cache rejection, invalid month / conflicting duplicate exclusion, stable outcome-independent identity with carrier discrimination, canonical schema/population/split counts, duplicate month rejection and fixed experiment-window enforcement. `git diff --check` passes for the owned files.

No production artifacts or frozen models were changed. This report distinguishes implemented data plumbing from unavailable full-data experiment evidence.
