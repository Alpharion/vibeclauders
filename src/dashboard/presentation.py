"""Reference-layout landing view, with observed/forecast evidence kept separate from examples."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from src.dashboard import views, plots, theme


def render(bundle, snapshot, window):
    from src.dashboard import replay
    from src.dashboard.weather_actions import render_priority_actions
    render_priority_actions(bundle, snapshot)
    left, right = st.columns([1.05, 1], gap="medium")
    outlook = views.airport_outlook(bundle, snapshot.airport.icao, snapshot.asof_utc)
    with left, st.container(border=True, key="concept-weather-panel"):
        st.markdown(f"### {snapshot.airport.iata} · Location forecast")
        st.caption(f"Airport-specific outlook · cutoff {snapshot.asof_utc:%d %b %Y %H:%M} UTC")
        if outlook:
            selected = outlook.get(snapshot.horizon_hours)
            if selected is not None:
                category = views.flight_category(selected.visibility_sm, selected.ceiling_ft_agl)
                st.caption(f"Target flight category: {category} · +{snapshot.horizon_hours}h")
                metrics = [
                    ('Visibility', views.weather_display('visibility_sm', selected) + ' SM', 'eye'),
                    ('Ceiling', views.weather_display('ceiling_ft_agl', selected), 'cloud'),
                    ('Wind', views.known_value(selected['wind_speed_kt'], ' kt'), 'wind'),
                ]
                from html import escape
                theme.html('<div class="concept-weather-metrics">' + ''.join(
                    f'<div class="concept-metric">{theme.icon(icon)}<span>{label}</span><strong>{escape(value)}</strong><small>Published TAF · +{snapshot.horizon_hours}h</small></div>'
                    for label, value, icon in metrics) + '</div>')
            records = []
            for lead, row in sorted(outlook.items()):
                records.append({"Lead": f"+{lead}h", "UTC": row.target_hour_utc.strftime('%d %b %H:%M'),
                    "Category": views.flight_category(row.visibility_sm, row.ceiling_ft_agl),
                    "Visibility SM": row.visibility_sm, "Ceiling ft": row.ceiling_ft_agl,
                    "Wind kt": row.wind_speed_kt, "Gust kt": row.wind_gust_kt})
            frame = pd.DataFrame(records)
            chart = go.Figure()
            chart.add_trace(go.Scatter(x=frame.Lead, y=frame['Wind kt'], name='Wind (kt)', mode='lines+markers', line={'color':'#4DA3FF','width':3}))
            chart.add_trace(go.Scatter(x=frame.Lead, y=frame['Gust kt'], name='Gusts (kt)', mode='lines+markers', line={'color':'#A78BFA','width':3}))
            plots._layout(chart, 'Weather outlook · next 12 hours', 'Wind / gusts (kt)', 250)
            chart.update_layout(margin={'l':30,'r':16,'t':45,'b':30}, legend={'orientation':'h','y':1.12,'x':0})
            st.plotly_chart(chart, key='landing-weather-trend', width='stretch', config=plots.CONFIG)
        else:
            st.info("No published TAF for this airport/cutoff. Select a populated historical snapshot.")
    with right, st.container(border=True, key="concept-map-panel"):
        st.markdown("### Geographic outlook")
        st.caption(f"{snapshot.airport.iata} connections · Target {snapshot.target_hour_utc:%d %b %H:%M} UTC")
        replay.map_section(bundle, snapshot, window)
        st.caption("Observed radar · schematic connections · arrows show flight direction.")
