# ATL/DFW flow-planning replay: Airbus Track, Challenge 5

A local Streamlit decision-support prototype for an **airport flow planner** at Atlanta (ATL) and Dallas/Fort Worth (DFW).

- **Today:** capacity cuts happen reactively, once weather arrives, and delays cascade.
- **This tool:** at a historical cutoff, shows what was known 3, 6 and 12 hours ahead. That covers forecast weather and runway-relative wind, the probability each departure is delayed over 45 minutes, traffic context, a capacity estimate, and review priorities.
- **Boundary:** read-only. A human reviews everything, and the app sends no operational instructions.

**No LLM is used.** Forecasting, classification and capacity estimation are statistical tasks; they need reproducible, testable models and leakage control, not text generation.

## Current status (31 Oct 2026)

| Build | Tests | Notes |
|---|---|---|
| `main` | 410 passed, **31 failed**; app smoke fails | The Figma dashboard rebuild (`a3f3484`) crashes the replay screen ("Component 'watchlist' is not registered"), and some older tests call removed APIs. **Fix before presenting.** |
| `codex/member-1-accuracy-integration` | 501 passed; release gate `verified` | Adds review priorities and an illustrative arrival scenario to Compare. Pre-Figma UI; conflicts with `main` in `src/dashboard/app.py`. |

Both builds use the same published models. All figures come from [`handover/judging-figures.md`](handover/judging-figures.md); open items are in [`handover/presentation-readiness-review.md`](handover/presentation-readiness-review.md).

## Quick start

Python 3.14 with the versions in `requirements-observed.txt`. A clean install hasn't been tested yet.

```text
python -m pip install -r requirements-observed.txt
python -m streamlit run app.py
```

The published artifacts are committed, so the app runs offline; only map tiles and live weather need a network. `DASHBOARD_DATA_ROOT` selects another artifact folder.

## Automatic public-data pipeline

Every step downloads and processes public data with no manual work. Run them from the repository root:

```text
python -m src.data_capacity run                                  # IEM METAR/TAF, BTS, NOAA -> flights, weather, features, traffic (~16 min from empty caches)
python -m src.data_capacity run --cache-only                     # offline rerun from cached downloads
python -m src.data_capacity estimate-capacity --from-published   # weather-conditioned capacity estimate
python -m src.flight_risk train                                  # delay-risk model on verified Member 1 inputs
python -m src.flight_risk verify                                 # hash, key and range checks on the risk publication
```

| Source | Use |
|---|---|
| IEM METAR and TAF archives | Weather known at each cutoff: issue time plus latency, amendments, prevailing vs TEMPO/PROB groups |
| BTS On-Time Reporting | Flights and hourly traffic. Full ATL/DFW extracts for 2023-01..2025-07 (3,255,141 flights) are committed in [`data/public/bts/filtered/`](data/public/bts/filtered/) |
| NOAA Storm Events | Retrospective evaluation cohorts only, never a predictor |
| Challenge CSV (`data/weather/`) | Canonical flight sample. Its embedded weather columns are not used, because there's no record of when those values were available |

Airports come from a registry (`src/shared.py`). The pipelines accept any registered ICAO/IATA code and refuse airports with a missing heading or timezone instead of guessing (`tests/data_capacity/test_generic_airport.py`, `tests/flight_risk/test_airports.py`).

## What it delivers (held-out January–July 2025)

Splits are by airport-local date: train 2023, select on 2024, test January–July 2025.

**Severe departure delay (>45 min).** Gradient boosting with cutoff-safe weather, 10,604 predictions for 3,537 flights.

| | ATL +3h | ATL +6h | ATL +12h | DFW +3h | DFW +6h | DFW +12h |
|---|---|---|---|---|---|---|
| Precision | 26.1% | 29.2% | 31.2% | 23.5% | 25.5% | 26.3% |
| Recall | 52.2% | 50.0% | 32.0% | 48.9% | 50.0% | 49.6% |
| PR-AUC (baseline) | 0.262 (0.208) | 0.275 (0.208) | 0.258 (0.208) | 0.249 (0.196) | 0.257 (0.196) | 0.271 (0.196) |
| Recall at the same alert workload, model vs historical-rate baseline | 52.2% vs 43.2% | 50.0% vs 37.8% | 32.0% vs 24.7% | 48.9% vs 45.1% | 50.0% vs 42.4% | 49.6% vs 40.7% |

- PR-AUC is about twice the 13–15% base rate.
- Weather beats schedule-only on matched flights in every cell.
- Probabilities are uncalibrated (a calibration experiment was not adopted).
- This measures alert quality only. No delay-minute or fuel savings are claimed.

**Arrival capacity.**
- **Genuine facility AAR: unmet.** The organisers supplied none, and FAA ASPM requires credentials; the attempts are logged in `artifacts/capacity/data_access.json`.
- **Capacity estimate (proxy):** a high-demand, weather-regime frontier for reporting carriers (`artifacts/capacity_estimate/`). Its q0.90 pinball loss beats a no-weather baseline by 1.5–2%. It isn't AAR: there are no uncertainty bounds and no whole-airport scaling. Two further accuracy experiments were rejected under rules fixed in advance.
- **Arrivals forecast:** forecast of reporting-carrier arrivals per hour, RMSE 9.26 vs 15.43 baseline. In weather-impacted hours, weather improves RMSE by 1.83 (95% CI −3.46 to −0.46). This is throughput, not AAR, and team agreement to present it is pending.

**Safeguards (challenge "want to avoid").**
- **No leakage:** only inputs available at the cutoff are used, with tests.
- **Runway direction:** crosswind and tailwind are computed against ATL 080° and DFW 180°.
- **Normalised delays:** rates are published with their denominators.
- **Not single-airport:** the pipelines are registry-driven.

**Decision support.**
- Ranked departure review priorities, with an exact-snapshot companion brief: `python -m tools.delivery.controller_brief --airport KATL --asof 2025-07-12T20:00:00Z --lead 3`.
- Metering and rescheduling stay **unavailable**: there's no verified complete demand, capacity or backlog.

## Data coverage

| Item | Figure |
|---|---|
| Challenge flight sample (ATL/DFW) | 25,299 flights, which is 0.8% of full BTS traffic |
| Decoded METAR + TAF | 147,002 rows |
| Cutoff-safe weather snapshots | 135,786 |
| Hourly reporting-carrier traffic | 90,524 rows, 31 months, 0 failed |
| NOAA storm events (retrospective) | 1,839 |

Published runs: data/capacity `m1-20261031T084129Z-f83c9b`, risk `0949771a54bb4e49b4e215528eb5d46b`, capacity estimate `m1-capest-20261031T084305Z-940bb8`.

## Verify and package

```text
python -m pytest tests -q
python -m tools.delivery.verify_release        # fresh package extraction: risk verify, full suite, app smoke
python output/delivery/build-package.py
python output/delivery/build-package.py --verify output/delivery/challenge-5-implementation.zip
```

`verify_release` writes `output/delivery/VERIFICATION.md` and `verification.json`. A failure returns a nonzero exit and never replaces the last release ZIP. Automated checks don't cover map tiles, browser layout or the timed demo; those are in [`handover/SUBMISSION-CHECKLIST.md`](handover/SUBMISSION-CHECKLIST.md).

## Repository map

| Path | Contents |
|---|---|
| `src/data_capacity/` | Data acquisition, weather features, traffic, capacity estimate, arrivals forecast (Member 1) |
| `src/flight_risk/` | Delay-risk model, evaluation, queue and scenario logic (Member 2) |
| `src/dashboard/`, `app.py` | Streamlit UI |
| `artifacts/` | Published, hash-verified model outputs |
| `tools/delivery/`, `output/delivery/` | Release verification, packaging, controller brief |
| `handover/` | Demo script, checklist, figures, member results and status |

## Limitations

- No independent AAR validation.
- Flights are a sample and BTS covers reporting carriers only, so there are no whole-airport claims.
- Rare weather (winter, ATL thunderstorms) is thin.
- No operational benefit has been simulated or demonstrated.
