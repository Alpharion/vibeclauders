# Candidate B: residual q0.90 calibration — rejected

Starting checkpoint: `3767538` (reviewed Member 1 estimator `5805f89b8ae908b330e1e981536f52ae1725c2ee`). Branch: `codex/member-1-calibration-accuracy`. Ready for review as a reproducible negative experiment. Production code, model, forecasts, frontend, frozen inputs and risk publications are unchanged.

## Frozen protocol and implementation

The runner fixes the existing 2023 frontier, incumbent weather regimes, q=0.90 and airport-specific 2023 75th-percentile scheduled-demand screen. It fits one additive 0.90 residual quantile per airport/lead on January–August 2024 high-demand rows only. Minimum support is 100 distinct airport/target hours within each lead; insufficient/missing cells explicitly use zero correction. Corrected rates are clipped at zero and missing base predictions remain missing. No dependency or broad search was added.

Selection uses September–December 2024, airport-local target dates. Both estimates use identical available/partial, cutoff-safe weather snapshots with nonmissing observed arrivals and the same high-demand screen. The runner records cohort hashes, counts, exclusions, status counts, base backoff and calibration support. Duplicate evaluation keys are rejected. Quantile, screen, windows, support and engineering guardrails were implemented before evaluating the candidate.

The correction metadata records fitted-data end `2024-09-01T05:00:00+00:00` and selection end `2025-01-01T06:00:00+00:00` (latest boundary across both airports). Historical validation predictions are retrospective selection diagnostics, not emitted operational forecasts. No candidate forecast publication was emitted. Any post-selection backtest is restricted to cutoffs at/after selection end.

Required adoption: at least 1% reduction in six-cell macro q0.90 pinball; no more than 2% macro proxy RMSE increase; no more than 5% pinball increase in any cell. These are fixed engineering guardrails, not significance tests.

## Late-2024 validation

| Airport / lead | n = unique hours per lead | calibration n / offset | RMSE before → after | q0.90 pinball before → after | below-frontier share before → after |
|---|---:|---:|---:|---:|---:|
| ATL / 3 | 906 | 1699 / -1.0 | 20.1233 → 19.3414 | 2.4249 → 2.4625 | .8775 → .8620 |
| ATL / 6 | 906 | 1699 / -1.0 | 20.1576 → 19.3752 | 2.4354 → 2.4708 | .8775 → .8642 |
| ATL / 12 | 906 | 1699 / -1.0 | 20.1301 → 19.3503 | 2.4248 → 2.4617 | .8764 → .8631 |
| DFW / 3 | 869 | 1706 / -0.8 | 21.6343 → 21.1523 | 3.3770 → 3.4926 | .7664 → .7537 |
| DFW / 6 | 869 | 1706 / 0.0 | 21.5306 → 21.5306 | 3.3867 → 3.3867 | .7641 → .7641 |
| DFW / 12 | 869 | 1706 / 0.0 | 21.4878 → 21.4878 | 3.3932 → 3.3932 | .7629 → .7629 |

Macro pinball: **2.906999 → 2.944592, 1.2932% worse**. Macro RMSE: **20.843971 → 20.372970, 2.2597% better**. Worst cell pinball increase: **3.4240%** (DFW/3). The primary guardrail fails: **reject Candidate B; retain incumbent**. An RMSE gain does not justify changing the frontier target.

Each airport/lead has 2929 total validation snapshots; 2023 ATL and 2060 DFW snapshots per lead are excluded by the fixed eligibility definition, primarily the high-demand screen. These counts are not unavailable-prediction counts; machine evidence records those separately. Leads repeat target hours and must not be counted as independent observations.

All six calibration cells met support; there was no calibration fallback on scored rows. Machine evidence includes training-airport q0.90 baseline metrics and per-regime before/after metrics, support, coverage, and base backoff counts. ATL convective and all winter scored cohorts have zero support. DFW convective n is 31/30/26 across 3/6/12 hours; ATL wind n is 33/27/29. These sparse cohorts cannot establish reliable severe-weather skill.

Failure example: DFW/3 IFR (n=34), pinball **3.5206 → 3.6759**, coverage **.7353 → .7059**, despite RMSE **19.4928 → 19.0615**. The early-2024 downward residual correction does not transfer to late-2024 coverage.

## Reproduction and checks

Machine evidence: `handover/member-1-calibration-evidence.json`, SHA256 `39d551b65f085da9a11ba3fcdc1efeb42ed1a93e913fffd3001fb11b9c19fb54`. It contains the serialized 2023 base model, six correction cells, input hashes/upstream run, exact protocol, all validation cells and severe cohorts, and locked rejection. No 2025 comparison was run because validation rejected the candidate. Existing 2025 results were previously inspected and are not pristine external validation.

Commands (from this checkout):

```powershell
python -m src.data_capacity.capacity_calibration --output handover/member-1-calibration-evidence.json
# exit 0, rejected; repeated execution produces identical evidence
$env:TEMP = (Resolve-Path tmp).Path
$env:TMP = $env:TEMP
python -m pytest tests/data_capacity/test_capacity_calibration.py tests/data_capacity/test_capacity_estimate.py tests/dashboard/test_capacity_estimate.py -q --basetemp tmp/calibration-pytest-final
# exit 0, 33 passed
```

Initial test attempt exited 1: one exact floating-point equality in the new test was corrected to `np.isclose`, and pytest could not create its default sandbox temporary directory. A second attempt exited 1 because the explicit `tmp` parent did not yet exist. Creating checkout-local `tmp` and setting TEMP/TMP resolved the environment issue; the subsequent two focused runs passed. No product behavior was changed to accommodate tests.

Tests cover serialized reproduction; Jan–Aug-only fitting under late-2024/2025-label perturbations; future/missing/unavailable weather exclusion; high-demand eligibility; unique support and identity fallback; missing prediction preservation; identical evaluation hours; temporal metadata; and each adoption guardrail. Existing estimator/dashboard publication checks also pass. The coordinator owns combined full-suite/release verification; no redundant full-suite run or real-app smoke was needed for this experiment-only branch.

Incumbent publication remains run `m1-capest-20261031T072310Z-a27968`, manifest SHA256 `c0d6d26ba4f3f6c216e07a302a4826d868a6893e889c508cff342a9013e9c363`. The experiment reads hash-verified capacity inputs and writes only its evidence. Reporting-carrier capacity remains a proxy, facility `aar_observed` remains null, uncertainty intervals remain unavailable, and no queue activation or operational savings claim is made.
