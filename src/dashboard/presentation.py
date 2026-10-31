"""Reference-layout landing view, with observed/forecast evidence kept separate from examples."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from src.dashboard import views, plots, theme


def render(bundle, snapshot, window):
    from src.dashboard import replay
    left, right = st.columns([1.05, 1], gap="medium")
    outlook = views.airport_outlook(bundle, snapshot.airport.icao, snapshot.asof_utc)
    with left, st.container(border=True):
        st.markdown(f"### {snapshot.airport.iata} Â· Location forecast")
        st.caption(f"Airport-specific outlook Â· cutoff {snapshot.asof_utc:%d %b %Y %H:%M} UTC")
        if outlook:
            first = next(iter(outlook.values()))
            category = views.flight_category(first['obs_visibility_sm'], first['obs_ceiling_ft_agl'])
            columns = st.columns(3)
            columns[0].metric("Observed category", category)
            columns[1].metric("Visibility (SM)", views.known_value(first['obs_visibility_sm'], digits=1))
            columns[2].metric("Ceiling (ft AGL)", views.weather_display('obs_ceiling_ft_agl', first))
            records = []
            for lead, row in sorted(outlook.items()):
                records.append({"Lead": f"+{lead}h", "UTC": row.target_hour_utc.strftime('%d %b %H:%M'),
                    "Category": views.flight_category(row.visibility_sm, row.ceiling_ft_agl),
                    "Visibility SM": row.visibility_sm, "Ceiling ft": row.ceiling_ft_agl,
                    "Wind kt": row.wind_speed_kt, "Gust kt": row.wind_gust_kt})
            frame = pd.DataFrame(records)
            st.markdown("**Flight category & visibility**")
            st.dataframe(frame.loc[frame.Lead.eq(f'+{snapshot.horizon_hours}h'), ['Lead','UTC','Category','Visibility SM','Ceiling ft','Wind kt','Gust kt']], hide_index=True, width='stretch')
            with st.expander('All horizons · ceiling and wind trends', expanded=False):
                ceiling = go.Figure(go.Bar(x=frame.Lead, y=frame['Ceiling ft'], marker_color='#28C6F4'))
                plots._layout(ceiling, 'Cloud ceiling Â· published TAF', 'ft AGL', 180)
                st.plotly_chart(ceiling, key='landing-ceiling', width='stretch', config=plots.CONFIG)
                wind = go.Figure()
                for field, color in [('Wind kt','#E8EDF2'),('Gust kt','#F75555')]:
                    wind.add_trace(go.Scatter(x=frame.Lead, y=frame[field], name=field, mode='lines+markers', line_color=color))
                plots._layout(wind, 'Wind & gusts Â· published TAF', 'kt', 180)
                st.plotly_chart(wind, key='landing-wind', width='stretch', config=plots.CONFIG)
                st.caption("Published +3/+6/+12h forecast points; intermediate hours are not interpolated. Ceiling encoding 30,000 ft means no ceiling reported.")
        else:
            st.info("No published TAF for this airport/cutoff. Select a populated historical snapshot.")
    with right:
        st.markdown("### Geographic outlook")
        st.caption(f"{snapshot.airport.iata} connections Â· Target {snapshot.target_hour_utc:%d %b %H:%M} UTC")
        replay.map_section(bundle, snapshot, window)
        st.caption("Map uses observed historical radar and schematic sampled connections. It does not show a computed forecast-convection boundary or approved reroute.")
    with st.expander("Illustrative hold / reroute scenario â€” not selected-airport evidence", expanded=False):
        st.markdown("### Impact comparison Â· JFK â†’ ATL Â· hypothetical")
        st.caption("ILLUSTRATIVE SCENARIO â€” NOT LIVE. Fixed reference-design examples; independent of selected airport and model outputs. No operational benefit is established.")
        cols = st.columns(3, gap="medium")
        scenarios = [
            ('1. No adverse weather', 'Baseline example', '16:10Z',0,0,0,0),
            ('2. Weather Â· hold', 'Maintain route Â· illustrative hold', '17:05Z',55,0,300,18),
            ('3. Weather Â· reroute', 'Illustrative alternate path', '16:30Z',20,120,650,6),
        ]
        for col, scenario_key, (title, subtitle, arrival, delay, distance, fuel, connections) in zip(cols, ('baseline', 'hold', 'reroute'), scenarios):
            with col, st.container(border=True, key=f'scenario-{scenario_key}'):
                st.markdown(f"**{title}**")
                st.caption(subtitle)
                st.table(pd.DataFrame({'Field':['Arrival UTC','Added delay','Added distance','Added fuel','Connections at risk'],
                    'Example':[arrival,f'{delay} min',f'{distance} NM',f'{fuel} kg',str(connections)]}).set_index('Field'))
        with st.container(border=True):
            st.markdown('**Reroute vs hold**')
            st.metric('Illustrative earlier arrival', '35 min')
            st.metric('Illustrative extra fuel', '350 kg')
            def open_compare():
                st.session_state['tab'] = 'Compare'
            st.button('Compare scenario', key='landing-compare', on_click=open_compare)
            st.caption('Placeholder arithmetic only; aircraft, route, eligibility and ATC validation are required.')
