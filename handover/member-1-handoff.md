# Member 1 handoff: public data, weather features, AAR capacity

State: **ready_for_review**. Current run: `m1-20261031T045159Z-3df67d`. Live status is in `handover/status-member-1.json`.

**Challenge 5 is not complete: there is no AAR prediction yet.** Genuine facility AAR lives in FAA ASPM, which needs an account login. The modelling code is built and tested. Once someone drops a real export into `data/public/aspm/` (spec in that folder's README), one command produces real RMSE numbers.

## Commands (verified)

```powershell
python -m src.data_capacity --help
python -m src.data_capacity run                          # full run: downloads, then publishes; manifest written last
python -m src.data_capacity run --cache-only             # offline, reproducible from cached downloads
python -m src.data_capacity run --bts-months 2023-01     # also ingest BTS monthly archives automatically
python -m src.data_capacity bts --months 2023-01 2023-02 # BTS ingestion only
python -m src.data_capacity access                       # source reachability probe (JSON to stdout)
python -m pytest tests/data_capacity -q                  # 41 passed
```

Other options: `--airports` takes any registry ICAO/IATA code (unknown airports are rejected, never guessed); `--start` and `--end` set the date range. With a full download, a run takes about 3 minutes.

## Outputs (contract v2.0)

| Path | Rows | Status |
|---|---|---|
| `data/processed/flights.parquet` | 25,299 | available (sample coverage) |
| `artifacts/capacity/weather.parquet` | 147,010 | available |
| `artifacts/capacity/weather_features.parquet` | 135,786 | available (99.96% of rows) |
| `artifacts/capacity/forecast.parquet` | 0, typed | **unavailable**: no genuine AAR |
| `artifacts/capacity/evaluation.json` | – | **unavailable**, includes the exact extract request |
| `artifacts/capacity/data_access.json` | – | partial |
| `data/processed/provenance.json` | – | partial |
| `data/processed/storm_events.parquet` | 1,839 | retrospective cohorts only, never a predictor |
| `artifacts/capacity/manifest.json` | – | partial; holds hashes, coverage and capabilities |

Not published, on purpose: `arrival_demand`, `initial_backlog` and `eligible_flights`. The flight data is a sample, so there is no complete demand and no observed queue at the cutoff. Member 2's queue and advice must therefore stay unavailable.

## How to join

- Snapshot key: `(airport [ICAO], asof_utc, target_hour_utc, horizon_hours)`. `airport_iata` is also provided.
- For a departure: `target_hour_utc = floor(scheduled_dep_utc, 1h)` and `asof_utc = target_hour_utc - h`, for h in 3, 6, 12.
- Model inputs: use the 9 contract features. Extra documented features are `crosswind_upper_kt`, `crosswind_gust_kt`, `cond_*` (TEMPO/PROB) and `obs_*` (METAR at cutoff). Semantics are in `manifest.json → capabilities.weather_features.feature_semantics`.
- **Never** use the weather columns embedded in the challenge CSV. Nothing records when those values became available.

## Evidence

- **Leakage control.** The TAF used is the latest bulletin available at or before the cutoff (issue time + 10 min latency, max age 12 h). METAR is observation time + 10 min (max age 2 h). Tests show a later amendment cannot change an earlier snapshot, and TEMPO groups never replace the prevailing forecast. The validator fails the run on any input available after the cutoff.
- **Wind.** Crosswind and tailwind are computed against fixed headings (ATL 080, DFW 180). Calm wind gives 0. Variable or missing direction gives null, not 0. 3–5% of rows have a null crosswind because of variable winds; `crosswind_upper_kt` covers those rows.
- **Identity.** All 726 Jan-2023 sample flights match the full BTS month exactly. The key is still **provisional** because `src/shared.py` does not exist yet. Member 2 must re-verify the IDs once Member 3 publishes it.
- **Failure case shown:** AAR capability unavailable, with the reason and the remedy.

## Unmet / next owner

1. Genuine AAR: supervisor or a team member with ASPM access → `data/public/aspm/*.csv` → rerun with `--cache-only`.
2. `src.shared.flight_key` and the airport registry: Member 3.
3. `implementation-plan.md`, referenced by the handoffs, is not in this repo: Member 2.
