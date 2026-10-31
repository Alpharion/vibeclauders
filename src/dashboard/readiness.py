"""Visible challenge evidence from the currently verified publication bundle."""
import math

import pandas as pd
import streamlit as st

AUTOMATION_COMMANDS = """python -m src.data_capacity run
python -m src.data_capacity estimate-capacity --from-published
python -m src.flight_risk train
python -m src.flight_risk verify"""


def capacity_rmse(document):
    rows = []
    for m in (document or {}).get("metrics", []):
        if m.get("split") == "test" and m.get("metric") == "high_demand_throughput_rmse":
            rows.append({"Airport": m["airport"], "Lead (hours)": m["horizon_hours"],
                         "Eligible hours": m["n"], "Model proxy RMSE": m["value"],
                         "Airport baseline RMSE": m.get("baseline_value")})
    return pd.DataFrame(rows)


def impact_text(document, snapshot):
    if snapshot is None:
        return None
    for row in (document or {}).get("impact", {}).get("comparisons", []):
        if row.get("airport") != snapshot.airport.icao or row.get("horizon_hours") != snapshot.horizon_hours:
            continue
        model, baseline = row.get("model_recall"), row.get("baseline_recall")
        if not all(isinstance(v, (float, int)) and math.isfinite(v) and 0 <= v <= 1 for v in (model, baseline)):
            return None
        gain = f" ({(model / baseline - 1):.1%} relative change)" if baseline > 0 else ""
        return (f"At the same {row['alerts']} alerts, held-out severe-delay recall is {model:.1%} "
                f"versus {baseline:.1%} for the historical-rate baseline{gain}. "
                f"Model precision is {row['model_precision']:.1%}; cohort: {row['n']} sampled departures.")
    return None


def render_readiness(bundle, snapshot=None):
    st.subheader("Model evidence and reproducibility")
    st.markdown("**Capacity accuracy: model estimate, not independently measured facility AAR**")
    st.write("Organisers supplied no genuine AAR labels. We estimate attainable reporting-carrier arrivals from high-demand historical throughput. RMSE below uses that proxy target; it does not establish whole-airport AAR accuracy.")
    document = bundle.docs.get("capacity_estimate_evaluation")
    table = capacity_rmse(document)
    if table.empty:
        st.info("Capacity-proxy RMSE is unavailable in this publication.")
    else:
        st.dataframe(table.round(3), hide_index=True)
        st.caption(f"Capacity run: {document.get('run_id', 'unknown')}. Held-out January–July 2025; units: reporting-carrier arrivals/hour. Repeated leads are not independent hours. Baseline: train-only airport frontier.")
    if snapshot is not None:
        estimates = bundle.table("capacity_estimate")
        selected = snapshot.rows(estimates) if estimates is not None else pd.DataFrame()
        if len(selected) == 1 and selected.iloc[0]["status"] in ("available", "partial"):
            row = selected.iloc[0]
            st.write(f"Selected estimate: {row['aar_pred']:.1f} arrivals/hour; status {row['status']}; support {row['support_n']} training hours; fallback level {row['backoff_level']}.")
            if row['backoff_level'] != 'regime':
                st.caption("The selected weather regime lacks enough training support, so this estimate uses a broader weather group or airport frontier. It is not evidence of strong performance in rare storms or winter weather.")
    st.caption("No uncertainty interval is claimed. The two optional weather/calibration experiments failed their fixed adoption criterion; the incumbent publication is retained.")
    st.markdown("**Impact at equal alert workload**")
    impact = impact_text(bundle.docs.get("risk_evaluation"), snapshot)
    st.write(impact or "No matched airport/lead impact comparison is available for this selection.")
    st.caption("This measures alert quality in the sampled departures, not saved delay minutes, fuel or a tested intervention. Probabilities are not calibrated guarantees.")
    with st.expander("Automatic public-data processing and model design", expanded=True):
        st.write("The pipeline downloads and caches public weather and traffic sources, aligns airport/time keys, builds cutoff-aware features, trains statistical models and publishes hash-verified artifacts. Commands below reproduce processing; opening this panel does not run or refresh them.")
        st.code(AUTOMATION_COMMANDS, language="bash")
        st.write("No LLM is used: hourly forecasting and severe-delay classification are statistical tasks evaluated against held-out numerical targets. Review wording is deterministic and linked to model evidence.")
        st.caption("Airport-generic implementation is tested in tests/data_capacity/test_generic_airport.py and tests/flight_risk/test_airports.py, including a synthetic third airport. This is extensibility evidence, not measured accuracy at an additional airport.")
        st.caption("Downloads require network access; historical flight schedules have replay assumptions. Publication run IDs and hashes identify the loaded data, not live operational freshness.")
