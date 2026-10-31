"""Visible review priorities and explicitly assumed arrival scenarios."""
import pandas as pd
import streamlit as st
from src.dashboard import views
from src.dashboard.data import Bundle
from src.dashboard.views import Snapshot

def clock(value):
    return pd.Timestamp(value).strftime("%H:%M")

def review_actions_section(bundle: Bundle, snapshot: Snapshot) -> None:
    st.markdown("**Departure review priorities**")
    brief, problem = views.review_priorities(bundle, snapshot)
    if problem:
        st.caption(f"Review priorities unavailable: {problem}")
        return
    st.caption(
        f"{brief['airport']} · cutoff {clock(snapshot.asof_utc)} UTC · +{brief['horizon_hours']}h · "
        f"Risk run {brief['risk_run_id']} · {brief['sampled_flights_scored']} sampled departures scored"
    )
    if brief["status"] == "unavailable":
        st.caption(brief["summary"])
        return
    st.write(brief["summary"] + ".")
    priorities = brief["review_priorities"]
    if priorities:
        st.write(priorities[0]["recommended_review"] + ".")
        table = pd.DataFrame(priorities)[["flight_id", "probability", "threshold", "model_kind"]]
        st.dataframe(table, hide_index=True, column_config={
            "probability": st.column_config.NumberColumn("Delay >45 min probability", format="percent"),
            "threshold": st.column_config.NumberColumn("Alert threshold", format="percent"),
            "model_kind": "Model",
        })
        st.caption("Flagged because published probability meets its validation-selected threshold; highest risk first.")
    st.caption(" ".join(brief["limitations"]))


def arrival_scenario_section(bundle: Bundle, snapshot: Snapshot, window: int) -> None:
    from src.flight_risk.arrival_scenario import build_scenario

    st.markdown("**Illustrative arrival scenario**")
    scenario = build_scenario(
        bundle.table("traffic_hourly"), bundle.table("capacity_estimate"),
        airport=snapshot.airport.icao, asof_utc=snapshot.asof_utc,
        window_hours=window, anchor_lead=snapshot.horizon_hours,
    )
    for limitation in scenario["limitations"]:
        st.caption(limitation)
    if scenario["status"] != "scenario":
        st.caption("Scenario unavailable: " + "; ".join(scenario["missing_inputs"]))
    else:
        st.caption(
            "Scheduled reporting-carrier demand with estimated backlog and constant model-estimated capacity. "
            f"Capacity anchor: +{scenario['anchor_lead']}h, {scenario['anchor_target_hour_utc']}."
        )
        metrics = scenario["metrics"]
        for column, (label, field) in zip(st.columns(3), (
            ("Initial backlog (estimated)", "initial_backlog_flights"),
            ("Peak backlog (scenario)", "peak_backlog_flights"),
            ("End backlog (scenario)", "end_backlog_flights"),
        )):
            column.metric(label, metrics[field])
        st.caption(
            f"{metrics['scheduled_arrivals']} scheduled arrivals in this window; "
            f"constant capacity proxy {metrics['constant_capacity_proxy_per_hour']:.1f} reporting-carrier arrivals/hour."
        )
        st.dataframe(scenario["queue"], hide_index=True)
    st.caption("Illustrative planning scenario; not a metering or rescheduling instruction, or measured operational benefit.")


