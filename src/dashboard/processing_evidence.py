"""Explain the implemented ingestion and evidence chain without triggering downloads."""
import streamlit as st


def render_processing_evidence(bundle):
    with st.expander("How datasets become forecasts", expanded=False):
        st.markdown("""
1. **Acquire distinct populations.** The supplied BTS-derived flight sample supports departure-risk modelling. Monthly BTS On-Time Reporting downloads provide broader reporting-carrier hourly traffic. IEM provides archived METAR observations and TAF forecasts. NOAA storm events annotate retrospective evaluation only.
2. **Validate and cache.** Download helpers record URL, retrieval time, status and SHA-256 hash. Valid caches can be reused; failed downloads do not replace good cached files. `--cache-only` refuses missing or invalid cache entries. Failed months remain missing coverage, not zero movements.
3. **Standardise flights and time.** Airport registry timezones and runway headings resolve local schedules to UTC. Midnight rollover and daylight-saving cases are handled explicitly: repeated fall-back clock times use the first DST occurrence and are flagged; nonexistent local times and unresolvable flight-date matches are excluded and audited. Actual gate/runway times are retrospective outcomes, never future predictors. Scheduled gate counts include cancellations; observed runway counts exclude cancelled movements and diverted destination arrivals.
4. **Build each forecast snapshot.** Join on airport, cutoff, target hour and lead. Select the latest TAF available by cutoff and overlapping the target hour; keep conditional TEMPO/PROB groups separate from prevailing weather. METAR supplies only observations available by cutoff. Availability assumes a 10-minute archive latency; TAF age is capped at 12 hours and METAR age at 2 hours. These are replay assumptions, not verified live ingestion timestamps.
5. **Respect runway and temporal structure.** Wind is transformed relative to ATL 080° and DFW 180°. Train on 2023, select on 2024, and report January–July 2025 held-out results. Future amendments, actual delays and retrospective storm labels cannot enter the prediction inputs. The capacity frontier and severe-delay classifier have separate targets and evaluation reports.
6. **Publish and validate.** Producers write tables and evaluation documents, then publish their manifest last. Consumers check declared hashes, schemas, run identifiers and exact snapshot keys. Missing, stale or inconsistent inputs produce explicit partial/unavailable states. Review actions use the selected published probabilities; arrival scenarios disclose their reconstructed-demand, warmup-backlog and constant-capacity assumptions.
""")
        group = bundle.groups.get("capacity")
        manifest = group.manifest if group else None
        if manifest:
            st.markdown("**Evidence for the loaded publication**")
            st.write(f"Run {manifest.get('run_id', 'unknown')} · status {manifest.get('status', 'unknown')} · published {manifest.get('generated_at_utc', 'unknown')}")
            st.code(manifest.get("command", "Producer command not recorded"), language="bash")
            st.caption("This is the recorded producer command, not a job executed by opening this page. A cache-only run demonstrates processing of cached inputs; it does not prove a fresh download on this visit.")
        else:
            st.info("No verified capacity publication is loaded; processing history cannot be established here.")
        for key, label in (("flights", "Sample flight records"), ("traffic_hourly", "Reporting-carrier traffic rows"), ("weather_features", "Weather snapshot rows"), ("predictions", "Risk prediction rows")):
            table = bundle.table(key)
            st.caption(f"{label}: {len(table):,}" if table is not None else f"{label}: unavailable")
        st.caption("Automatic processing is a command-line pipeline, not a live streaming service or an automatic dashboard retraining trigger. No public downloads or retraining are performed during release verification.")
