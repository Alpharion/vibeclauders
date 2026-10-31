"""Visible challenge evidence from the currently verified publication bundle."""
import math

import pandas as pd
import streamlit as st

AUTOMATION_COMMANDS = """python -m src.data_capacity run
python -m src.data_capacity estimate-capacity --from-published
python -m src.flight_risk train
python -m src.flight_risk verify"""


def relative_error_reduction(model, baseline):
    """Percent error reduction; undefined for zero or invalid baseline."""
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) and v >= 0 for v in (model, baseline)) or baseline == 0:
        return None
    return 100 * (baseline - model) / baseline


def capacity_rmse(document):
    rows = []
    for m in (document or {}).get("metrics", []):
        if m.get("split") == "test" and m.get("metric") == "high_demand_throughput_rmse":
            rows.append({"Airport": m["airport"], "Lead (hours)": m["horizon_hours"],
                         "Eligible hours": m["n"], "Model proxy RMSE": m["value"],
                         "Airport baseline RMSE": m.get("baseline_value"),
                         "RMSE reduction vs baseline (%)": relative_error_reduction(m["value"], m.get("baseline_value"))})
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



def explain_metrics(bundle, snapshot, table):
    with st.expander("How to interpret RMSE and capacity model accuracy", expanded=True):
        st.latex(r"\mathrm{RMSE}=\sqrt{\frac{1}{n}\sum_{i=1}^{n}(\hat y_i-y_i)^2}")
        st.write("For each eligible hour, subtract observed reporting-carrier arrivals from the predicted frontier, square the error, average across hours, then take the square root. Lower is better; squaring gives large errors extra weight. Units remain arrivals per hour, not percent accuracy or an error bound on each forecast.")
        selected = table
        if snapshot is not None and not table.empty:
            selected = table[(table["Airport"] == snapshot.airport.icao) & (table["Lead (hours)"] == snapshot.horizon_hours)]
        if len(selected) == 1:
            row = selected.iloc[0]
            st.write(f"For {row['Airport']} +{row['Lead (hours)']}h, RMSE {row['Model proxy RMSE']:.3f} means a root-mean-square discrepancy of that many reporting-carrier arrivals/hour over {row['Eligible hours']} high-demand hours. It does not mean {row['Model proxy RMSE']:.3f}% accuracy, or that every hour is within that error.")
            gain = row["RMSE reduction vs baseline (%)"]
            if pd.notna(gain):
                st.write(f"Against baseline RMSE {row['Airport baseline RMSE']:.3f}, relative error reduction is {gain:.2f}%: 100 × (baseline − model) / baseline. A negative value means worse error. This is a comparison on the same proxy cohort, not model accuracy as a percentage.")
        st.write("The capacity model fits a 90th-percentile frontier (q = 0.90), not a mean-arrivals forecast. Training uses 2023 hours whose scheduled arrivals meet the airport's 2023 75th-percentile demand threshold. Weather/airport/lead cells need at least 30 distinct training hours; sparse cells fall back to a broader weather group, then the airport frontier. The airport baseline ignores weather.")
        st.latex(r"L_{0.90}(y,\hat q)=\max(0.90(y-\hat q),-0.10(y-\hat q))")
        st.write("Pinball loss evaluates that upper-quantile objective: underestimating observed throughput by one arrival costs 0.90, overestimating by one costs 0.10. Lower is better. Reducing RMSE alone can move a frontier toward the mean and worsen its intended quantile behavior; this is why optional candidates were required to improve pinball loss as well. A nominal 90th percentile does not guarantee 90% coverage in new weather or a different population.")
        st.caption("High-demand throughput may still be demand-limited or flow-restricted. Neither these metrics nor the assumption that it approximates capacity validates physical facility AAR. Sparse storm/winter cohorts and absent uncertainty intervals remain limitations.")
    with st.expander("How to interpret severe-delay model metrics", expanded=True):
        st.write("The target is departure delay strictly greater than 45 minutes. Precision is true severe-delay alerts / all alerts; recall is alerted severe delays / all severe delays. Precision answers how often alerts are right; recall answers how many severe events are caught. They depend on the alert threshold and must be read together.")
        st.write("PR-AUC here is average precision: a summary of precision and recall across probability thresholds (higher is better). Compare it with the severe-delay prevalence in the same cohort; it is not percent accuracy. Brier score is mean (predicted probability − binary outcome)², between 0 and 1 (lower is better). It measures probability error, not only classification mistakes; a low value alone does not prove calibration when severe events are rare.")
        risk = bundle.docs.get("risk_evaluation") or {}
        if snapshot is not None:
            metrics = [m for m in risk.get("metrics", []) if m.get("split") == "test" and m.get("airport") == snapshot.airport.icao and m.get("horizon_hours") == snapshot.horizon_hours and m.get("metric") in ("precision", "recall", "pr_auc", "brier")]
            if metrics:
                st.dataframe(pd.DataFrame([{"Metric": m["metric"], "Held-out value": m["value"], "Departures": m["n"]} for m in metrics]), hide_index=True)
                first = metrics[0]
                if first.get("n", 0) > 0 and first.get("severe_n") is not None:
                    st.caption(f"Same-cohort severe-delay prevalence: {first['severe_n'] / first['n']:.1%} ({first['severe_n']}/{first['n']}).")
        st.write("Models train on 2023; model choice and F1-maximizing alert thresholds use 2024 validation data. Reported test metrics use January–July 2025. Changing a threshold trades missed events against false alarms; it does not improve the underlying ranking by itself. The equal-alert-workload impact comparison below differs from comparing separately thresholded classifiers.")
        calibration = risk.get("calibration_experiment") or {}
        if calibration.get("status") == "available":
            st.caption(f"Calibration experiment: {calibration.get('method')}. Adopted: {calibration.get('adopted')}. Selection rule: {calibration.get('decision_rule')}.")
        st.caption("Published probabilities are not calibrated guarantees. Results describe sampled departures, not all airport traffic; no intervention benefit or saved delay minutes is established.")


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
    explain_metrics(bundle, snapshot, table)
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

    from src.dashboard.processing_evidence import render_processing_evidence
    render_processing_evidence(bundle)
