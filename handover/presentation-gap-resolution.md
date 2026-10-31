# Presentation review gap resolution

Response to `presentation-readiness-review.md`, which reviewed `a075bf6` and noted the later Figma dashboard replacement. This integration merges current main and checks the actual routed frontend rather than relying on old panel implementations. The current release report, not the review's 395-test or earlier integration's 501-test count, establishes runtime verification.

| Review item | Resolution / evidence | Remaining boundary |
|---|---|---|
| P0-1: AAR story and inconsistent RMSE | README and demo consistently identify a model-estimated reporting-carrier capacity proxy. The separate throughput 9.26/15.43 claim is removed from the presentation. Evaluation exposes proxy-target RMSE and its baseline. | Organisers supply no genuine AAR labels; independent facility-AAR RMSE cannot be invented. |
| P0-2: visible recommendations | Compare displays exact-key ranked departure review priorities and explicitly illustrative arrival scenarios, integrated with the rebuilt UI. | Review priorities are not executable flight instructions; operational decisions remain separately gated. |
| P0-3: automation, LLM split, generality | README includes acquisition → estimation → risk training → verification commands. Evaluation surfaces the processing method. Statistical models and fixed review templates use no LLM. Airport-generic tests are linked. | Public acquisition needs a network; the dashboard does not claim to rerun training on page load. Third-airport configurability is not accuracy evidence. |
| P0-4: release and human gates | Combined verification and package rebuild must run on the final merged runtime. Checklist retains explicit human checks. | Browser tiles, an actual under-three-minute rehearsal, submission timestamp and supervisor acceptance require real evidence. |
| P0-5: demo capacity explanation | Script now explains ATL +3h: 80/hour, partial, degraded-weather fallback with 476 training hours. | Sparse storms and reporting-carrier scope remain visible limitations. |
| P1-6: accuracy extension | Weather and calibration experiments were executed; both rejected by the fixed q0.90 adoption criterion. Incumbent retained. See `member-1-accuracy-results.md`. | Lower proxy RMSE alone did not justify changing the quantile objective. |
| P1-7: impact | Demo/README express ATL +3h recall 52.2% versus 43.2% at equal alert workload: +9 percentage points, about 21% more severe cases detected. | No delay-minute, fuel, whole-airport or causal-intervention benefit. |
| P1-8: unknown traffic | Current frontend traffic totals must preserve missing coverage as unknown, with regression evidence in the UI follow-up. | Missing is never an observed zero. |
| P1-9: install/dependencies | Pinned observed requirements and explicit install commands remain. Coordinator records any actual fresh-environment check separately. | Neither documentation nor an existing-environment release gate proves fresh installation. |

## Presenter acceptance

Use the current dashboard's Historical replay, ATL, cutoff 12 July 2025 20:00 UTC, +3h, outcomes hidden. Show review priorities and capacity support, then Evaluation's processing and accuracy evidence. Reveal the false alarm only at the relevant script step. Repeat the airport/lead/reveal matrix and check remote map tiles in the real browser. Record the observed result and reviewer in `SUBMISSION-CHECKLIST.md`; this document does not grant supervisor acceptance.

## Documentation verification

Commands were checked against the argument parsers in `src/data_capacity/__main__.py` and `src/flight_risk/__main__.py`. No public downloads, retraining or artifact regeneration were performed by the documentation change. Current code/test verification is owned by the coordinator and recorded in `output/delivery/verification.json`.

## Coordinator fresh-install and browser evidence

On 31 October 2026 an isolated Python 3.14 virtual environment was created at `tmp/presentation-clean-env`, without system site packages. `python -m pip install -r requirements-observed.txt` completed successfully; `python -m pip check` reported no broken requirements. The final extracted-release gate uses this environment.

A real browser loaded the redesigned Historical replay and Evaluation screens. The six-cell capacity-proxy RMSE table, selected support, equal-alert comparison and automation/non-LLM explanation were visible. The initial Overview rendered map imagery and airport/route labels; this is a spot check, not proof of all remote tiles or the full browser matrix. The timed presenter rehearsal, submission and supervisor sign-off remain pending.
