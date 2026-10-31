# Visible controller review actions

The existing Compare → Proposed actions panel now shows departure review priorities and an explicitly illustrative arrival scenario before the separately gated operational decision output. No tabs or transmission controls were added. Overview also reports the exact-key review count separately from published operational actions.

## Evidence and boundaries

Review priorities use the existing briefing summarizer on predictions already validated by the dashboard publication loader. Selection is exact airport, cutoff and 3/6/12-hour lead. Prediction run, model/selection times, weather availability, target hour, probability/threshold and flight uniqueness are checked. Failed evidence produces an unavailable message; missing exact keys never reuse another snapshot. Flights crossing their validation-selected thresholds are ranked by descending probability, with an action to review current weather and airline/inbound-aircraft status. No observed delay or cancellation fields enter this display. No flags is explicitly not an airport all-clear.

The illustrative arrival scenario uses the coordinator's `arrival_scenario.build_scenario` with the loaded traffic and estimate tables. Assumptions/limitations appear before initial, peak and end backlog numbers. The constant capacity anchor lead and target hour are shown. This is a schedule-derived reporting-carrier scenario with estimated backlog, not identified aircraft or measured physical backlog. The existing operational queue and recommendation checks are unchanged; metering/rescheduling remains withheld without its verified prerequisites. No saved delay or fuel claim is made.

## Actual verification

- `python -m pytest tests/dashboard/test_review_actions.py -q --basetemp=tmp/review-actions-tests --tb=short`: 12 passed before adding the scenario integration test.
- `python -m pytest tests/dashboard/test_review_actions.py tests/dashboard/test_app.py -q --basetemp=tmp/review-actions-app-tests --tb=short`: 23 passed, including existing full-app selection/reveal/malformed-artifact checks.
- Real-artifact Compare integration test: 1 passed; shows both review priorities and scenario while retaining operational mismatch and reveal gates.
- Final focused run after metric labels and assumptions ordering: `python -m pytest tests/dashboard/test_review_actions.py -q --basetemp=tmp/review-actions-final --tb=short`: **13 passed in 6.17s**, exit 0.
- `git diff --check` for owned runtime/tests: exit 0.

TEMP/TMP pointed to the checkout's `tmp/review-actions-runtime`. The real-artifact tests use ATL, cutoff 2025-07-12 20:00 UTC, +3h, and verify the two flagged flight IDs from the existing risk publication without displaying outcomes. Combined release verification remains the coordinator's gate. Manual browser/map testing is not claimed.

Owned files: `src/dashboard/app.py`, `src/dashboard/views.py`, `tests/dashboard/test_review_actions.py`, this report. No model/publication artifacts changed and no commits were made by this agent.
