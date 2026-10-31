"""Always-visible flights for the airport and prediction window currently selected."""
import pandas as pd
import streamlit as st
from src.dashboard import views


def render(bundle, snapshot):
    if snapshot is None:
        return
    with st.container(border=True, key="card-flight-watchlist"):
        st.markdown(f"### {snapshot.airport.iata} · Flight watchlist")
        st.caption(f"Cutoff {snapshot.asof_utc:%d %b %H:%M} UTC · +{snapshot.horizon_hours}h · departures {snapshot.target_hour_utc:%d %b %H:%M}–{snapshot.target_hour_utc + pd.Timedelta(hours=1):%H:%M} UTC · sampled flights, not all airport traffic")
        scored = views.risk_rows(bundle, snapshot)
        flights = bundle.table("flights")
        if scored is not None and not scored.empty:
            rows = scored.copy()
            rows["Review status"] = views.flagged(rows).map({True: "HIGH RISK · review", False: "Below review threshold"})
            rows = rows.sort_values("probability_severe_delay", ascending=False)
        elif flights is not None:
            rows = views.scored_flights(flights, snapshot).copy()
            rows["Review status"] = "Not scored at this cutoff"
        else:
            rows = pd.DataFrame()
        if rows.empty:
            st.info("No sampled departures at this target hour. Change the cutoff using ‘Jump to’ for a populated snapshot. No flights or risk scores are fabricated.")
            return
        if "carrier" in rows and "flight_number" in rows:
            rows["Flight"] = rows["carrier"].fillna("").astype(str) + " " + rows["flight_number"].fillna("").astype(str)
        names = {"dest":"Destination", "scheduled_dep_utc":"Departure UTC", "probability_severe_delay":"Delay >45 min probability", "threshold":"Review threshold", "flight_id":"Flight ID"}
        columns = [c for c in ["Flight", "dest", "scheduled_dep_utc", "Review status", "probability_severe_delay", "threshold", "flight_id"] if c in rows]
        st.dataframe(rows[columns].rename(columns=names), hide_index=True, height=min(300, 40 + 35 * len(rows)), width="stretch", column_config={
            "Delay >45 min probability": st.column_config.NumberColumn(format="percent"),
            "Review threshold": st.column_config.NumberColumn(format="percent"),
        })
        st.caption("Highest published risk first. High risk means probability meets that flight's model threshold; no actual delay outcomes are used here.")
