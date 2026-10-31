"""Learned METAR transition probabilities, isolated from historical replay."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from src.dashboard import live

ARTIFACT = Path(__file__).resolve().parents[2] / 'artifacts/live_weather/model.json'
EVENTS = ['Thunderstorm', 'Visibility <3 SM', 'Ceiling <1000 ft', 'Gusts >=25 kt']


def state(visibility, ceiling, gust, storm, month):
    category = 'low' if visibility < 3 or ceiling < 1000 else 'clear'
    return f'{category}/{int(gust >= 25)}/{int(storm)}/{(month-1)//3}'


def infer(document, station, airport, now):
    if airport not in document['airports']:
        raise ValueError('Model trained only for ATL and DFW.')
    report = live.latest(station)
    if not report or station.get('status') != 'available':
        raise ValueError('Refresh weather: no fresh successful station feed.')
    age = live.observation_age_minutes(report, now)
    if age is None or age < 0 or age > 90:
        raise ValueError('Observation timestamp missing, future-dated or older than 90 minutes.')
    visibility = report.get('visib')
    if visibility is None or report.get('wspd') is None or not report.get('rawOb'):
        raise ValueError('Visibility, wind or raw METAR is missing.')
    visibility = float(str(visibility).rstrip('+'))
    clouds = report.get('clouds')
    if clouds is None:
        raise ValueError('Cloud coverage missing; ceiling cannot be inferred.')
    ceiling = live.ceiling_ft(report)
    ceiling = 30000 if ceiling is None else ceiling
    gust = report.get('wgst') or report['wspd']
    storm = 'TS' in (report.get('wxString') or '')
    key = state(visibility, ceiling, gust, storm, now.month)
    result=[]
    for lead in (3,6,12):
        model=document['models'][f'{airport}/{lead}']
        cell=model['cells'].get(key)
        probabilities=cell['probabilities'] if cell else model['baseline']
        for i,event in enumerate(EVENTS):
            use=model['selected'][i]
            result.append({'Lead':f'+{lead}h','Target UTC':str(now + pd.Timedelta(hours=lead)), 'Condition':event,
                'Probability':probabilities[i] if use=='transition' else model['baseline'][i],
                'Method':use if cell else 'airport baseline (unseen state)'})
    return pd.DataFrame(result)


def render(feed, airport, now):
    with st.container(border=True):
        st.markdown('### Live-input weather prediction · +3h / +6h / +12h')
        if not ARTIFACT.exists():
            st.info('Weather model not published. Run python -m tools.delivery.train_live_weather.')
            return
        document=json.loads(ARTIFACT.read_text())
        try:
            rows=infer(document, feed['stations'].get(airport), airport, now)
        except (ValueError, TypeError, KeyError) as error:
            st.info(str(error)); return
        st.dataframe(rows, hide_index=True, column_config={'Probability':st.column_config.NumberColumn(format='percent')})
        st.caption('Experimental statistical METAR transition model, not a numerical weather model or official TAF. Live observations are inputs; probabilities are learned from historical observations. No illustrative values are substituted. Forecast times are based on refresh time; observation age is at most 90 minutes.')
        with st.expander('Weather model validation'):
            st.write('Fit 2023; choose transition versus climatology by 2024 Brier score; report 2025 as an updated retrospective backtest. Lower Brier is better. No independent live validation or probability calibration is claimed.')
            st.dataframe(pd.DataFrame(document['evaluation']), hide_index=True)
