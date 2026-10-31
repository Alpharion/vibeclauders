"""Historical replay and live weather for an airport flow planner. Read-only: nothing is transmitted."""
from __future__ import annotations

import os
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from src.dashboard import components, live_screen, replay, theme, views
from src.dashboard.data import SCORED_HORIZONS, Bundle, fingerprint, load_bundle
from src.dashboard.outputs import agreement_pending
from src.dashboard.theme import html
from src.dashboard.views import Snapshot, resolve_airport
from src.shared import AIRPORTS

REPO_ROOT = Path(__file__).resolve().parents[2]
STATUS_LABEL = {"available": "Available", "partial": "Partial", "unavailable": "Unavailable"}
HISTORICAL, LIVE = "Historical replay", "Live weather"
FOOTER = "Demo data: forecast values are placeholders · Decision support · Human review required · No operational commands transmitted · UTC throughout"


@st.cache_data(show_spinner="Validating published artifacts…", max_entries=2)
def cached_bundle(root: str, stamp: str) -> Bundle:
    return load_bundle(Path(root))


def data_root() -> Path:
    return Path(os.environ.get("DASHBOARD_DATA_ROOT", REPO_ROOT))


def airport_name(icao: str) -> str:
    info = AIRPORTS[icao]
    return f"{info['iata']} · {info.get('name', icao)}"


# --- Shell --------------------------------------------------------------------


def header() -> str:
    with st.container(key="app-header", horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
        codes = " / ".join(info["iata"] for info in AIRPORTS.values())
        html(f'<div class="brand">{theme.icon("globe")}<b>Weather &amp; Traffic</b><span>{escape(codes)}</span></div>')
        st.session_state.setdefault("mode", HISTORICAL)
        return st.segmented_control("Mode", [HISTORICAL, LIVE], key="mode", required=True, label_visibility="collapsed")


def choose_cutoff(index: pd.DataFrame, icao: str, horizon: int) -> tuple[pd.DataFrame, pd.DataFrame, str, str]:
    """Settle date and hour before the popover opens, because its label shows them."""
    rows = index[index["airport"] == icao]
    busiest = views.busiest_cutoffs(index, icao, horizon)
    default = busiest["asof_utc"].iloc[0] if len(busiest) else rows["asof_utc"].iloc[0]
    date_key = f"date-{icao}"
    st.session_state.setdefault(date_key, default.strftime("%Y-%m-%d"))
    date = st.session_state[date_key]
    hours = sorted(rows[rows["asof_utc"].dt.strftime("%Y-%m-%d") == date]["asof_utc"].dt.strftime("%H:%M").unique())
    hour_key = f"hour-{icao}-{date}"
    if st.session_state.get(hour_key) not in hours:
        st.session_state[hour_key] = default.strftime("%H:%M") if default.strftime("%Y-%m-%d") == date else hours[0]
    return rows, busiest, date, st.session_state[hour_key]


def controls(bundle: Bundle) -> tuple[Snapshot | None, int]:
    """Airport, cutoff and horizon: the shared state every replay view reads."""
    index = views.replay_index(bundle)
    choices = [icao for icao in AIRPORTS if icao in set(index["airport"])] or list(AIRPORTS)
    st.session_state.setdefault("window", 6)
    st.session_state.setdefault("horizon", SCORED_HORIZONS[0])
    if st.session_state.get("airport") not in choices:
        st.session_state["airport"] = choices[0]
    with st.container(key="toolbar", horizontal=True, vertical_alignment="center", gap="small"):
        icao = st.selectbox("Airport", choices, key="airport", format_func=airport_name, label_visibility="collapsed", width=248)
        airport = resolve_airport(icao)
        rows = index[index["airport"] == icao]
        snapshot = None
        if not rows.empty:
            snapshot = cutoff_control(bundle, index, icao, airport)
        html('<div class="tb-target">Horizon</div>')
        st.segmented_control(
            "Horizon", SCORED_HORIZONS, key="horizon", required=True, format_func=lambda h: f"+{h}h", label_visibility="collapsed",
        )
        if snapshot is not None:
            snapshot = Snapshot(airport, snapshot.asof_utc, st.session_state["horizon"])
            html(f'<div class="tb-target">Target<b>{snapshot.target_hour_utc:%H:%M} UTC</b></div>')
        st.space("stretch")
        html(theme.badge("HISTORICAL REPLAY · PARTIAL COVERAGE", "amber"))
    return snapshot, st.session_state["window"]


def cutoff_control(bundle: Bundle, index: pd.DataFrame, icao: str, airport) -> Snapshot:
    horizon = st.session_state["horizon"]
    rows, busiest, date, hour = choose_cutoff(index, icao, horizon)
    stamp = views.utc(f"{date} {hour}")
    counts = views.scored_counts(index, icao, horizon)
    dates = sorted(rows["asof_utc"].dt.strftime("%Y-%m-%d").unique())
    per_date = counts.groupby(counts.index.strftime("%Y-%m-%d")).sum()
    with st.popover(f"Replay cutoff · {stamp:%d %b %Y · %H:%M} UTC", icon=":material/calendar_month:", key=f"cutoff-{icao}"):
        jump_to(bundle, icao, busiest)
        date = st.selectbox("Date (UTC)", dates, key=f"date-{icao}", format_func=lambda d: f"{d} · {per_date.get(d, 0)} scored")
        on_date = rows[rows["asof_utc"].dt.strftime("%Y-%m-%d") == date]
        hours = sorted(on_date["asof_utc"].dt.strftime("%H:%M").unique())
        hour = st.selectbox(
            "Hour (UTC)", hours, key=f"hour-{icao}-{date}",
            format_func=lambda h: f"{h} · {counts.get(views.utc(f'{date} {h}'), 0)} scored",
        )
        st.number_input("Planning window (hours)", 1, 24, key="window")
    return Snapshot(airport, views.utc(f"{date} {hour}"), horizon)


def jump_to(bundle: Bundle, icao: str, busiest: pd.DataFrame) -> None:
    """Shortcuts, because most cutoffs in this sample score a single flight."""
    targets = {
        f"{row.asof_utc:%Y-%m-%d %H:%M} · {row.predictions:.0f} scored": (row.asof_utc, None)
        for row in busiest.itertuples()
    }
    published = bundle.docs.get("recommendations")
    if published and resolve_airport(str(published.get("airport"))).icao == icao:
        asof = views.utc(published["asof_utc"])
        targets[f"Published decision snapshot · {asof:%Y-%m-%d %H:%M}"] = (asof, published.get("horizon_hours"))

    def apply() -> None:
        choice = st.session_state[f"jump-{icao}"]
        if choice is None:
            return
        asof, window = targets[choice]
        date = asof.strftime("%Y-%m-%d")
        st.session_state[f"date-{icao}"] = date
        st.session_state[f"hour-{icao}-{date}"] = asof.strftime("%H:%M")
        if window:
            st.session_state["window"] = window

    st.selectbox(
        "Jump to", list(targets), index=None, key=f"jump-{icao}", on_change=apply,
        placeholder="Busiest cutoffs and published decision",
    )


# --- Rail ---------------------------------------------------------------------


def watch_card(bundle: Bundle, icao: str, snapshot: Snapshot | None, active: bool) -> dict:
    """One airport at the shared cutoff: observed conditions, then TAF category by lead."""
    info = AIRPORTS[icao]
    card = {"icao": icao, "title": f"{info['iata']} · {info.get('name', icao)}", "active": active}
    outlook = views.airport_outlook(bundle, icao, snapshot.asof_utc) if snapshot else {}
    if not outlook:
        return {**card, "empty": "No weather evidence at this cutoff."}
    row = next(iter(outlook.values()))
    gust = row["obs_wind_gust_kt"]
    wind = views.known_value(row["obs_wind_speed_kt"], " kt")
    if pd.notna(gust) and gust != row["obs_wind_speed_kt"]:
        wind += f", gust {gust:.0f}"
    category = views.flight_category(row["obs_visibility_sm"], row["obs_ceiling_ft_agl"])
    return {
        **card, "category": category, "temperature": views.known_value(row["temperature_c"], "°C"),
        "glyph": "storm" if row["obs_thunderstorm_flag"] == 1 else ("sun" if category == "VFR" else "cloud"),
        "details": [
            f"Wind {wind}",
            f"{views.known_value(row['obs_visibility_sm'], ' SM', 1)} · {views.weather_display('obs_ceiling_ft_agl', row)}",
        ],
        "leads": [
            {
                "lead": lead,
                "category": views.flight_category(outlook[lead]["visibility_sm"], outlook[lead]["ceiling_ft_agl"]) if lead in outlook else "Unknown",
            }
            for lead in SCORED_HORIZONS
        ],
    }


def select_airport() -> None:
    choice = st.session_state["watchlist"].select
    if choice in AIRPORTS:
        st.session_state["airport"] = choice


def rail(bundle: Bundle, snapshot: Snapshot | None, reveal: bool) -> None:
    selected = st.session_state["airport"]
    html(f'<div class="side-line" style="font-size:14px;font-weight:500">Airports ({len(AIRPORTS)})</div>')
    components.watchlist([watch_card(bundle, icao, snapshot, icao == selected) for icao in AIRPORTS], "watchlist", select_airport)
    state = "Outcomes revealed" if reveal else "Outcomes hidden"
    html(
        '<div class="side-title">Replay context</div><div class="side-line">Forecasts issued by cutoff</div>'
        f'<div class="side-line {"cyan" if reveal else ""}">{state}</div>'
    )
    if bundle.table("throughput_forecast") is not None and agreement_pending(bundle):
        st.toggle(
            "Preview held arrivals forecast", False, key="preview-held",
            help="Observed reporting-carrier arrivals, not AAR. Held from presentation until team agreement is recorded.",
        )
    html('<div class="side-line" style="margin-top:4px">Data sources</div>')
    html("".join(theme.status_row(c.status, c.name, STATUS_LABEL[c.status]) for c in bundle.capabilities))


# --- Entry point --------------------------------------------------------------


def replay_mode() -> None:
    root = data_root()
    bundle = cached_bundle(str(root), fingerprint(root))
    snapshot, window = controls(bundle)
    st.session_state.setdefault("reveal", False)
    st.session_state.setdefault("tab", "Weather")
    reveal = st.session_state["reveal"]
    with st.container(key="app-body", horizontal=True, gap=None):
        with st.container(key="rail", width=268):
            rail(bundle, snapshot, reveal)
        with st.container(key="main"):
            preview = bool(st.session_state.get("preview-held"))
            replay.render(bundle, snapshot, window, reveal, preview)
            html(f'<div class="footnote">{FOOTER}</div>')


def main() -> None:
    st.set_page_config(page_title="Weather & Traffic", page_icon="🛬", layout="wide", initial_sidebar_state="collapsed")
    theme.inject()
    if header() == LIVE:
        live_screen.render(HISTORICAL, FOOTER)
    else:
        replay_mode()

# Compatibility for direct panel callers; the application routes through replay.
from src.dashboard.presentation_actions import review_actions_section, arrival_scenario_section

def compare_tab(bundle, snapshot, window, reveal):
    forecasts = replay.outputs.movement_forecasts(bundle, snapshot.airport, snapshot.asof_utc, False)
    return replay.compare_tab(bundle, snapshot, window, reveal, forecasts)
