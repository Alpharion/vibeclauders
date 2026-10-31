# Three-minute Challenge 5 demonstration

This guide is the current presentation plan. Earlier plans are historical where they require organiser AAR labels or describe already-published artifacts as absent. The organisers provide no genuine AAR labels; the capacity deliverable is a separately labelled model estimate with explicit assumptions and proxy validation. Member 1 owns that estimator and all frontend changes.

## Rehearse before submission

1. Run `python -m tools.delivery.verify_release` on the combined tree. A nonzero exit blocks the live demo. `--baseline` permits an absent estimator for independent testing, but still fails on any test/app error.
2. Launch `python -m streamlit run app.py`. Check both airports, all leads, reveal masking and browser map tiles. The automatic smoke does not prove that remote tiles load.
3. Generate the separate review brief: `python -m tools.delivery.controller_brief --airport KATL --asof 2025-07-12T20:00:00Z --lead 3`. Open `output/delivery/CONTROLLER_BRIEF.md`. It is a companion artifact, not a new dashboard panel or a queue instruction.
4. Use Historical replay, ATL, +3h, cutoff 12 July 2025 at 20:00 UTC, with outcomes hidden. Verify these values on screen; changing the lead can change available cutoff choices.
5. Record the combined commit, package receipt/hash, submission timestamp and timed rehearsal duration in `SUBMISSION-CHECKLIST.md`. Do not invent submission or supervisor sign-off.

## Timed script

| Time | Show | Say |
|---|---|---|
| 0:00-0:20 | Overview, airport/cutoff/lead | "Our user is an airport flow planner. Today they react as weather disrupts capacity. This replay provides advance risk evidence so they can prioritize review three, six or twelve hours ahead." |
| 0:20-0:50 | Weather and runway-relative wind | "We join flights with weather available at the cutoff. ATL uses the challenge's 080-degree heading; DFW uses 180. Crosswind and tailwind matter, not just raw wind speed. NOAA storm records are retrospective evaluation evidence." |
| 0:50-1:20 | Traffic risk plus companion brief | "At this exact cutoff, two sampled ATL departures cross their validation-selected thresholds: about 61% and 37% risk of a delay over 45 minutes. The suggested next step is to review weather and airline/inbound-aircraft status. These are review priorities, not revised flight times or metering instructions." |
| 1:20-1:45 | Existing Arrival capacity panel | If Member 1's estimate is published and checked: explain the displayed number, horizon, reporting-carrier scope, support and proxy assumption. Otherwise say: "The capacity estimator is not delivered in this build; this is an incomplete part of Challenge 5." Never substitute throughput RMSE for capacity RMSE. |
| 1:45-2:15 | Evaluation and normalized history | "We train on 2023, select on 2024 and test on January-July 2025. At ATL +3h, precision is 26.1% and recall 52.2%. At equal alert workload, recall is 43.2% for the historical-rate baseline. This measures better prioritization, not saved delay minutes or fuel." |
| 2:15-2:40 | Reveal outcomes, failure case | "The 61.2% alert is a false alarm: this departure was delayed 21 minutes, below our severe-delay definition. The forecast indicated thunderstorm risk, but a high probability does not guarantee disruption. The user can see uncertainty and check the evidence." |
| 2:40-3:00 | Evidence and Compare refusal | "Every result has a run and source hashes. We withhold operational advice without complete demand, backlog and validated capacity inputs. The human remains responsible. Our demonstrated benefit is improved alert quality; operational benefits need a separate simulation." |

Scenario flight IDs: `460f3042c18b22443112` (false alarm, 0.612027) and `a6e1ef65ebf371bd00f0` (0.369712). Risk run: `0949771a54bb4e49b4e215528eb5d46b`. Check the regenerated brief before presenting if the producer is republished. Do not disclose outcomes before the reveal step.

## Claims and boundaries

| Claim | Evidence | Boundary |
|---|---|---|
| Delay probabilities and weather benefit | `artifacts/risk/evaluation.json`, matched cohorts | Modest precision; no calibrated probability guarantee |
| Better alert prioritization | `impact.comparisons` in risk evaluation | Same alert workload; sampled departures; no intervention tested |
| Reporting-carrier arrivals forecast | `artifacts/capacity/throughput_evaluation.json` | RMSE 9.26 vs baseline 15.43; not facility capacity accuracy |
| Capacity estimate | Member 1's optional `capacity_estimate` publication | Absent until published; proxy target and assumptions must be visible |
| Controller review suggestion | Hashed exact-key predictions in companion brief | Human review only; no capacity/routing/scheduling decision |
| Reliable delivery | Current `output/delivery/verification.json` | Current failures and manual browser checks still matter |

The challenge asks for controller recommendations, but does not explicitly demand a full rescheduling optimizer. The companion brief is a bounded review aid; it does not complete the missing capacity/recommendation integration in the app. No new UI work is assigned to Member 1 by this guide.

## Rubric coverage

Problem realism 20%: identify the flow planner and current reactive process. Technical soundness 25%: demonstrate a working combined build and leakage/directionality safeguards. Honest evaluation 20%: show baseline, held-out results and the false alarm. Trust 20%: show cutoff, provenance, limitations and refusal. Impact 10%: quantify alert quality only. Time discipline 5%: record actual submission time and finish within three minutes. No predicted judge score is claimed.
