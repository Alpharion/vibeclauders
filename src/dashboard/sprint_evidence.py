"""Display bounded experiment results separately from the published model."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st


def render_sprint_evidence(bundle):
    path = Path(bundle.root) / "handover/full-bts-model-evidence.json"
    if not path.is_file():
        return
    with st.expander("Latest accuracy experiment: cutoff information", expanded=False):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            decision = report["decision"]
            rows = report["validation"]
            if len(rows) != 6:
                raise ValueError("Incomplete airport/lead comparison")
        except (OSError, ValueError, KeyError, TypeError):
            st.info("Experiment evidence is unavailable or incomplete; the published model is unchanged.")
            return
        population = report.get("training_population", "not recorded")
        st.write(f"Training population: {population}. Full-BTS execution status: {report.get('full_bts_status', 'not recorded')}.")
        st.write("The bounded experiments compare expanded training data and, where evaluated, recently completed departure-delay counts/rates plus scheduled target-hour arrivals/departures. Results below describe the recorded candidate only; they do not change the published operational model.")
        st.caption(f"Recent-delay history population: {report.get('feature_history_population', 'not used or not recorded')}. Scheduled counts use BTS reporting carriers where included. Completed gate departures must precede cutoff; immediate observation and reconstructed schedule availability remain replay assumptions.")
        st.write("Selection: September–December 2024, comparing the same six airport/lead cohorts. Both models use the same fixed gradient-boosting family fitted on 2023; alert thresholds use earlier 2024. This is an experiment comparator, not a claim that production metrics changed.")
        st.markdown("**Passed experimental selection; production publication unchanged**" if decision.get("adopt") else "**Rejected: retain the published model**")
        if "macro_ap_relative_gain" in decision:
            st.write(f"Macro average precision change: {decision['macro_ap_relative_gain']:+.2%}; macro Brier change: {decision['macro_brier_relative_regression']:+.2%} (lower Brier is better).")
        st.caption("Pre-set rule: at least 1% relative macro average-precision gain, at most 2% macro Brier regression, and at most 5% average-precision regression in any cell. Six cells are weighted equally.")
        st.dataframe(pd.DataFrame([{
            "Airport": r["airport"], "Lead": r["lead"],
            "Comparator AP": r["incumbent"]["pr_auc"], "Candidate AP": r["candidate"]["pr_auc"],
            "Comparator Brier": r["incumbent"]["brier"], "Candidate Brier": r["candidate"]["brier"],
        } for r in rows]).round(4), hide_index=True)
        st.caption("The 2025 period has previously been inspected. A rejected candidate is not scored again on it. A sample-only result does not establish whether full-BTS training would help; a successful experiment still requires a separately verified production publication.")
