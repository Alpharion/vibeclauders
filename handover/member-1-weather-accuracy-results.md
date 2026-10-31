# Candidate A: bounded weather-regime experiment

Decision: REJECT; retain incumbent production estimator and all published artifacts unchanged. Ready for review as a reproducible negative experiment.

Source checkpoint: `3767538` (reviewed Member 1 implementation `5805f89b8ae908b330e1e981536f52ae1725c2ee`). Branch: `codex/member-1-weather-accuracy`.

## Frozen method and selection

q=0.90 and the airport 2023 75th-percentile scheduled-arrival screen remain fixed. Both frontiers are fitted only on 2023; January–August 2024 is unused. Selection uses airport-local September–December 2024 target dates. One candidate only; no parameter search. Demand thresholds and eligible cohorts are identical for both models. Eligibility requires observed throughput, high scheduled demand, usable status, prevailing TAF coverage and nonfuture available-at timestamps.

Conditional aggregates combine TEMPO/PROB hazards and cannot associate their maximum probability with a particular hazard. Any conditional TS/frozen/IFR or conditional gust >=25 only promotes otherwise VFR to the existing mvfr/degraded risk stratum, never to certain convective/winter weather. This overloaded mvfr name means forecast-risk category in the experiment. Prevailing TS/frozen/IFR retain priority. Gust crosswind >=15 kt and gust-scaled tailwind >=10 kt supplement prevailing wind thresholds. The tailwind scaling uses aggregate maxima and is an approximation across overlapping groups, not an exact directional gust calculation. Unknown wind remains unknown unless known sustained and gust speed are both below 10 kt, bounding both wind thresholds. A missing peak component cannot establish that bound. Fixed runway headings remain ATL 080 / DFW 180. Unknown regime uses existing all-weather backoff.

Rule fixed before scoring: at least 1% reduction in equal-weight six-cell mean pinball loss; no >2% increase in equal-weight mean RMSE; no cell pinball increase >5%. These are engineering guardrails, not significance claims.

Observed ratios candidate/incumbent: macro pinball 1.001794347; macro RMSE 0.994697785; worst cell pinball 1.003595976. Pinball worsens 0.1794%; RMSE improves 0.5302%; primary criterion fails.

## Same-cohort results

B = incumbent; A = candidate. RMSE targets high-demand observed reporting-carrier throughput, not facility AAR. Coverage is empirical observed share at or below frontier. Every row has the same n before/after, each also its unique target-hour count within that lead.

### September–December 2024 selection

|Airport|Lead|n|Pinball B → A|RMSE B → A|Coverage B → A|
|---|---:|---:|---:|---:|---:|
|KATL|3|906|2.424912 → 2.423929|20.123299 → 19.969086|0.8775 → 0.8720|
|KATL|6|906|2.435353 → 2.440397|20.157600 → 19.986751|0.8775 → 0.8731|
|KATL|12|906|2.424834 → 2.433554|20.130123 → 19.945027|0.8764 → 0.8709|
|KDFW|3|869|3.377008 → 3.387238|21.634319 → 21.577178|0.7664 → 0.7664|
|KDFW|6|869|3.386674 → 3.394937|21.530645 → 21.473885|0.7641 → 0.7641|
|KDFW|12|869|3.393211 → 3.393234|21.487840 → 21.448785|0.7629 → 0.7618|

Window snapshots: 17574; common eligible: 5325; distinct airport/target-hour pairs across leads: 1775. Excluded for demand/input criteria: 12249; missing observed: 0; missing/future features: 0; unavailable predictions B/A: 0/0.

### Updated January–July 2025 backtest

|Airport|Lead|n|Pinball B → A|RMSE B → A|Coverage B → A|
|---|---:|---:|---:|---:|---:|
|KATL|3|827|2.052588 → 2.036929|22.666040 → 22.325759|0.9722 → 0.9686|
|KATL|6|827|2.062733 → 2.045345|22.764349 → 22.420705|0.9722 → 0.9698|
|KATL|12|827|2.067110 → 2.032950|22.762668 → 22.131839|0.9710 → 0.9577|
|KDFW|3|1412|2.366898 → 2.366013|22.286786 → 22.183854|0.8697 → 0.8697|
|KDFW|6|1412|2.373626 → 2.373654|22.067795 → 21.980277|0.8654 → 0.8654|
|KDFW|12|1412|2.366997 → 2.365496|21.838222 → 21.793446|0.8640 → 0.8619|

Window snapshots: 30522; common eligible: 6717; distinct airport/target-hour pairs across leads: 2239. Excluded for demand/input criteria: 23805; missing observed: 12; missing/future features: 0; unavailable predictions B/A: 0/0.

2025 was inspected previously by the team. This is an updated held-out backtest, not pristine external validation. Rejection was locked on late-2024 metrics before computing these values, and was not changed by 2025. Deterministic regeneration during report/check completion reproduced the identical decision; no candidate parameters were tuned.

## Support and failure

The accompanying JSON includes every model cell and training support, per-validation-cell minimum selected support, backoff counts, all regime counts and per-regime metrics, severe-weather metrics, and train-only airport quantile baseline comparisons. Training minimum support remains 30 and fallback hierarchy is unchanged. Leads are not pooled as independent target hours.

Prevailing convective/winter validation support is zero at ATL and DFW 31/30/26 at leads 3/6/12. Both models give identical severe-cohort predictions. Such small cohorts cannot establish severe-weather skill. Conditional hazards are represented only as forecast risk; no occurrence probability or uncertainty interval is inferred.

Failure example: {'airport': 'KATL', 'target_hour_utc': '2024-09-03 12:00:00+00:00', 'lead': 12, 'observed': 81.0, 'incumbent': 80.0, 'candidate': 79.0, 'regime_before': 'mvfr', 'regime_after': 'mvfr'}. Even an unchanged regime label can have a changed frontier because conditional risk reallocates training hours into its cell. This illustrates why broader weather classification does not ensure lower quantile loss.

## Reproduction and checks

`python -m src.data_capacity.weather_accuracy` exits 0 and writes the machine-readable report. It verifies committed capacity manifest/input hashes before loading, stores those hashes and source hashes, stores both fitted models, locks validation selection before reporting 2025, and never calls publish or modifies production behavior.

`python -m pytest tests/data_capacity/test_capacity_weather_accuracy.py tests/data_capacity/test_capacity_estimate.py tests/dashboard/test_capacity_estimate.py -q` initially exited 1: 14 passed, 19 fixture setup errors because the sandbox default temporary directory could not be created. No assertion failures.

Rerun with TEMP/TMP pointing to checkout `tmp/weather-test-runtime`, plus `--basetemp=tmp/weather-pytest-accuracy`: exit 0, **33 passed in 11.49s**. The six new tests cover conditional-vs-prevailing semantics, unknown wind bounds, gust directionality/priority, missing/future input exclusion, held-out-label perturbation/model reproduction, and adoption guardrails. After tightening the missing-peak bound to match the documented assumption, the experiment reproduced identical real-data metrics and the six new tests passed again (exit 0, 0.90s).

`python -m src.flight_risk verify`: exit 0, status passed, 10,604 prediction rows, 3,537 unique flights; decision remains unavailable. Full suite is deferred to coordinator as requested; no frontend/publication binding changed, so no additional app smoke was required.

## Limitations and preservation

No facility AAR labels exist. Capacity remains a reporting-carrier throughput proxy; no whole-airport scaling, invented intervals, operational savings, or queue activation. Production source, risk/data/dependencies/shared source and all published artifacts remain unchanged. No 2025 tuning. This branch adds only the reusable experiment, tests, and these two reports. No new publication run exists.

Delivery: local commit complete. Default git push failed resolving GitHub (getaddrinfo thread failed). An elevated push was rejected by automatic approval review because it deemed the GitHub destination/source-and-results payload insufficiently authorized. No workaround attempted; coordinator can integrate the local commit. Explicit approval is required to push this branch/payload to https://github.com/Alpharion/vibeclauders.git.
