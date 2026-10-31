# Live departure review

The Live weather page now has a separate Live departure review panel. No replay rows or illustrative flights are used here.

## Connect the flight feed

1. Obtain a FlightAware AeroAPI account/key with airport scheduled-departure access.
2. Set `AEROAPI_KEY` in the server environment before starting Streamlit. Keep it out of Git, screenshots and frontend configuration.
3. Start the dashboard, select Live weather and ATL or DFW, then click **Refresh flights**.

Official provider endpoint: https://www.flightaware.com/commercial/aeroapi/
`GET /airports/{id}/flights/scheduled_departures` with the `x-apikey` header.
Each explicit refresh requests at most three pages, for the next 13 hours. The panel marks a partial board if the response has another page. Provider usage charges may apply. Weather auto-refresh does not trigger paid flight requests.

## What is scored

The trusted repository artifact `artifacts/risk/model.joblib` supplies the trained schedule-only classifier and its published threshold. Inputs are airport, IATA carrier, destination, local departure month/day/hour and scheduled duration. Distance is not available from this adapter and uses the trained missing-value imputer; provider route distance is deliberately not substituted for the BTS distance feature. The training pipeline's calibration is applied only when the schedule classifier was the calibrated primary model.

Cancelled, already departed, out-of-window, wrong-origin and timezone-ambiguous records are excluded. Missing carrier/destination/duration means unscored, with the reason displayed. Duplicates use the provider flight identifier. A provider-estimated delay of at least 45 minutes independently triggers review, even for an unscored flight. Estimated delays never enter the model features.

The board expires after 15 minutes. Failed refreshes withhold previous scoring until a successful retry. No key means an explicit disconnected state. Flight data is retained in the Streamlit session only.

## Operational limits

This is experimental **schedule-only live inference**, not weather-enhanced flight-risk scoring. The live weather model runs separately. Mapping current TAF forecasts into the flight classifier's training schema and validating that path remain follow-up work. Predictions are not validated on live operations; historical performance is not a claim of live accuracy. Monitor calibration, missing distance and carrier coverage before relying on alerts. No operational instructions are transmitted.

## Verification

Adapter tests cover request bounds, stale/wrong-airport rejection, cancelled/departed/timezone filtering, deduplication, unscored records and separation of provider delay from model probability. A synthetic adapter fixture is also scored using the shipped artifact. It is not real live data or a live-accuracy evaluation. An actual authenticated provider request requires the deployment key and has not been exercised in this workspace.
