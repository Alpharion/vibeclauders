# Team handoff and supervisor guide

> Readiness update (31 October 2026): Member 1 published the chart fix and reporting-carrier capacity proxy at `5805f89b8ae908b330e1e981536f52ae1725c2ee`, run `m1-capest-20261031T072310Z-a27968`, ready for review. Publication is not supervisor acceptance. The current integration branch combines reviewed commits for verification; main merge remains a separate supervisor action. See [readiness review handoff](readiness-review-handoff.md).

> Current work uses the two-member [30-minute handoff](sprint-30min/README.md), [judging demo](JUDGING-DEMO.md) and [submission checklist](SUBMISSION-CHECKLIST.md). Member 1 owns capacity estimation and the frontend; Member 2 owns delivery/readiness. No organiser AAR labels are expected. The original three-member allocation below is historical, not a new assignment or a reason to wait for labels.

## Responsibility split

The original chat is **Member 2**, responsible for flight-risk modelling, arrival queue analysis and evidence-supported recommendations. Two separate agents receive the following handoffs and are monitored by their respective human team members:

| Role | Handoff | Scope |
|---|---|---|
| Member 1 | `handover/agent-1-data-capacity.md` | Public ingestion, canonical data, weather and genuine AAR |
| Member 2 | `handover/agent-2-flight-risk.md` | Risk, normalised metrics, queues and advice; implemented in the original chat |
| Member 3 | `handover/agent-3-dashboard-integration.md` | Shared configuration, dashboard, integration and demonstration |

These files prepare the external handoffs. Their existence does not mean Members 1/3 have started or been accepted. Never fabricate a status for an unstarted agent.

## Start the external agents

Give each agent the same workspace and, in order:

1. `implementation-plan.md` for outcome, scope and priorities.
2. `handover/shared-contract.md` for authoritative schemas and semantics.
3. Its own handoff for ownership, implementation steps and acceptance.
4. This guide for reporting and coordination.

Copy the handoff's **Start prompt** into the agent's chat. The supervising team member identifies themselves and records actual start time. Inspect the current workspace/manifests first; another member may have progressed since these documents were written.

Agents must not silently take over one another's files. If a separate checkout is used, the supervisor explicitly arranges transfer of completed code/artifact bundles to the shared workspace, preserves run IDs and reruns integration checks. A path in a different checkout is not a completed shared handoff.

## Contract and change control

`handover/shared-contract.md` is the source of truth for schema `2.0`. Member 2 owns coordination documents; Member 3 owns shared implementation helpers/configuration. Preserve stable flight IDs.

For an incompatible change, send a concrete request through the supervisor with:

- Old/new path, field or key and one bounded example.
- Reason, affected consumers and compatibility impact.
- Required producer/consumer changes, owner and check command.
- Existing artifact invalidation and proposed schema/run transition.

Continue independent work while changes are coordinated. Do not publish incompatible output under the old version. Supervisors handle sponsor access and external questions; the handoff does not authorise third-party messages.

## Progress reporting

External agents own `handover/status-member-1.json` or `handover/status-member-3.json`. Update after meaningful publication, a checkpoint, blocking discovery, check result or completion. Give a concise supervisor chat update at each checkpoint without repeatedly narrating unchanged state.

This is a **format template**, not real status. Replace every placeholder with evidence before writing a status file. Unknown values remain null.

```json
{
  "member": "1 or 3",
  "schema_version": "2.0",
  "state": "in_progress",
  "started_at_utc": "actual ISO-8601 timestamp",
  "updated_at_utc": "actual ISO-8601 timestamp",
  "elapsed_minutes": null,
  "completed": ["concrete completed work since last report"],
  "artifacts": [{
    "path": "actual published artifact",
    "run_id": "actual run ID or null",
    "status": "available, partial or unavailable",
    "coverage": "actual airports/dates/horizons or null"
  }],
  "commands_tested": ["exact command actually run"],
  "test_results": [{
    "command": "matching tested command",
    "result": "passed, failed or not_run",
    "evidence": "actual result or reason not run"
  }],
  "blockers": [{
    "requirement": "affected requirement",
    "reason": "specific missing prerequisite or failure",
    "evidence": "observed failure",
    "owner": "person/subsystem needed to resolve it",
    "next_action": "specific remedy or decision"
  }],
  "next_steps": ["independent work and next deliverable"],
  "contract_changes_requested": []
}
```

Work `state` is `in_progress`, `blocked`, `ready_for_review` or `complete`, exactly as in the shared contract. Use blocked only if no useful independent work remains; a blocked provider can leave one capability unavailable while the agent continues. Mark complete only after supervisor artifact/command readback; until then use ready_for_review. Work state and artifact status differ: completed code can honestly report unavailable AAR, but that does not meet the challenge's AAR requirement. The optional start time and elapsed-time fields in this template supplement the contract's required keys.

## Supervisor checkpoints

Elapsed times refer to actual team kickoff. The four-hour target is not permission to report incomplete work as complete.

| Checkpoint | Member 1 evidence | Member 3 evidence | Supervisor action |
|---|---|---|---|
| 20 minutes | Real AAR access/overlap result | Identity/schema/config agreement | Resolve access ownership; ask for evidence, not assurances |
| 45 minutes | Canonical flights and real weather slice or precise unavailable causes | Running shell consuming early outputs/empty states | Compare keys, timing and schema across producers/consumer |
| 90-120 minutes | Real AAR result when labels permit; features for Member 2 | Real predictions and evaluation visible | Check metrics, splits and coverage; cut optional scope if needed |
| 180 minutes | Reproducible cached artifacts and checks | Snapshot/recommendation integration checks | Review one ordinary case and one failure/unavailable case |
| 210 minutes | Feature freeze | Feature freeze | Allow defects, validation and demo preparation |
| 240 minutes | Complete handoff evidence | Cached app and three-minute demo | Accept supported work; record unmet requirements explicitly |

The AAR gate must distinguish usable genuine labels with overlapping weather from an unmet requirement. If unavailable, the supervisor may seek a sponsor extract using the agent's exact schema/date request. Arrival counts must not be relabelled capacity to pass this gate.

## Publication and acceptance

Publish complete artifacts atomically and manifests last. Use schema/run/generation metadata, coverage and limitations specified by the contract. Distinguish measurements, forecasts, simulations and unavailable capability. Isolate test fixtures from deliverables.

Before accepting a handoff, verify:

1. Changed paths respect ownership and stable IDs/contracts match.
2. Exact documented commands reproduce outputs from declared inputs/cache.
3. Claimed checks actually ran, with result counts/failures retained. Member 2 now provides `python -m src.flight_risk train`, `decide` and `verify`; see the Member 3 handoff for the exact sequence and `handover/member-2-results.md` once published for measured evidence.
4. Manifests, hashes, coverage, keys, times, units and sources agree. Member 1's `artifact_hashes` keys resolve relative to its manifest directory; every consumed input is declared and every capacity row matches the upstream run. Retain Member 2's immutable input-snapshot provenance when tracing source paths.
5. Missing prerequisites stay explicit; no assumed zero, fabricated result or stale snapshot fills a gap.
6. Member 3 can load the published run and demonstrate success and failure/limitation.
7. Model quality is separate from simulated benefit and human review is clear.

Final handoff must list changed files, commands, output/run IDs, real tests/metrics, a demonstrated failure case, blockers and next owner. “Done” without evidence is insufficient.

## Scope cuts

Preserve genuine AAR evidence, cutoff-safe models, normalised evaluation, historical trends and explicit failure states. Defer routing/diversion, ATIS, extra live-weather work and map refinement. Without complete demand/backlog, retain sample-based risk/history while withholding unsupported whole-airport queue claims. Without AAR, identify partial Challenge 5 coverage and exactly what remains missing.
