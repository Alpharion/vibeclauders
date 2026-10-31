"""Always-visible flights for the airport and prediction window currently selected."""
import pandas as pd
import streamlit as st
from html import escape
from src.dashboard import views, theme


def flight_cards(rows):
    cards = []
    for _, row in rows.iterrows():
        probability = row.get("probability_severe_delay")
        threshold = row.get("threshold")
        known = pd.notna(probability)
        tone = "unscored" if not known else "red" if probability >= .5 else "amber" if probability >= .25 else "cyan"
        value = f"{probability:.1%}" if known else "Not scored"
        status = "REVIEW" if known and pd.notna(threshold) and probability >= threshold else "Below threshold" if known and pd.notna(threshold) else "Threshold unavailable"
        name = row.get("Flight", row.get("flight_id", "Unknown flight"))
        departure = row.get("scheduled_dep_utc")
        when = pd.Timestamp(departure).strftime("%d %b %H:%M UTC") if pd.notna(departure) else "Time unavailable"
        threshold_text = f"{threshold:.1%}" if pd.notna(threshold) else "Unknown"
        cards.append(f'<article class="flight-risk-card {tone}"><div class="flight-risk-head"><b>{escape(str(name))}</b><span>{escape(str(row.get("origin", "")))} → {escape(str(row.get("dest", "Unknown")))}</span></div><div class="flight-risk-score"><strong>{value}</strong><span>delay &gt;45 min</span></div><div class="flight-risk-status">{status} · threshold {threshold_text}</div><div class="flight-risk-meta">{when}</div></article>')
    return '<div class="flight-risk-grid">' + ''.join(cards) + '</div>'


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
            rows["Flight"] = rows["carrier"].astype("string").fillna("") + " " + rows["flight_number"].astype("string").fillna("")
        theme.html(flight_cards(rows))
        st.caption("Display colours: cyan <25%, amber 25–<50%, red ≥50%, grey unscored. These visual bands are not calibrated risk categories; REVIEW uses each model's published threshold, even on a cyan card.")
        names = {"dest":"Destination", "scheduled_dep_utc":"Departure UTC", "probability_severe_delay":"Delay >45 min probability", "threshold":"Review threshold", "flight_id":"Flight ID"}
        columns = [c for c in ["Flight", "dest", "scheduled_dep_utc", "Review status", "probability_severe_delay", "threshold", "flight_id"] if c in rows]
        with st.expander("Flight watchlist details"):
            st.dataframe(rows[columns].rename(columns=names), hide_index=True, height=min(300, 40 + 35 * len(rows)), width="stretch", column_config={
                "Delay >45 min probability": st.column_config.NumberColumn(format="percent"),
                "Review threshold": st.column_config.NumberColumn(format="percent"),
            })
        st.caption("Highest published risk first. High risk means probability meets that flight's model threshold; no actual delay outcomes are used here.")
