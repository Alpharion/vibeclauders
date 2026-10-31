"""Live weather mode: current observations only, with its own feed state, never read by replay."""
from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from src.dashboard import components, live, map_view, theme
from src.dashboard.theme import badge, card, card_title, chip, html
from src.shared import AIRPORTS

AUTO_REFRESH = {"Off": None, "5 min": 300, "15 min": 900}
STATUS_LABEL = {"available": "Available", "cached": "Cached", "unavailable": "Unavailable"}
STATUS_TONE = {"available": "green", "cached": "amber", "unavailable": "red"}


def airport_name(icao: str) -> str:
    info = AIRPORTS[icao]
    return f"{info['iata']} · {info.get('name', icao)}"


def stamp_label(value: str | None) -> str:
    return "Not fetched" if value is None else f"{pd.Timestamp(value):%H:%M} UTC"


def refresh(only: list[str] | None = None) -> None:
    with st.spinner("Retrieving current weather…"):
        st.session_state["live_feed"] = live.refresh_feed(st.session_state.get("live_feed"), only)


def return_to_replay(mode: str) -> None:
    st.session_state["mode"] = mode


def select_station() -> None:
    choice = st.session_state["live-watchlist"].select
    if choice in AIRPORTS:
        st.session_state["live-airport"] = choice


def select_station_on_map() -> None:
    choice = st.session_state["live-map"].airport
    if choice in AIRPORTS:
        st.session_state["live-airport"] = choice


def render(replay_mode: str, footer: str) -> None:
    st.session_state.setdefault("live-auto", "Off")
    panel(replay_mode, footer, AUTO_REFRESH[st.session_state["live-auto"]])


def panel(replay_mode: str, footer: str, interval: int | None) -> None:
    @st.fragment(run_every=interval)
    def body() -> None:
        feed = st.session_state.get("live_feed")
        due = interval and feed and (pd.Timestamp.now(tz="UTC") - pd.Timestamp(feed["retrieved_at_utc"])).total_seconds() >= interval
        if due:
            refresh()
        now = pd.Timestamp.now(tz="UTC")
        icao = toolbar(now)
        feed = st.session_state.get("live_feed")
        with st.container(key="app-body", horizontal=True, gap=None):
            with st.container(key="main"):
                with st.container(horizontal=True, vertical_alignment="center"):
                    theme.title(f"{AIRPORTS[icao]['iata']} · Live weather", "Selected airport · current conditions and outlook")
                    st.space("stretch")
                if feed is None:
                    st.info("Nothing is fetched until you ask, so replay and offline demos need no network.")
                else:
                    current_conditions(feed, icao, now)
                    from src.dashboard.live_prediction import render as render_prediction
                    render_prediction(feed, icao, now)
                    with card("live-map"):
                        map_section(feed, icao, now)
                    with st.expander("Source freshness and observation history"):
                        status_column(feed, icao, now)
                        recent_section(feed, icao)
                from src.dashboard.live_flights import render as render_live_flights
                render_live_flights(icao, now)
                html('<div class="footnote">Live inputs · experimental predictions · human review required</div>')

    body()


def toolbar(now: pd.Timestamp) -> str:
    with st.container(key="toolbar", horizontal=True, vertical_alignment="center", gap="small"):
        icao = st.selectbox("Airport", list(AIRPORTS), key="airport", format_func=airport_name, label_visibility="collapsed", width=248)
        feed = st.session_state.get("live_feed")
        stamp = stamp_label(feed["retrieved_at_utc"]) if feed else "Not fetched"
        html(f'<div class="tb-target">Weather snapshot<b>{now:%d %b %Y · %H:%M} UTC</b></div>')
        html(f'<div class="tb-target">Last refresh<b>{stamp}</b></div>')
        st.selectbox("Auto-refresh", list(AUTO_REFRESH), key="live-auto", label_visibility="collapsed", format_func=lambda v: f"Auto-refresh: {v}", width=180)
        st.button("Refresh", key="live-fetch", type="primary", on_click=refresh, width="content")
        st.space("stretch")
        html(badge("LIVE WEATHER · FLIGHT REVIEW", "cyan"))
    return icao


def station_card(feed: dict | None, icao: str, active: bool, now: pd.Timestamp) -> dict:
    info = AIRPORTS[icao]
    base = {"icao": icao, "title": f"{info['iata']} · {info.get('name', icao)}", "active": active}
    station = (feed or {}).get("stations", {}).get(icao)
    message = live.latest(station)
    if message is None:
        status = station["status"] if station else None
        note = {"status": status, "statusLabel": STATUS_LABEL[status]} if status else {}
        return {**base, **note, "empty": "No observation fetched."}
    observed = live.observed_at(message)
    age = live.age_label(live.observation_age_minutes(message, now))
    visibility, ceiling = message.get("visib", "?"), live.ceiling_ft(message)
    return {
        **base, "source": f"METAR {observed:%H:%M} UTC · {age}" if observed is not None else f"METAR · {age}",
        "status": station["status"], "statusLabel": STATUS_LABEL[station["status"]],
        "category": live.category(message), "temperature": "?" if message.get("temp") is None else f"{message['temp']:.0f}°C",
        "glyph": "storm" if "TS" in str(message.get("wxString") or "") else ("sun" if live.category(message) == "VFR" else "cloud"),
        "details": [live.wind_text(message), f"{visibility} SM · {'no ceiling' if ceiling is None else f'{ceiling:,} ft'}"],
    }


def current_conditions(feed: dict, icao: str, now: pd.Timestamp) -> None:
    station = feed["stations"].get(icao)
    message = live.latest(station)
    with card("conditions"):
        if message is None:
            card_title(airport_name(icao), glyph="plane")
            st.info("No current observation returned for this airport.")
            return
        age = live.observation_age_minutes(message, now)
        observed = live.observed_at(message)
        with st.container(horizontal=True, vertical_alignment="center"):
            card_title(str(message.get("name") or airport_name(icao)), glyph="plane")
            st.space("stretch")
            html(badge(f"OBSERVED {observed:%H:%M} UTC · {live.age_label(age).upper()}", "cyan"))
            with st.popover("View raw METAR", key=f"raw-{icao}"):
                st.code(message.get("rawOb", "No raw message"), language=None)
        ceiling = live.ceiling_ft(message)
        pressure = live.pressure_inhg(message)
        items = [
            ("eye", "Visibility", f"{message.get('visib', 'Unknown')} SM"),
            ("cloud", "Ceiling", "None reported" if ceiling is None else f"{ceiling:,} ft AGL"),
            ("wind", "Wind", live.wind_text(message)),
            ("thermo", "Temperature", "Unknown" if message.get("temp") is None else f"{message['temp']:.0f}°C"),
            ("clock", "Pressure", "Unknown" if pressure is None else f"{pressure:.2f} inHg"),
        ]
        cells = "".join(
            f'<div class="item">{theme.icon(glyph)}<div>{escape(label)}<b>{escape(value)}</b></div></div>' for glyph, label, value in items
        )
        html(f'<div class="conditions"><div class="cat-col">{chip(live.category(message))}Flight category</div>{cells}</div>')
        if live.is_stale(message, now):
            theme.notice(f"<b>Stale observation.</b> The latest report is {age:.0f} minutes old.")


def map_section(feed: dict, icao: str, now: pd.Timestamp) -> None:
    radar = feed["radar"] or {"status": "unavailable", "valid_utc": None}
    valid = pd.Timestamp(radar["valid_utc"]) if radar["valid_utc"] else None
    categories = {
        info["iata"]: live.category(live.latest(feed["stations"].get(name)) or {}) for name, info in AIRPORTS.items()
    }
    codes = {info["iata"]: name for name, info in AIRPORTS.items()}
    payload = map_view.live_payload(categories, AIRPORTS[icao]["iata"], valid, codes)
    age = "" if valid is None else f"{(now - valid).total_seconds() / 60:.0f} min old"
    payload.update(
        title="Current weather map", tag=f"OBSERVED LAYER {valid:%H:%M} UTC" if valid is not None else None, age=age,
        height=380, viewKey="live", banner={"text": "", "alert": False},
        flag="" if radar["status"] == "available" else ("Radar layer cached" if valid is not None else "Radar layer unavailable"),
        layerButtons=[], note="NEXRAD composite. Station markers only; no aircraft, routes or forecasts.",
    )
    components.ops_map(payload, "live-map", on_airport_change=select_station_on_map)


def status_column(feed: dict, icao: str, now: pd.Timestamp) -> None:
    station = feed["stations"].get(icao) or {"status": "unavailable"}
    message = live.latest(station)
    with card("station"):
        card_title("Station details", glyph="file")
        observed = live.observed_at(message) if message else None
        html(
            theme.status_row("", "ICAO code", icao)
            + theme.status_row("", "Observation time", "Unknown" if observed is None else f"{observed:%H:%M} UTC")
            + theme.status_row(STATUS_TONE[station["status"]], "Status", STATUS_LABEL[station["status"]])
            + theme.status_row("", "Cached fallback", "In use" if station["status"] == "cached" else "On")
        )
    with card("feeds"):
        card_title("Feed status", glyph="database")
        rows = ""
        for name, info in AIRPORTS.items():
            entry = feed["stations"].get(name) or {"status": "unavailable"}
            report = live.latest(entry)
            when = live.observed_at(report) if report else None
            label = f"{info['iata']} METAR · {STATUS_LABEL[entry['status']]}"
            rows += theme.status_row(STATUS_TONE[entry["status"]], label, "Unknown" if when is None else f"{when:%H:%M} UTC")
        radar = feed["radar"] or {"status": "unavailable", "valid_utc": None}
        valid = "Unknown" if not radar["valid_utc"] else f"{pd.Timestamp(radar['valid_utc']):%H:%M} UTC"
        html(rows + theme.status_row(STATUS_TONE[radar["status"]], f"Radar · {STATUS_LABEL[radar['status']]}", valid))
        failed = live.failed_sources(feed)
        if failed:
            names = ", ".join(AIRPORTS[f]["iata"] if f in AIRPORTS else "Radar" for f in failed)
            details = [feed["stations"][f]["error"] if f in AIRPORTS else feed["radar"]["error"] for f in failed]
            theme.notice(f"<b>{escape(names)} refresh failed.</b> Last cached observation shown where one exists; it keeps its original time.", glyph="warn")
            st.button("Retry source", key="live-retry", on_click=refresh, args=(failed,), width="content")
            with st.expander("Failure details"):
                st.write(details)


def recent_section(feed: dict, icao: str) -> None:
    rows = live.recent_rows(feed["stations"].get(icao))
    with card("recent"):
        card_title(f"Recent observations · {AIRPORTS[icao]['iata']}", glyph="file")
        if not rows:
            st.caption("No reports returned for this station.")
            return
        cells = [
            [escape(r["observed"]), chip(r["category"]), escape(r["visibility"]), escape(r["ceiling"]), escape(r["wind"]), escape(r["temperature"])]
            for r in rows
        ]
        html(theme.table(["Observed UTC", "Category", "Visibility", "Ceiling", "Wind", "Temperature"], cells))
