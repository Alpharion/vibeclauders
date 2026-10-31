"""Live departure board and schedule-only inference; no replay predictions are reused."""
from pathlib import Path
import os
import re

import joblib
import numpy as np
import pandas as pd
import requests
import streamlit as st

from src.shared import AIRPORTS
from src.dashboard import theme
from src.dashboard.flight_watchlist import flight_cards

MODEL = Path(__file__).resolve().parents[2] / 'artifacts/risk/model.joblib'
BASE = 'https://aeroapi.flightaware.com/aeroapi'
MAX_AGE_MINUTES = 15


def utc(value):
    if not value:
        return None
    try:
        stamp = pd.Timestamp(value)
        return stamp.tz_convert('UTC') if stamp.tzinfo else None
    except (ValueError, TypeError):
        return None


def fetch_departures(airport, now, api_key, get=requests.get):
    """One bounded provider request. Never print credentials or response bodies."""
    if airport not in AIRPORTS:
        raise ValueError('Unsupported airport')
    response = get(f'{BASE}/airports/{airport}/flights/scheduled_departures',
        headers={'x-apikey': api_key}, params={'start': now.isoformat(),
        'end': (now + pd.Timedelta(hours=13)).isoformat(), 'max_pages': 3}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get('scheduled_departures'), list):
        raise ValueError('Invalid departure feed')
    return {'airport': airport, 'retrieved_at_utc': now.isoformat(),
            'flights': payload['scheduled_departures'],
            'partial': bool((payload.get('links') or {}).get('next'))}


def prepare(feed, airport, now):
    fetched = utc(feed.get('retrieved_at_utc'))
    if feed.get('airport') != airport or fetched is None or not 0 <= (now-fetched).total_seconds() <= MAX_AGE_MINUTES*60:
        raise ValueError('Departure feed is stale or belongs to another airport. Refresh flights to score.')
    rows = []
    for f in feed['flights']:
        if not isinstance(f, dict) or not isinstance(f.get('origin'), dict) or not isinstance(f.get('destination'), dict):
            continue
        dep, arr = utc(f.get('scheduled_out')), utc(f.get('scheduled_in'))
        origin = (f.get('origin') or {}).get('code_iata')
        dest = (f.get('destination') or {}).get('code_iata')
        if origin != AIRPORTS[airport]['iata'] or f.get('cancelled') or f.get('actual_out') or dep is None:
            continue
        if not now <= dep < now + pd.Timedelta(hours=13):
            continue
        ident = f.get('ident_iata') or ''
        match = re.fullmatch(r'([A-Z0-9]{2})(\d+[A-Z]?)', ident)
        local = dep.tz_convert(AIRPORTS[airport]['timezone'])
        duration = (arr-dep).total_seconds()/60 if arr else np.nan
        # The trained estimator imputes missing distance; never substitute route miles for BTS distance.
        estimated = utc(f.get('estimated_out'))
        rows.append(dict(flight_id=f.get('fa_flight_id') or f'{ident}-{dep.isoformat()}',
            Flight=ident or f.get('ident') or 'Identifier unavailable', origin=origin, dest=dest,
            airport=airport, carrier=match[1] if match else None, scheduled_dep_utc=dep,
            month=local.month, day_of_week=local.dayofweek, local_hour=local.hour+local.minute/60,
            scheduled_duration_min=duration, distance_miles=np.nan,
            provider_delay_min=max(0,(estimated-dep).total_seconds()/60) if estimated else np.nan,
            unscored_reason='' if match and dest and 0 < duration < 1440 else 'Missing airline, destination or scheduled duration'))
    return pd.DataFrame(rows).drop_duplicates('flight_id') if rows else pd.DataFrame()


def score(rows, model_bundle):
    result = rows.copy()
    if result.empty:
        return result
    result['probability_severe_delay'] = np.nan
    result['threshold'] = np.nan
    eligible = result.unscored_reason.eq('')
    model = model_bundle['schedule_model']
    if eligible.any():
        probabilities = model.predict(result.loc[eligible])
        threshold = model.threshold
        # Training calibrates the primary model only; schedule model is primary only without weather model.
        calibrator = model_bundle.get('calibrator') if model_bundle.get('weather_model') is None else None
        if calibrator is not None:
            def logit(x):
                p = np.clip(np.asarray(x), 1e-6, 1-1e-6)
                return np.log(p/(1-p)).reshape(-1,1)
            probabilities = calibrator.predict_proba(logit(probabilities))[:,1]
            threshold = calibrator.predict_proba(logit([threshold]))[0,1]
        if not np.isfinite(probabilities).all() or np.any((probabilities < 0) | (probabilities > 1)) or not 0 <= threshold <= 1:
            raise ValueError('Invalid model probabilities')
        result.loc[eligible, 'probability_severe_delay'] = probabilities
        result.loc[eligible, 'threshold'] = threshold
    result['Review'] = (result.probability_severe_delay >= result.threshold) | (result.provider_delay_min >= 45)
    return result.sort_values(['Review','probability_severe_delay'],ascending=False,na_position='last')


@st.cache_resource
def load_model(modified):
    return joblib.load(MODEL)  # Trusted repository artifact only; never loaded from the feed.


def render(airport, now):
    with st.container(border=True, key='live-flight-risk'):
        theme.card_title(f"{AIRPORTS[airport]['iata']} · Live departure review")
        st.caption('Experimental schedule-only risk · next 13 hours · weather is not a flight-risk input.')
        key = os.environ.get('AEROAPI_KEY')
        if not key:
            st.info('Live departures are not connected. Configure AEROAPI_KEY on the server, then select Refresh flights. No historical flights are shown as live.')
            return
        if st.button('Refresh flights', key='live-flight-refresh'):
            try:
                st.session_state[f'live-flights-{airport}'] = fetch_departures(airport, now, key)
                st.session_state.pop(f'live-flights-error-{airport}', None)
            except (requests.RequestException, ValueError, TypeError):
                st.session_state[f'live-flights-error-{airport}'] = True
        if st.session_state.get(f'live-flights-error-{airport}'):
            st.warning('Flight feed refresh failed. Previous results are withheld; retry Refresh flights.')
            return
        feed = st.session_state.get(f'live-flights-{airport}')
        if feed is None:
            st.info('Select Refresh flights to fetch current departures. Provider usage charges may apply.')
            return
        try:
            rows = prepare(feed, airport, now)
            rows = score(rows, load_model(MODEL.stat().st_mtime_ns))
        except (ValueError, KeyError, TypeError, OSError, ImportError):
            st.warning('Live scoring unavailable: refresh the feed or check the installed model/runtime.')
            return
        st.caption(f"FlightAware · fetched {pd.Timestamp(feed['retrieved_at_utc']):%d %b %H:%M} UTC · {'partial board (page limit)' if feed['partial'] else 'returned departure board'}")
        if rows.empty:
            st.info('No eligible upcoming departures were returned.')
            return
        flagged = rows[rows.Review]
        if not flagged.empty:
            st.warning(f'{len(flagged)} flights require review. Confirm departure readiness, inbound aircraft and current restrictions with operations.')
        else:
            st.info('No returned flights currently meet the review criteria. This does not establish absence of risk.')
        # Provider estimates are separate from the model probability.
        theme.html(flight_cards(rows.head(6)))
        st.dataframe(rows[['Flight','dest','scheduled_dep_utc','probability_severe_delay','provider_delay_min','Review','unscored_reason']].rename(columns={
            'dest':'Destination','scheduled_dep_utc':'Departure UTC','probability_severe_delay':'Model delay >45 min probability',
            'provider_delay_min':'Provider estimated delay (min)','unscored_reason':'Not scored reason'}), hide_index=True,
            column_config={'Model delay >45 min probability':st.column_config.NumberColumn(format='percent')})
        st.caption('Review = model threshold met or provider estimated delay ≥45 min. Distance is unavailable and uses the trained imputer. Live performance is not validated; historical test metrics do not establish live accuracy. Human review required.')
