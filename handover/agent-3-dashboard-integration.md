# Member 3 handoff: dashboard, shared configuration and integration

## Start prompt

> You are Member 3. Implement application and integration work described in `implementation-plan.md`, `handover/shared-contract.md` and this handoff, in that order. The shared contract is authoritative for artifact schemas. Member 1 handles public data/capacity in a separate team-supervised chat; Member 2 is implemented in the original chat. Your assigned team member monitors your work. Work only in owned paths, consume published artifacts without changing other members' models, and report integration issues with concrete reproduction evidence. Build a usable app even when a subsystem is unavailable while clearly identifying unmet Challenge 5 requirements.

Workspace: `C:/Users/simho/OneDrive/Documents/ChatGPT/vibeClaude`.

Read `handover/README.md` for reporting and supervisor acceptance. This is a handoff to an external agent, not a claim that the agent or upstream work has already finished.

## Outcome and ownership

Deliver a reproducible local Streamlit dashboard for a named ATC/airport flow-planning user. The core workflow is: choose airport and historical cutoff; inspect weather, AAR and flight risk; review supported advice; reveal outcomes; inspect evaluation and a failure case. No operational action is transmitted.

You own:

- `app.py`, `src/dashboard/`, `src/shared.py`, `.streamlit/`.
- `tests/dashboard/`, `requirements.txt`, root `README.md`.
- `data/reference/`, including shared airport configuration.
- `handover/status-member-3.json` and final integration evidence.

Do not edit `src/data_capacity/`, `src/flight_risk/`, their tests, producer artifacts or raw inputs. Report mismatches to the producer through your supervisor. The original chat owns coordination documents; propose changes rather than silently changing the contract while consumers run.

## Current implementation and known integration gaps

The shell exists in `src/dashboard/app.py`, `data.py` and `plots.py`, launched through root `app.py`. It has historical/live modes, maps, artifact readers and empty states. Treat it as a starting implementation, not a tested finished product. Readers require a v2 compatibility review.

Prioritise these observed gaps:

1. `traffic_view` currently selects movements in `[asof, asof+horizon)`. The scored risk cohort is `[asof+horizon, asof+horizon+1 hour)`. Fix the scored-flight view; keep any cumulative planning window explicitly separate. Otherwise correctly scoped predictions can all disappear at the join.
2. Member 2 publishes held-out test predictions only. Derive replay defaults/choices from actual available snapshot keys, rather than implying every date in the flight sample has model output. Unsupported selections must remain visibly unsupported.
3. The recommendation file is one selected snapshot, not an automatic multi-snapshot index. Validate airport/cutoff/planning-window length before showing `recommendations.json` and `queue.parquet`. Recommendation `horizon_hours` is the planning-window length, distinct from a scored forecast lead. Use `decision_manifest.json` for these artifacts and the separate modelling `manifest.json` for predictions/evaluation. Do not reuse another snapshot; a future index requires a coordinated contract change.
4. File existence is not readiness. Validate manifests, schemas, keys, coverage and ranges before marking data connected.
5. The inspected system Python is `C:/Users/simho/anaconda3/python.exe`, with pandas 3.0.3, numpy 2.4.6, scikit-learn 1.9, scipy 1.18, pyarrow 23 and pytest 9. The current root requirement `pandas<3` conflicts with that runtime. Recheck versions, verify compatibility and reconcile/document requirements; do not blindly reinstall or repeat old version assumptions.

Start from the workspace and record environment/launch results:

```powershell
python -c "import sys, streamlit, pandas, plotly, pyarrow; print(sys.executable); print(streamlit.__version__, pandas.__version__)"
python -m streamlit run app.py
```

The launcher exists; successful startup and UI behavior still need verification. Required check after your suite exists:

```powershell
python -m pytest tests/dashboard -q
```

## Required work

### 1. Freeze shared configuration and consumer interfaces

Within 20 minutes confirm v2 schema and stable identity with Members 1/2 through your supervisor. Preserve `src.shared.flight_key` behavior so regenerated artifacts join. Add a configurable airport registry containing IATA, ICAO, timezone and heading, plus station mapping and optional coordinates when available; retain the existing `AIRPORTS` import compatibility. Demonstrate ATL/KATL and DFW/KDFW through configuration. Unknown metadata must not default to guessed direction or timezone; missing coordinates disable the relevant map layer rather than the core model.

Load only complete published runs. Validate schema version, columns, unique keys, UTC types, finite ranges, source coverage and run metadata. Include manifest/run ID and file changes in cache invalidation. Reject incompatible or partially written artifacts visibly. Distinguish available, partial and unavailable capability with actual missing prerequisites.

Build empty states immediately so integration does not wait on downloads. Test fixtures belong only under tests, labelled synthetic, never in demo artifacts presented as real results.

### 2. Align panels to one snapshot

Use exact `(airport, asof_utc, target_hour_utc, horizon_hours)` contract semantics. For scored views the target hour starts at cutoff plus 3/6/12 hours, and scored flights depart within that hour. A cumulative traffic/planning window is a different view.

- Prefer selectable snapshots with known coverage; never borrow a nearby cutoff/horizon silently.
- Keep weather, capacity, risk, normalised metrics and recommendations aligned.
- Display departure-risk probabilities only for supported departure origins. Do not assign that model's score to an inbound flight from an unsupported origin.
- Distinguish observed, scheduled, predicted and simulated values.
- Show issue/availability/validity time, units, source and model/run identity where useful for assessing evidence.
- Keep optional current weather independent from replay; old flights must not appear live.

### 3. Required views before optional visuals

**Forecast and risk:** Show cutoff-safe weather, runway-relative wind, predicted AAR, uncertainty only when supported, severe-departure-delay probabilities and selected threshold. Missing uncertainty is unknown, not a zero-width interval. Label a schedule-only model explicitly; repeated scores across horizons do not establish weather sensitivity.

**Historical trends:** Add an explicit trend view consuming `artifacts/risk/normalized_metrics.parquet`, whose daily cohorts are UTC periods. Show observed severe-delay rates and delay minutes per eligible flight across dates and ATL/DFW, with definitions, counts and sample coverage. These are historical cohorts, not horizon-keyed prediction rows. Honor `requires_outcome_reveal=True`; display them behind outcome reveal or in a clearly retrospective evaluation view. Without evidence of outcome availability, a period ending before cutoff alone does not make its labels known at that cutoff. Add AAR observed-versus-predicted trends for genuine held-out labels. Any independently verified historical context shown during replay must stop at the cutoff.

**Traffic and capacity:** Show arrivals/departures/total movements separately. Label sampled/complete traffic. A network flight can be two airport movements; do not label their sum unique flights. Apply AAR only to arrival demand. Queue output requires contiguous same-cutoff capacity, complete demand and known initial backlog. Do not fill isolated +3/+6/+12 points or missing demand with zero.

**Decision support:** Consume Member 2 output without inventing actions/benefits. A grounded advisory to review arrival metering can be useful before individual rescheduling is possible; show missing flight eligibility separately. Timing changes require verified eligible flights and must not ground-delay airborne aircraft. Label scenario effects simulated. Moving delay from airborne to ground does not itself prove total-delay reduction. Human review stays explicit and the app sends no operational actions.

**Evaluation and evidence:** Show AAR RMSE in flights/hour against baseline; risk precision/recall/PR-AUC/Brier/reliability/confusion counts; per-airport/horizon samples, splits, missingness and event cohorts where available. Report cancellations separately. Display actual source/contract readiness checks and acquisition failures, not only file presence. Include at least one failure/refusal with a reason.

Routing/diversion, ATIS, additional live-weather work and map refinement follow the core views/checks. Remove obsolete copy that requires routing evidence for every basic advisory.

### 4. Make normalisation and traceability inspectable

Use contracted Member 2 normalised metrics and show denominators. Severe-delay rate uses eligible non-cancelled departures with labels. Observed positive departure-delay minutes per eligible flight uses the declared cohort. Cancellation and missing-label shares need their own denominators. Do not label summed probabilities observed delayed flights or derive minutes from probability.

Keep conventional AAR RMSE; normalised delay comparisons supplement it. Sample statistics must not be presented as whole-airport impact.

Add a requirements/evidence matrix to root `README.md` mapping each Challenge 5 requirement to artifact, command, test/result and unmet limitation. Name the user, current reactive workflow and decision aided. Separate measured prediction quality from estimated operational value.

## Integration checks and acceptance

Own end-to-end verification; producer unit defects remain with their owners. Cover:

- App launch with absent, partial, malformed and valid artifacts.
- Exact airport/cutoff/horizon changes updating all panels without stale cache.
- Duplicate flight/prediction keys, invalid probabilities and incompatible run/schema metadata.
- Future amendments excluded from replay; actual outcome fields hidden in unrevealed tables and downloads.
- Correct schedule-only identification and held-out test coverage.
- Normalised denominators, cancellation exclusion and movement-count reconciliation.
- AAR used only for arrivals; missing intermediate capacity, demand or backlog suppressing unsupported queues/advice.
- Real missing-input reasons, with basic supported advice not gated on optional routing data.
- Read-only recommendations and no automatic operational action.
- Cached/offline demo and reload after a new manifest/run.

Coordinate one recorded end-to-end sequence: Member 1 preparation, Member 2 risk command, aggregate checks, app launch. Member 2's CLI now exists with these commands from the workspace:

```powershell
python -m src.flight_risk train
python -m src.flight_risk decide --airport KATL --asof 2025-07-15T12:00:00Z --window-hours 6
python -m src.flight_risk verify
python -m pytest tests/flight_risk tests/dashboard -q
python -m streamlit run app.py
```

The decision cutoff is a syntax example, not a promise of operational-input coverage. Use an actually supported cutoff for a success case, or retain its truthful unavailable result as a failure demonstration. Queue planning covers `[asof, asof+window_hours)`; this six-hour window is distinct from the +6h scored target hour. The aggregate pytest command requires your dashboard suite to exist. Member 1's preparation command remains its producer's responsibility to implement and report. Read `handover/member-2-results.md` when published for measured results and exact verified commands; do not infer success from these instructions.

Training auto-detects `data/processed/flights.parquet` and `artifacts/capacity/weather_features.parquet`. If present, they must be declared with matching SHA256 values in `artifacts/capacity/manifest.json`, using `schema_version="2.0"`, nonempty `run_id` and `artifact_hashes` keyed relative to that manifest directory (for example `../../data/processed/flights.parquet` and `weather_features.parquet`). If neither is present, training can use the declared sample baseline. Do not bypass verification or treat an invalid present artifact as absent.

The CLI supports `--input-manifest` on train/decide and `--output` on train/decide/verify; inspect each command's `--help` for explicit paths. Decisions verify exact demand/capacity/backlog bytes, and every capacity row must match the upstream manifest's `run_id`. The modelling and decision manifests are independent publications. A successful `verify` means integrity/snapshot checks passed; inspect `model_status`, `decision_status`, evaluation and missing inputs to assess capability completeness.

Training uses immutable verified inputs under `artifacts/risk/input_snapshots/<snapshot-id>/`. Its `provenance.json` links original input paths, upstream run, immutable snapshot paths and hashes. Preserve that lineage in the evidence view; a snapshot cache path is not a new source or proof that data was available at historical cutoff.

Record versions, run IDs and actual results. If a producer is blocked, identify the missing capability and demonstrate honest unavailable behavior.

## Checkpoints and final handoff

Use `handover/status-member-3.json` with the format in `handover/README.md`.

| Elapsed checkpoint | Deliverable |
|---|---|
| 20 minutes | Identity/config agreement; v2 reader plan; producer dependencies |
| 45 minutes | Running shell, validated empty states and early real slice connected when available |
| 90-120 minutes | Real predictions, explicit trends and baseline evaluation visible |
| 180 minutes | End-to-end consistency and supported advice; missing inputs visible |
| 210 minutes | Feature freeze; checks, defects and demonstration only |
| 240 minutes | Cached app, README/evidence matrix, checks and final blocker list |

Prepare a three-minute demo: user/status quo; cutoff/forecast; predictions and baselines; supported advice; one failure/limitation. Only show measured values produced by completed checks. Final handoff lists changed files, exact reproduction/launch commands, tests, compatible producer runs, UI review evidence and unmet requirements. A polished shell alone is not full challenge completion.
