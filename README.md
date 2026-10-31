# ATL/DFW flow-planning replay

A local Streamlit dashboard for an **ATC / airport flow planner** (Airbus Track, Challenge 5).

- **Today's workflow:** reactive. Planners respond once weather has already cut arrival capacity and delays are building.
- **Decision aided:** at a historical cutoff, should arrival metering be reviewed, and which departures carry the highest severe-delay risk 3, 6 or 12 hours ahead?
- **Boundary:** read-only. Every advisory needs human review, and the app transmits nothing.

Measured prediction quality (Evaluation tab) is separate from simulated operational value (Decision support tab). Neither is a claim about whole-airport impact while traffic is a sample.

## Run

```bash
pip install -r requirements.txt
python -m streamlit run app.py
python -m pytest tests/dashboard -q
```

The app reads producer output from the repository root. Set `DASHBOARD_DATA_ROOT` to read another folder. With nothing published it still starts, and shows why each capability is unavailable.

## Layout

| Path | Purpose |
|---|---|
| `src/shared.py` | Scored airport registry (`AIRPORTS`) and `flight_key` |
| `data/reference/airports.json` | Airport reference data |
| `src/dashboard/data.py` | Manifest, hash, schema and key validation; capability states |
| `src/dashboard/views.py` | Exact-snapshot selection and evidence gates |
| `src/dashboard/plots.py`, `app.py` | Charts and UI |

## Requirements and evidence

Status reflects this repository today. No producer artifacts are present, so every row marked "UI ready" has been exercised on synthetic test fixtures only.

| Challenge requirement | Artifact | Check | Status and limitation |
|---|---|---|---|
| Hourly AAR prediction at 3/6/12 h | `artifacts/capacity/forecast.parquet`, `evaluation.json` | `test_unsafe_aar_row_is_refused` | **Unmet until Member 1 publishes genuine AAR.** No proxy is shown |
| AAR RMSE against baseline | `artifacts/capacity/evaluation.json` | `test_valid_artifacts_and_selection_updates_panels` | UI ready; no measured result yet |
| Cutoff-safe weather and runway-relative wind | `artifacts/capacity/weather_features.parquet`, `weather.parquet` | `test_future_amendment_is_excluded` | UI ready; awaiting Member 1 |
| Severe departure-delay probability (over 45 min) | `artifacts/risk/predictions.parquet` | `test_risk_join_keeps_scored_cohort` | UI ready; real run not loaded here. Member 2 reports a schedule-only model, so weather skill is unmeasured |
| Precision, recall, PR-AUC, Brier, reliability | `artifacts/risk/evaluation.json` | `test_launch_with_partial_artifacts` | UI ready; real run not loaded here |
| Normalised historical trends | `artifacts/risk/normalized_metrics.parquet` | `test_history_recomputes_from_denominators`, `test_outcomes_locked_until_reveal` | UI ready; sample cohorts behind Reveal outcomes |
| AAR observed versus predicted trend | None contracted | Requested in `handover/status-member-3.json` | **Unmet.** The contract has no observed-AAR column |
| Arrivals, departures and movements | `data/processed/flights.parquet` | `test_movements_reconcile_and_are_labelled_sampled` | UI ready; awaiting Member 1 |
| Backlog and recovery queue | `artifacts/risk/queue.parquet` | `test_valid_queue_passes`, `test_queue_violation_is_detected` | **Unmet.** Needs genuine capacity, complete demand and cutoff backlog |
| Early flow-management advice | `artifacts/risk/recommendations.json` | `test_recommendation_refused_for_other_snapshot` | Withheld with reasons until the queue exists |
| Flight rescheduling | `data/processed/eligible_flights.parquet` | `test_revised_times_need_eligibility` | **Unmet.** Revised times need verified eligibility |
| Honest failure and refusal | All manifests | `tests/dashboard/test_data.py` | Evidence tab lists each rejection and reason |

Deferred under the handoff's scope cuts: routing/diversion, ATIS, live weather and the geographic map. None of these is implemented.
