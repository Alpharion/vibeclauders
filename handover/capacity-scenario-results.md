# Capacity scenario input adapter

Delivered `src/flight_risk/capacity_scenario.py`. This supplies explicitly assumed scenario capacity without changing the production estimator, published artifacts or genuine-AAR operational queue validation.

The current weather and capacity publications both contain only 3/6/12-hour forecasts. A contiguous queue beginning at the cutoff cannot be derived by silently filling the unscored hours. `build_capacity_inputs(forecast, *, airport, asof_utc, window_hours)` therefore returns only valid exact-cutoff rows and lists every missing window hour.

`build_constant_capacity_scenario(forecast, *, airport, asof_utc, window_hours, anchor_lead)` provides a separate sensitivity assumption: hold the selected published forecast rate constant over the scenario window. Its `capacity` dataframe retains original model/run/source and feature-availability timestamps; `anchor_target_hour_utc` and `anchor_horizon_hours` retain the true forecast key. `target_hour_utc` spans the assumed scenario hours, rows have `status=scenario_assumption`, and `input_kind=constant_capacity_proxy_assumption`. The result has `status=partial` and `operationally_eligible=false`; it never calls those hourly rates new forecasts or facility AAR. The caller must use hash-verified publication loading.

Both APIs return capacity dataframe, status, missing_inputs, limitations, population and label_kind. The constant scenario additionally returns constant_rate, anchor_lead and anchor_target_hour_utc. Invalid/missing anchors return unavailable with an empty dataframe. Checks cover exact cutoff, duplicate target, matching lead/target, nonfuture model/feature times, train-before-selection, finite nonnegative rates, source/run/model identifiers, supported status and proxy/reporting-carrier labels.

## Verification

`python -m pytest tests/flight_risk/test_capacity_scenario.py -q --basetemp=tmp/capacity-scenario-pytest --tb=short`: 25 passed, exit 0 (local TEMP/TMP used). Tests cover sparse versus complete windows, input immutability, explicit constant assumption and preservation of real anchor, duplicate/missing anchors, bad rate/status/label/population/provenance, future availability and invalid windows. Final rerun after duplicate/horizon validation tightening, with `--basetemp=tmp/capacity-scenario-final`: 25 passed, exit 0, 2.11 seconds.

Real published snapshot at 2025-07-12 20:00 UTC: ATL anchor rates +3/+6/+12 = 80/81/81; DFW = 74/67.4/74 reporting-carrier arrivals/hour. All six constant scenarios returned partial with complete assumed windows and no missing anchors. Strict ATL six-hour adapter correctly reports five missing hourly forecasts. These scenario rates are not new accuracy measurements or operational recommendations.

No commits were made by this worker; coordinator owns integration and release checks.
