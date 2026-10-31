# Member 2 verified results and handback

## Completion boundary

The local risk-model, normalized-metric, queue-validation and advisory implementation is complete and tested. Current project capability is **partial**: no verified weather features, genuine AAR, complete demand or cutoff backlog are published yet. Members 1 and 3 remain external workstreams under their own supervisors. This is not a claim that their tasks have started or that Challenge 5 is fully satisfied.

## Published real outputs

- `artifacts/risk/model.joblib`: selected schedule-only histogram gradient-boosting model and historical baseline.
- `artifacts/risk/predictions.parquet`: **10,604** held-out flight/horizon predictions covering **3,537** unique test flights, KATL/KDFW and leads 3/6/12.
- `artifacts/risk/normalized_metrics.parquet`: daily UTC observed delay/cancellation/missingness cohorts with explicit denominators and outcome-reveal flags.
- `artifacts/risk/evaluation.json`: candidate comparison, thresholds, per-airport/horizon metrics, reliability bins, exclusions and an actual failure example.
- `artifacts/risk/manifest.json`: schema, runtime, source hashes, artifact hashes, row counts and capability status.
- `artifacts/risk/recommendations.json`, `queue.parquet`, `decision_manifest.json`: verified unavailable result at KATL / 2025-07-15T12:00:00Z / six-hour window because demand, capacity and initial backlog are missing. Queue is empty with typed columns; no invented benefit or flight action.

The run used 15,947 eligible labels: 6,064 training, 6,346 validation and 3,537 test departures. All 204 cancelled departures were excluded, including seven with nonmissing delay labels. Seven test flight/horizon combinations were excluded because their cutoff preceded selection completion.

## Measured schedule-only test performance

| Airport, 3-hour lead | Test flights | Average precision | Historical baseline AP | Precision | Recall | Brier |
|---|---:|---:|---:|---:|---:|---:|
| KATL | 1,763 | 0.2496 | 0.2081 | 0.319 | 0.285 | 0.1082 |
| KDFW | 1,774 | 0.2276 | 0.1960 | 0.249 | 0.477 | 0.1239 |

Threshold selected on validation only: `0.157434`. AP improves over the historical airport/hour baseline, but this is a weak schedule-only signal with substantial missed severe delays. ATL recall is about 29%, DFW about 48%; this is not operationally validated forecasting. ATL thresholded F1 is lower than its historical baseline despite higher AP. The reports preserve those tradeoffs rather than claiming universal improvement.

Probabilities are **not post-hoc calibrated**; Brier/reliability quantify calibration. Same-flight schedule-only probabilities repeat across leads. Small differences at 12 hours arise from boundary exclusions, not measured weather lead-time skill. No weather, AAR, delay-minute, fuel or causal benefit claims follow from these results.

Failure example in evaluation: flight `bfd0e37ba4944076cf85` at DFW, predicted probability 0.170 above threshold, observed delay 41 minutes (below the >45-minute severe label). Display only when outcomes are revealed. No cause of this error is inferred.

## Verification performed

```powershell
python -m src.flight_risk train
python -m src.flight_risk decide --airport KATL --asof 2025-07-15T12:00:00Z --window-hours 6
python -m src.flight_risk verify
python -m pytest tests/flight_risk -q --basetemp=tmp/pytest-member2-final-01
```

All commands exited 0. **85 tests passed**. Coverage includes leakage under changed test outcomes, original-date/2400 splits, daylight-saving ambiguity, cancelled labels, source/availability/feature validity, queue conservation, stale/mismatched populations, complete hourly windows, capacity target provenance, model selection timing, manifest tampering, generation mismatch, typed unavailable outputs and CLI publication. Test fixtures stay under tests/tmp and are not passed off as real data.

One Windows/joblib warning reports unavailable physical-core discovery and falls back to logical cores; it does not affect command success. Use a fresh workspace `--basetemp` when rerunning; the default temp location is restricted.

The verifier reads hashes and tables without deserializing model code. It checks exact prediction keys, UTC/hour boundaries, lead relationship, probabilities, selection cutoff, model/evaluation run IDs and decision context. A passed integrity check does not change unavailable capability to available.

## Runtime and provenance

Model run: `c5a9e8584a3843b29612df39d8de5f96`; generated `2026-10-31T04:17:39.539119+00:00`.
Decision run: `29aa2c83afca4a70829e72696b07fc0e`.
Python `3.14.6` at `C:\Users\simho\anaconda3\python.exe`.
Libraries: numpy 2.4.6, pandas 3.0.3, scipy 1.18.0, scikit-learn 1.9.0, pyarrow 23.0.1, joblib 1.5.3.

The old root requirements constrain pandas below 3, while the verified runtime uses pandas 3.0.3. Member 3 owns dependency reconciliation and reproducible installation; no claim is made that installing the current requirements reproduces this environment. Serialized model reuse requires compatible versions or retraining.

## Member 1 handback needed

Publish canonical flights and cutoff-safe weather features with `artifact_hashes` in the v2 capacity manifest. The modelling pipeline is implemented for these inputs but real weather performance remains unmeasured. For queue/advice also publish authentic AAR forecasts for contiguous hours, complete arrival demand and known cutoff backlog for the same population. Three isolated scored leads are insufficient for a queue.

## Member 3 handback needed

Use the dedicated handoff and runbook. Fix target-hour selection and available replay keys; verify manifests; integrate normalized history with outcome masking; distinguish schedule/weather models and sample coverage. Run the commands again after Member 1 publishes accepted data and report refreshed results. Do not copy current schedule-only metrics as weather-model performance.

No files in the external members' implementation scopes were changed here. Existing dashboard remains awaiting Member 3 migration to contract v2.
