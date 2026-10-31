# Presentation readiness review: Challenge 5

- Reviewer: Member 1 agent, 31 October 2026.
- Reviewed build: `main` at `a075bf6`, which merges the readiness branch.
- Reference: `Autonomous SG 2026_Airbus Track.pdf`, Challenge 5 and the judging rubric.

> **Scope note.** `main` has since moved to `47e84d2`: Member 3 rebuilt the dashboard to the Figma designs in `a3f3484`. The findings below were checked on `a075bf6`. Re-check the dashboard items (P0-2, P0-5, P1-8) against the new UI before acting on them.

## Verdict

The build is technically sound and verified. On `a075bf6` I re-ran:

| Check | Result |
|---|---|
| `python -m pytest tests -q` | 395 passed (exit 0) |
| `python -m src.flight_risk verify` | exit 0 |
| `python -m tools.delivery.smoke_app` | exit 0 |

Working tree clean. It is **not yet presentation-ready**. The challenge asks for three things the build doesn't fully provide: an AAR accuracy result measured by RMSE, recommendations for controllers shown in the dashboard, and visible automatic data processing. `handover/SUBMISSION-CHECKLIST.md` also still says "not accepted for submission"; browser review, rehearsal and supervisor acceptance are still to do.

## Challenge 5 "Want to see"

| Deliverable | Status | Evidence | Gap |
|---|---|---|---|
| **Multi-source data integration** (weather logs + flight records, joined on time and station) | Met | Weather observations and forecasts (METAR/TAF, IEM) joined to flights by airport and time, using only what was known at the cutoff. NOAA storm logs used for evaluation only. 135,786 weather snapshots. | None |
| **AAR prediction, measured by RMSE** | Partly met | No real AAR data exists (organisers provided none; FAA ASPM needs a login). There's a separately labelled capacity estimate (`artifacts/capacity_estimate/`) and a forecast of actual arrival counts (RMSE 9.26 vs 15.43 baseline). | This is the headline accuracy measure, and we have no RMSE against real AAR. The capacity estimate beats the no-weather version by only 1.5–2% (pinball loss). |
| **Severe-delay (>45 min) risk classification** | Met | 10,604 held-out predictions; precision, recall, PR-AUC and Brier score by airport and lead; a schedule-only comparison; failure cases. ATL +3h: precision 26%, recall 52%. With the same number of alerts, recall is 52% vs 43% for the historical-rate baseline. | Accuracy is modest (PR-AUC 0.25–0.27 against a base rate of 0.13–0.15), and the probabilities aren't calibrated. That has to be framed honestly. |
| **Dashboard: risk scores, historical trends, recommendations for ATC** | Partly met | Risk scores and normalised history are in the app. | **Recommendations aren't in the dashboard.** It only shows "advice unavailable". The controller review brief exists only as a separate file (`output/delivery/CONTROLLER_BRIEF.md`). |
| **Automatic processing of public datasets** | Built, not visible | `python -m src.data_capacity run` downloads and processes everything with no manual steps; a clean run took 16 minutes. | The README never mentions it. Its only commands are verify and launch. |

## Challenge 5 "Want to avoid"

| Pitfall | Status |
|---|---|
| Data leakage across time | Avoided: only data available at the cutoff is used, with tests; held-out data never feeds model fitting |
| Ignoring runway direction | Avoided: crosswind and tailwind are computed against ATL 080 and DFW 180 |
| Fitting to a single airport | Avoided: configurable by airport registry; both pipelines tested with a synthetic third airport. Not yet shown in the README or demo |
| Comparing raw delay minutes across airports | Avoided: normalised history publishes rates with their denominators |

## Recommended follow-ups

### P0: before presenting

1. **Decide how AAR is presented, then make every document match.** The team should agree on one story: real AAR is unmet (with the access evidence), and we show a clearly labelled capacity estimate. There's an inconsistency to fix. `handover/JUDGING-DEMO.md` claims the arrivals forecast's "RMSE 9.26 vs 15.43", but that forecast isn't in the UI and the team never agreed to show it (plan section 7). Either agree and add it to the Evaluation panel (owner: Member 1), or remove the claim (owner: Member 2). The demo script's capacity line also still says "if Member 1's estimate is published"; it is now.
2. **Show recommendations in the dashboard.** This is the clearest remaining product gap. The controller brief's content is defensible: departures above their risk threshold, ranked, with "review weather and inbound-aircraft status". Putting it in an existing panel, labelled as review priorities, meets the requirement without the unsupported metering advice. If the team prefers, a clearly labelled flag when scheduled arrivals exceed the capacity estimate could go alongside it; it must stay out of the queue logic. Owner: Member 1 (the dashboard is in Member 1's paths under the sprint rules). Re-check against the rebuilt UI first.
3. **Fix the README for the rubric.** Owner: Member 2.
   - Add an automatic-processing section: `python -m src.data_capacity run`, then `python -m src.data_capacity estimate-capacity --from-published`, then `python -m src.flight_risk train` / `verify`.
   - Add one line saying no LLM is used, and why: forecasting and classification are statistical tasks. The rubric explicitly scores the LLM/non-LLM split.
   - Point to the airport-generic tests (`tests/data_capacity/test_generic_airport.py`, `tests/flight_risk/test_airports.py`).
4. **Finish the manual gates in `handover/SUBMISSION-CHECKLIST.md`.**
   - Browser check of ATL/DFW × 3/6/12 hours × outcomes hidden/shown, including whether the map tiles load (or say plainly that they need a network).
   - Rerun `python -m tools.delivery.verify_release` and rebuild the package on the final commit; the recorded run was on `ddc7b24`, and the dashboard has changed since.
   - A timed rehearsal under 3 minutes, and supervisor sign-off.
5. **Prepare the capacity talking point for the demo snapshot.** At ATL +3h with the 12 Jul 2025 20:00 UTC cutoff, the estimate is **80.0, "partial"**. The forecast had thunderstorms, and ATL has too few storm hours in training, so the estimate falls back to a broader degraded-weather group (support 476 hours). Rehearse that explanation, or pick a lead that shows a fully supported value (+6h and +12h show 81.0, available).

### P1: should do if time allows

6. **Capacity-estimate accuracy extension** (`handover/member-1-accuracy-15min.md`, branch `codex/member-1-accuracy-handoff`). It would try a better weather signal and an airport-level correction. Only worth it if it clears its own pre-set rule; otherwise keep `5805f89`. The current gain is small, and the winter cases are a known failure.
7. **Frame impact in plain numbers.** For example: "at the same alert budget, the model catches about 21% more severe delays than the historical-rate baseline" (ATL +3h recall 52.2% vs 43.2%). No delay-minute or fuel claims.
8. **Fix the traffic total display.** When coverage is completely unknown, the total should show unknown, not 0. Small, but it's the kind of honesty slip judges notice. Owner: Member 1; re-check in the rebuilt UI.
9. **Test a fresh-environment install.** It hasn't been done yet. Streamlit is also warning that `st.components.v1.html` is deprecated (its stated removal date has already passed); keep the pinned `requirements-observed.txt` so the demo doesn't break.

### P2: mention in the presentation as limits

- No independent AAR validation.
- Flight data is a 0.8% sample, so there are no whole-airport claims.
- No queue or rescheduling without complete demand and backlog data.
- Probabilities aren't calibrated.
- Rare weather types (winter, convective) are thin.

## Against the judging rubric

| Criterion | Assessment |
|---|---|
| Problem realism (20%) | Strong: named flow-planner user and a reactive status quo |
| Technical soundness (25%) | Strong build. Needs the LLM statement (P0-3) and visible automation |
| Honest evaluation (20%) | Strong: baselines, held-out split, failure cases, explicit refusals. Weakened by the inconsistent RMSE claim (P0-1) |
| Trust (20%) | Strong: hashes, cutoff checks, human-review framing |
| Impact (10%) | Moderate: alert quality only. Frame it as in P1-7 |
| Time discipline (5%) | Pending the rehearsal and the actual submission time |

## Owners at a glance

| Item | Owner |
|---|---|
| P0-1 AAR story and arrivals-forecast claim | Whole team decides; then Member 1 (UI) or Member 2 (docs) |
| P0-2 Recommendations in the dashboard | Member 1 |
| P0-3 README: automation, LLM statement, generic-airport evidence | Member 2 |
| P0-4 Manual release gates, rebuild, rehearsal, sign-off | Supervisor / Member 2 |
| P0-5 Demo capacity talking point | Presenter |
| P1-6 Accuracy extension | Member 1 (optional) |
| P1-7 Impact framing | Presenter / Member 2 |
| P1-8 Traffic total display | Member 1 |
| P1-9 Fresh install, dependency pin | Member 2 |
