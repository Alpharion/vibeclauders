"""Human-review prompts grounded in the selected cutoff's published TAF."""
import pandas as pd
import streamlit as st


RULES = (
    ("Thunderstorms", "thunderstorm_flag", lambda x: x == 1, "cond_thunderstorm_flag", lambda x: x == 1,
     "Review convective-weather restrictions and affected arrival/departure banks; coordinate contingency planning with operations."),
    ("Low visibility", "visibility_sm", lambda x: x < 3, "cond_min_visibility_sm", lambda x: x < 3,
     "Review low-visibility procedures and compare scheduled arrival demand with the capacity estimate."),
    ("Low ceiling", "ceiling_ft_agl", lambda x: x < 1000, "cond_min_ceiling_ft_agl", lambda x: x < 1000,
     "Review instrument-approach availability and arrival sequencing with the responsible operations team."),
    ("Strong gusts", "wind_gust_kt", lambda x: x >= 25, "cond_max_gust_kt", lambda x: x >= 25,
     "Review runway-relative winds and aircraft-specific wind limits; confirm runway configuration with operations."),
)


def recommendations(row, cutoff):
    if row is None or pd.isna(row.get("available_at_utc")) or pd.Timestamp(row["available_at_utc"]) > pd.Timestamp(cutoff):
        return [], "No verified weather feature row available at this cutoff."
    items = []
    for name, field, test, conditional_field, conditional_test, action in RULES:
        value, conditional = row.get(field), row.get(conditional_field)
        prevailing = pd.notna(value) and test(value)
        contingent = pd.notna(conditional) and conditional_test(conditional)
        if prevailing or contingent:
            evidence = f"{field} = {value:g}" if prevailing else f"{conditional_field} = {conditional:g}"
            items.append({"Condition": name, "Forecast basis": "Prevailing TAF" if prevailing else "Conditional TAF group",
                          "Evidence": evidence, "Recommended review": action})
    return items, None


def paired_flights(bundle, snapshot):
    from src.dashboard import views
    rows = views.risk_rows(bundle, snapshot)
    if rows is None or rows.empty:
        return pd.DataFrame()
    return rows.loc[views.flagged(rows), ["flight_id", "probability_severe_delay", "threshold", "model_kind"]].copy()


def render_weather_actions(row, snapshot, bundle=None):
    st.markdown("### Weather-condition recommendations")
    st.caption(f"{snapshot.airport.iata} · +{snapshot.horizon_hours}h · cutoff {snapshot.asof_utc:%Y-%m-%d %H:%M} UTC. Rule-based review prompts from published TAF features, not model-generated operational instructions.")
    items, problem = recommendations(row, snapshot.asof_utc)
    if problem:
        st.warning("PLACEHOLDER — not validated against current conditions")
        st.write("Suggested ATC follow-up: obtain the latest METAR/TAF and confirm runway configuration, active restrictions and airline readiness. Review potential arrival-flow constraints only after these inputs are confirmed.")
        st.caption("Needed to validate: weather available at this cutoff, current runway configuration and operational restrictions. This placeholder is not a clearance or a recommendation to reduce capacity.")
    if problem:
        st.info(problem)
    elif items:
        for item in items:
            with st.container(border=True):
                st.markdown(f"**{item['Condition']} — {item['Forecast basis']}**")
                st.write(item["Recommended review"])
                st.caption(item["Evidence"])
    else:
        st.info("No review trigger found in the available TAF fields. Continue monitoring; missing fields and unmodelled hazards do not imply safe conditions.")
    if items and bundle is not None:
        st.markdown("**Paired high-risk departures**")
        flights = paired_flights(bundle, snapshot)
        if flights.empty:
            st.info("No published departure meets its risk threshold at this exact airport, cutoff and target hour; these weather reviews are airport-level only.")
        else:
            flights["Weather reviews"] = "; ".join(item["Condition"] for item in items)
            st.dataframe(flights, hide_index=True, column_config={
                "probability_severe_delay": st.column_config.NumberColumn("Delay >45 min probability", format="percent"),
                "threshold": st.column_config.NumberColumn("Review threshold", format="percent"),
            })
        st.caption("Uses the same published predictions and probability ≥ threshold rule as the selected airport's risk view. Pairing means shared forecast exposure, not a causal explanation of a flight's prediction; schedule-only predictions remain labelled by model kind.")
    st.caption("Review triggers: thunderstorm flag; visibility <3 SM; ceiling <1,000 ft AGL; gusts ≥25 kt. These are screening thresholds, not airport or aircraft operating limits. Conditional groups describe possible conditions, not a probability. Human review is required; no clearance, rescheduling or measured benefit is implied.")
    st.caption("Historical METAR base rates below provide context only and do not trigger these recommendations. Later observations revealed for evaluation are excluded.")
