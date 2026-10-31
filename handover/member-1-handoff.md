# Member 1 handoff: public data, weather features, AAR capacity

State: **ready_for_review**. Branch `zeph`. Current published run: `m1-20261031T065014Z-eacdd5`. Live status: `handover/status-member-1.json`. Plan reference: `parallel-plan.md` section 3.

**Challenge 5 is not complete: there is no AAR prediction.** Genuine facility AAR lives only in FAA ASPM, which needs an account login. The modelling code is built and tested on synthetic fixtures. Once someone drops a real export into `data/public/aspm/` (spec in that folder's README), a single `run --cache-only` produces real RMSE results. Each request and reply belongs in `data/public/aspm/attempts.json`; the run copies the log into `data_access.json`.

## Plan tasks

| # | Task | Result |
|---|---|---|
| 1.1 | LF JSON | `write_json` writes `\n` on every OS; a test fails on any `\r` in published JSON |
| 1.2 | Pursue AAR | **Gate 2 decision: AAR unmet.** The attempt log has 2 entries: the automated ASPM check (refused: login required) and the organisers' answer (no AAR data provided). The decision is published in `data_access.json → aar.gate_2_decision`. No proxy is published |
| 1.3 | BTS traffic | `traffic_hourly.parquet`: 90,524 rows, KATL and KDFW, all 31 months 2023-01..2025-07, 0 failed months |
| 1.4 | TAF validity | 0 inverted rows (was 5,582). The 9 contract features are unchanged; 35 of 135,786 rows gain month-end TEMPO/PROB groups in the `cond_*` columns |
| 1.5 | Clean automatic run | Fresh checkout, empty caches, `python -m src.data_capacity run`: 16m01s, exit 0, no manual step, 0 failed downloads (details below) |
| 1.6 | Airport-generic | Test-only registry with a synthetic KORD (heading 270) runs every stage. A missing heading or timezone is refused with the field named. No third airport appears in artifacts |
| 1.7, 1.8 | AAR model and queue leads | Not run: no AAR (Gate 2). Code for 1.7 is ready and tested on synthetic data; 1.8 was not started, per the plan |

## Commands (verified)

```powershell
python -m src.data_capacity --help
python -m src.data_capacity run                 # full automatic run: downloads, publishes, manifest last
python -m src.data_capacity run --cache-only    # offline rerun from cached downloads (about 4 min)
python -m src.data_capacity run --no-bts        # skip BTS; traffic_hourly and the arrivals forecast are then unavailable
python -m src.data_capacity run --no-throughput # skip the observed-arrivals forecast
python -m src.data_capacity bts --months 2023-01 2023-02 --workers 4   # BTS only
python -m src.data_capacity access              # source reachability probe (JSON to stdout)
python -m pytest tests/data_capacity -q         # Member 1 suite
python -m pytest tests -q                       # whole repo: 299 passed
```

`--airports` accepts any ICAO/IATA code in the shared registry; airports that are missing or incomplete are refused, never guessed. `--start` and `--end` set the local date range, and BTS months follow it.

## Outputs (contract v2.0)

| Path | Rows | Status |
|---|---|---|
| `data/processed/flights.parquet` | 25,299 | available (sample coverage), IDs from `src.shared.flight_key` |
| `artifacts/capacity/weather.parquet` | 147,002 | available |
| `artifacts/capacity/weather_features.parquet` | 135,786 | available (99.96% of rows) |
| `artifacts/capacity/traffic_hourly.parquet` | 90,524 | available; `coverage='reporting_carriers'` |
| `artifacts/capacity/forecast.parquet` | 0, typed, includes `aar_observed` | **unavailable**: no genuine AAR |
| `artifacts/capacity/throughput_forecast.parquet` | 30,465 held-out rows | available; observed arrivals, **not AAR**; team agreement pending |
| `artifacts/capacity/throughput_evaluation.json` | – | measured results, cohorts, failure case |
| `artifacts/capacity/evaluation.json` | – | **unavailable**, includes the exact extract request |
| `artifacts/capacity/data_access.json` | – | partial; probes, attempt log, acquisition records |
| `data/processed/provenance.json` | – | partial |
| `data/processed/storm_events.parquet` | 1,839 | retrospective cohorts only, never a predictor |
| `artifacts/capacity/manifest.json` | – | partial; hashes, coverage, capabilities |

Not published, on purpose: `arrival_demand`, `initial_backlog` and `eligible_flights`. Full BTS counts don't change this. They are reconstructed after the fact for the reporting carriers only, so they are not demand known at a cutoff.

## Observed-arrivals forecast (plan section 7 stretch, NOT AAR)

Built at Member 1's request. **Agreement from Members 2 and 3, which section 7 requires, is still pending.** The evaluation records this, and Member 3 should not present it until it is agreed.

- **What it is:** a forecast of reporting-carrier arrivals that land in the target hour (`actual_count` from `traffic_hourly`), at 3, 6 and 12 hours ahead. `label_kind = observed_reporting_carrier_arrivals`, with no `aar` columns. Throughput is limited by demand, by BTS coverage and by upstream flow programmes, so it is not runway capacity.
- **Inputs:** cutoff-safe weather features, calendar fields, and the target hour's published schedule. Treating the schedule as known at the cutoff is a disclosed assumption: BTS CRS times reconstruct it and include flights later cancelled.
- **Models:** on the same rows and the contract split, a training-only completion-ratio baseline, a schedule-only model and a schedule + weather model.

Measured on the 2025-01..07 test set (30,465 snapshot rows; RMSE in arrivals/hour; mean observed 35.0):

| | Weather model | Schedule only | Baseline |
|---|---|---|---|
| All hours | 9.26 | 9.38 | 15.43 |
| Thunderstorm forecast (n = 899) | 15.87 | 17.24 | 26.41 |
| Frozen precipitation forecast (n = 146) | 22.10 | 33.77 | 37.00 |
| Ceiling < 1000 ft (n = 2,101) | 10.78 | 12.63 | 20.33 |
| NOAA storm hours, retrospective (n = 558) | 21.25 | 25.40 | 31.86 |
| Benign (n = 24,667) | 8.75 | 8.56 | 13.79 |

- **What weather adds:** for weather-impacted hours, weather minus schedule-only = −1.83 RMSE, 95% date-block bootstrap interval [−3.46, −0.46], a clear gain. Over all hours it is −0.13 [−0.40, +0.14], not significant, because 81% of hours are benign.
- **Intervals:** Mondrian split-conformal, 90% nominal. Empirical coverage is 0.91 at ATL but 0.79 at DFW, which looks like a 2024 → 2025 shift. Storm cohorts reach 0.56–0.77, so intervals are still too narrow in severe weather.
- **Failure case:** ATL, cutoff 2025-04-10, 77 arrivals scheduled and 8 observed. The cutoff TAF forecast rain but no thunderstorm; NOAA logged Thunderstorm Wind. That convection was not forecastable at the cutoff.
- **Fix found by an earlier failure:** for the Jan 2025 Atlanta winter storm (82 scheduled, 16 observed) the TAF did forecast `-SNPL`/`FZRA`, but `precip_flag` couldn't separate that from rain. The additive `frozen_precip_flag` (and its `cond_`/`obs_` versions) cut RMSE in frozen-precipitation hours from 33.8 (schedule-only) to 22.1.

## traffic_hourly semantics (for Member 3)

- Key `(airport, hour_utc, direction)`. `scheduled_count` counts scheduled gate times in the hour, cancellations included. `actual_count` counts reconstructed runway times: wheels-off for departures, wheels-on for arrivals. Cancelled flights don't count; diverted flights don't count as arrivals.
- Zero means no reporting-carrier movement in a covered hour. Hours from failed months are absent, not zero. `actual_count` is null for the last 2 hours before a coverage gap, where flights from the missing month could have operated early.
- Typical load: ATL median 45 scheduled arrivals per hour (maximum 112); DFW median 31 (maximum 98).
- Label it as retrospective traffic for reporting carriers. Never present it as demand, capacity or AAR.

## How to join weather features

- Snapshot key: `(airport [ICAO], asof_utc, target_hour_utc, horizon_hours)`; `airport_iata` is also provided.
- For a departure: `target_hour_utc = floor(scheduled_dep_utc, 1h)` and `asof_utc = target_hour_utc - h`, for h in 3, 6, 12.
- Display: visibility 6.01 means over 6 SM (TAF P6SM). Ceiling 30000 means no ceiling forecast. A gust equal to the wind speed means no gust forecast. `temperature_c` is the METAR observed at the cutoff.

## Evidence

- **Leakage control.** The TAF used is the latest bulletin available at or before the cutoff (issue time + 10 min, max age 12 h). METAR is observation time + 10 min (max age 2 h). Tests prove a later amendment can't change an earlier snapshot, and TEMPO never replaces the prevailing forecast.
- **TAF periods.** A prevailing group ends at the next prevailing group, or at the end of the 30 h period of its 00/06/12/18Z cycle. TEMPO/PROB periods come from the raw `DDHH/DDHH` text, because IEM's `fx_valid_end` is wrong across month ends.
- **Wind.** Components are computed against fixed headings (ATL 080, DFW 180). Calm gives 0; variable or missing direction gives null; `crosswind_upper_kt` bounds the unknown cases.
- **Identity.** IDs come from `src.shared.flight_key`. All 726 Jan-2023 sample flights match the full BTS month on ID, schedule, delays and cancellation; the sample is 0.8% of BTS ATL/DFW traffic.
- **Failure case shown.** AAR is unavailable, with the reason, the attempt log and the remedy.

## Clean run (task 1.5)

- **Setup:** a detached git worktree at commit `aef4aa8`, so no download caches; the only input was the tracked challenge CSV.
- **Command:** `python -m src.data_capacity run`, from 2026-10-31 06:06:28Z to 06:22:28Z (16m01s wall time). Exit 0, no manual step.
- **Downloads:** 31 of 31 BTS months, all IEM METAR/TAF chunks and all NOAA storm years, with 0 failures. The resulting run was `m1-20261031T060631Z-ca753e`, status partial (AAR unavailable only).
- **Reproducibility finding:** flights, traffic and storm outputs matched the cached run exactly. Weather did not: IEM returns the same rows in a different order between downloads, and decoding depended on that order when choosing between duplicates in the same minute. Decoding now sorts the input on a full key, and a test shuffles rows. Both download sets now produce identical weather and features.
- **Effect of that fix:** 12 contract-feature cells (6 snapshot rows) changed. In each case the tie between same-minute duplicates (a DFW TAF with two initial groups, and a METAR with an AUTO duplicate) is now resolved the same way every time. Member 2's pinned inputs are unaffected; whether to refresh is Member 2's call.
- **Tests in the clean worktree:** `python -m pytest tests/data_capacity -q` gave 80 passed.

## Unmet / next owner

1. Genuine AAR (core requirement): **unmet at Gate 2.** The organisers provided none and ASPM needs credentials. If an export ever arrives, put it in `data/public/aspm/*.csv`, log it in `attempts.json`, then run `python -m src.data_capacity run --cache-only`. The section 7 stretch is now implemented as a separately named artifact (see above), pending team agreement.
2. Demand and backlog: unobtainable from public sample or BTS data, so the queue and advice stay refusals (Member 2 and Member 3 report this).
3. Linux check of hashes: JSON output is now LF-only and `.gitattributes` keeps artifacts byte-exact. The test suite has not been run on Linux from this machine.
