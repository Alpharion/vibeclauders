# Frozen sprint interface and independence rules

This document fixes the sprint boundary before either external agent starts. It refines the earlier plan's label-dependent AAR approach in accordance with the user's clarification. Existing leakage, provenance, outcome masking and honest-evaluation rules remain in force. No mid-sprint cross-agent schema negotiation is required.

## 1. Existing publications are immutable inputs

Base commit: `737b46852c2d4b98e7c01e68ed7e3888f6542c5c`.

- Capacity/data run: `m1-20261031T065014Z-eacdd5`.
- Risk run: `0949771a54bb4e49b4e215528eb5d46b`.
- Existing capacity, traffic, weather, canonical flights, frozen risk inputs and risk outputs retain their bytes/run IDs.
- Do not rewrite the existing capacity manifest to claim a new run while leaving its old row-level run IDs in place.

## 2. Member 1 adds an isolated optional publication

Directory: `artifacts/capacity_estimate/`.

| File | Purpose |
|---|---|
| `manifest.json` | v2 envelope, exact output hashes/counts, input hashes, run/version and scope |
| `forecast.parquet` | Exact-key model estimates for KATL/KDFW at 3/6/12 hours |
| `evaluation.json` | Explicit validation target, splits, cohort counts, proxy metrics and limitations |
| `assumptions.json` | Population, demand-screen rule, model method, quantile, sparse-cell fallback and runway/weather assumptions |
| `model.json` | Reproducible fitted parameters for the small table/frontier estimator; no pickle needed for this sprint |

Manifest: `schema_version='2.0'`, nonempty `run_id`, timezone-aware `generated_at_utc`, `producer`, `status` in available/partial/unavailable, `artifact_hashes` mapping manifest-relative output paths to SHA256, output row counts, `sources` with repository-relative input paths/hashes and upstream run IDs. JSON is LF, finite values or null. Give every JSON payload, including assumptions/model, the same v2 envelope/run ID so the existing document loader can validate it. Hash all four payload files; write the manifest last. Build/validate in a sibling temporary directory before publishing. This new group never replaces genuine capacity or risk publications.

Forecast key: `(airport, asof_utc, target_hour_utc, horizon_hours)`. UTC-aware hourly timestamps, target = cutoff + lead; no duplicate/null keys. Preserve the existing forecast-shaped fields:

`aar_pred`, `aar_lower`, `aar_upper`, `status`, `source`, `source_id`, `label_kind`, `features_available_at_utc`, `model_train_end_utc`, `model_selection_end_utc`, `run_id`, `model_version`, `coverage`, `aar_observed`.

Add these explicit fields:

- `label_kind='model_estimated_capacity'` (never `facility_aar`).
- `population`: the existing BTS reporting-carrier population; no automatic whole-airport scaling.
- `estimation_method`: e.g. `high_demand_weather_frontier_v1`.
- `assumptions_id`: matches the assumptions document.
- `validation_target='high_demand_observed_reporting_carrier_arrivals'`.
- `uncertainty_kind='unavailable'` when bounds are not defensibly estimated; both bounds then null.
- `support_n`: unique airport/target-hour training support within the selected lead/cell/fallback, with its identity recorded; pooled horizons must not inflate independent-hour counts.

`aar_pred` is nonnegative arrivals/hour for the named population. `aar_observed` remains null: no independent facility label exists. `coverage` describes the held-out replay scope, not all airport operations. Partial estimates can be shown with their limitations. Usable rows require non-null feature/training/selection timestamps no later than cutoff and `status` available or partial. Unsupported weather/support gives unavailable rather than fabricated precision.

Evaluation keeps a v2 envelope and has `label_kind`, `validation_target`, `split`, `method`, `assumptions_id`, `metrics`, `limitations`, `missing_inputs`. Metrics include airport, horizon, metric name, value, baseline_value, n and units. Name any RMSE explicitly `high_demand_throughput_rmse`; for a quantile estimator also report pinball loss at the stated quantile. These assess a proxy target, not real facility AAR accuracy. There is no manufactured observed-capacity curve or accuracy claim against self-generated labels.

## 3. Existing frontend binding, owned entirely by Member 1

- Add an optional, independently hashed `capacity_estimate` group to the loader/cache fingerprint.
- Keep existing genuine `facility_aar` rows supported. Prefer a valid genuine row at the selected key; otherwise use a valid estimate at that exact key with the label **Estimated arrival capacity - reporting carriers** and a visible **model proxy** note.
- Reuse the current Arrival capacity card and Evaluation panel. Show estimation method, support/scope and uncertainty state there; do not add tabs, controls or a major new layout.
- Missing or invalid estimate files leave the baseline app functioning with the existing unavailable explanation.
- Never feed estimates into the existing queue as if they had `facility_aar` provenance. Queue and metering refusal remain unchanged.
- Keep genuine AAR evaluation/trends separate. No estimate may populate `aar_observed`. Any held-out actual arrival values in proxy evaluation stay behind outcome reveal.
- Existing observed-arrivals forecasts remain separate and are not renamed or overwritten.

## 4. Member 2's package contract

The package builder includes tracked runtime code/assets and manifest-backed producer directories dynamically, not a fixed risk-only allowlist. Discover `artifacts/**/manifest.json` and decision manifests, include their payloads and required processed inputs, plus frozen input snapshots. Validate referenced paths stay inside the repository; fail clearly on missing declared payloads or mismatched hashes. Do not follow historical absolute source paths outside the repo.

`capacity_estimate` is optional: absence on base main is normal, presence means its entire verified publication is included. Member 2 tests this with a synthetic publication in a temporary copy, without waiting for or modifying Member 1's real output. Neither agent edits this interface during the sprint.

Package metadata records source commit/dirty status, producer runs, payload hash/size and verification scope. Never stamp an uncommitted tree as if the commit alone identified all content. Preserve the committed `requirements-observed.txt`; capture the packaging machine's versions separately if useful.

## 5. Merge model

Two isolated checkouts, same pinned base, disjoint writes. Each branch's own P0 works with the other's unchanged base. The supervisor merges either order and reruns the already completed builder. Ordinary final release verification is unavoidable, but neither agent's implementation or acceptance waits on another agent's new code/artifacts.
