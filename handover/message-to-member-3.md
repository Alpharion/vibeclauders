# To Member 3's supervisor (app and delivery, branch `a`)

From Member 2, 31 October 2026.

## Branch `a` reviewed against Member 2 run `28ffd143`: works, one status bug and three display gaps

I checked `origin/a` at `14c0f8d` with current `main` (`ac7e0f9`) merged in locally. The merge was clean; nothing was pushed. I ran the suite and drove `app.py` with Streamlit AppTest on the real artifacts.

### Works as intended

- 236 tests pass. The only 2 failures are Member 1's capacity manifest tests (the CRLF problem in `handover/message-to-member-1.md`).
- The app loads run `28ffd143` with no exceptions, before or after outcomes are revealed.
- **"Against the status quo"** shows all 6 `impact` comparisons.
- **"Storm-event cohorts"** shows all 48 `storm_cohorts` rows. Unavailable cohorts keep null values with `status`/`reason`.
- **Failure cases** stay hidden until outcomes are revealed. After reveal, all three cards appear (Missed `6bffcd9e…`, False alarm `460f3042…`, Declined `c740f6ce…`) with explanation and remedy.
- AAR, the AAR trend and traffic show explicit unavailable states.

### Please fix

1. **Weather risk shows "✅ Available"; Member 2 publishes `partial`.** `src/dashboard/data.py:375` decides this from which prediction kinds exist and ignores `artifacts/risk/manifest.json → capabilities`. The published statuses are:

   ```
   schedule_risk: available, weather_risk: partial, weather_model_evaluation: partial,
   normalized_observed_delays: available, storm_cohort_evaluation: available
   ```

   It's partial because 5 of 10,604 test rows fell back to schedule-only. Contract section 2 defines three states (`available`, `partial`, `unavailable`), and `_capability` only produces two. Suggested fix: read the producer's capability status when the manifest provides one, and add a partial state.
2. **"Schedule risk" will mislabel itself later.** It's available only while some rows are schedule-only (`bool(schedule_kinds)`). If a future run gives every row weather, it will show unavailable even though the schedule model is fitted and published. Reading `capabilities.schedule_risk.status` fixes this as well.

### Suggested display improvements

3. **Show `calibration_experiment` visibly.** It's currently only in the collapsed full report. Plan 2.7 says the result is reported either way. A caption is enough: "Calibration tested on validation data only; not adopted (0.07% Brier gain against a 1% rule). Probabilities are uncalibrated."
4. **`alert_rates`** is an extra key Member 2 added to the contract under the evaluation additions. Its shape is `{airport, horizon_hours, alerts, scored, alert_rate, observed_severe, observed_severe_rate}`. The impact table already shows alert counts, so a small table or caption is optional.
5. **Pivot the storm table** to one row per `(cohort, airport, horizon_hours)` with metrics as columns. The current 48-row long format is hard to read in a three-minute demo.
6. **Optional:** the legacy `failure_case` shows as a fourth card titled "Failure case". It's a different flight, so it isn't a duplicate, but you could label it "Earlier example (missed)" or hide it now that `failure_cases` exists. Member 2 keeps the key for contract compatibility.

### Numbers for the README and demo

All measured on run `28ffd143`. Source: `handover/member-2-results.md`.

- At the same number of alerts, the model's recall beats the historical airport/hour rate by +4 to +12 percentage points in all 6 airport/lead cells.
- In storm windows the model ranks flights better (higher AP in every cell). But at its threshold it doesn't beat the baseline's recall at DFW, and storm cohorts are small (41–90 flights).
- No delay-minute, fuel or savings claims.
