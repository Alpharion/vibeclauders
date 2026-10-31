"""Isolated presentation examples; never passed to prediction or evaluation code."""
import pandas as pd
import streamlit as st
from src.dashboard import views


def movement_value(row, scheduled, direction):
    if row is not None:
        return float(row.forecast)
    return float(scheduled) if pd.notna(scheduled) else float(40 if direction == "arrival" else 45)


def render_examples(page, bundle, snapshot):
    st.markdown("#### Illustrative numerical examples")
    st.caption("PLACEHOLDERS ONLY — constructed demonstration values, not observations, fitted predictions, operational limits or measured performance. These examples never enter recommendations, exports or evaluation calculations.")
    if page in ("Overview", "Traffic"):
        st.dataframe(pd.DataFrame([
            {"Example field": "Incoming movements", "Value": "40 flights/hour"},
            {"Example field": "Outgoing movements", "Value": "45 flights/hour"},
            {"Example field": "Combined movements", "Value": "85 flights/hour"},
            {"Example field": "Capacity illustration", "Value": "50 arrivals/hour"},
            {"Example field": "Illustrative range (not a confidence interval)", "Value": "40–60 arrivals/hour"},
        ]), hide_index=True)
    elif page == "Compare":
        st.dataframe(pd.DataFrame([
            {"Example": "Arrival volume", "Illustrative prediction": 40, "Illustrative outcome": 43, "Difference": 3},
            {"Example": "Departure volume", "Illustrative prediction": 45, "Illustrative outcome": 42, "Difference": -3},
            {"Example": "Total volume", "Illustrative prediction": 85, "Illustrative outcome": 85, "Difference": 0},
        ]), hide_index=True)
        st.caption("Placeholder follow-up scenario: 55 scheduled arrivals/hour versus an assumed 50/hour capacity creates a 5-flight imbalance after one hour from zero backlog. Ask the flow coordinator to verify the inputs; this is not a metering instruction. A 10-minute review interval is an example workflow setting, not an ATC requirement.")
    elif page == "Weather":
        st.caption("The weather probability cards above already contain labelled fixed examples when the probability model is missing. Published TAF and METAR measurements remain separate.")
    else:
        st.write("Worked example only: predictions [40, 45, 50] versus fictional outcomes [42, 43, 51] give RMSE √((4 + 4 + 1)/3) = **1.73 flights/hour**. This is not our model's score.")
        st.caption("Genuine AAR RMSE and validated capacity uncertainty remain unavailable. Use the published proxy and arrival-forecast metrics above for judging.")
