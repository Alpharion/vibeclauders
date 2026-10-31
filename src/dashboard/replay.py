"""The five historical replay views. Each reads the shared snapshot; outcomes need an explicit reveal."""
from __future__ import annotations

import json
from html import escape

import pandas as pd
import streamlit as st

from src.dashboard import components, map_view, outputs, plots, theme, views
from src.dashboard.data import SCORED_HORIZONS, Bundle, is_schedule_only
from src.dashboard.outputs import MovementForecasts
from src.dashboard.theme import badge, card, card_title, chip, html, tile
from src.dashboard.views import Snapshot
from src.shared import AIRPORTS

TABS = ("Overview", "Weather", "Traffic", "Compare", "Evaluation")
STATUS_LABEL = {"available": "Available", "partial": "Partial", "unavailable": "Unavailable"}
CHART = {"config": plots.CONFIG}


def fmt_time(value) -> str:
    return "unknown" if pd.isna(value) else pd.Timestamp(value).strftime("%Y-%m-%d %H:%M UTC")


def clock(value) -> str:
    return pd.Timestamp(value).strftime("%H:%M")


def window_label(snapshot: Snapshot) -> str:
    return f"{clock(snapshot.target_hour_utc)}–{clock(snapshot.target_hour_utc + outputs.WINDOW)} UTC"


def unavailable(capability: str, reason: str) -> None:
    st.warning(f"**{capability} unavailable.** {reason}", icon="⛔")


def number(value, digits: int = 0) -> str:
    return "—" if value is None or pd.isna(value) else f"{value:,.{digits}f}"


def render(bundle: Bundle, snapshot: Snapshot | None, window: int, reveal: bool, preview: bool) -> None:
    tabs = st.tabs(list(TABS), key="tab", on_change="rerun")
    if snapshot is None:
        with tabs[0]:
            unavailable("Replay", "No snapshot is published.")
    else:
        forecasts = outputs.movement_forecasts(bundle, snapshot.airport, snapshot.asof_utc, preview)
        if tabs[0].open:
            with tabs[0]:
                overview_tab(bundle, snapshot, window, reveal, forecasts)
        if tabs[1].open:
            with tabs[1]:
                weather_tab(bundle, snapshot)
        if tabs[2].open:
            with tabs[2]:
                traffic_tab(bundle, snapshot, window, reveal, forecasts)
        if tabs[3].open:
            with tabs[3]:
                compare_tab(bundle, snapshot, window, reveal, forecasts)
    if tabs[4].open:
        with tabs[4]:
            evaluation_tab(bundle, snapshot, reveal)


def set_reveal(value: bool) -> None:
    st.session_state["reveal"] = value


def outcomes_bar(reveal: bool, name: str, detail: str) -> None:
    """The deliberate step: showing outcomes never moves the cutoff or the saved forecast."""
    with st.container(border=True, key=f"card-outcomes-{name}", horizontal=True, vertical_alignment="center", gap="medium"):
        heading = "Actual outcomes revealed" if reveal else "Actual outcomes hidden"
        note = "Forecasts stay frozen at the cutoff." if reveal else detail
        html(f'<div class="card-title" style="font-size:14px">{escape(heading)}</div><div class="card-note">{escape(note)}</div>')
        st.space("stretch")
        st.button(
            "Hide outcomes" if reveal else "Reveal outcomes", key=f"reveal-{name}", on_click=set_reveal, args=(not reveal,),
            width="content",
        )


# --- Overview -----------------------------------------------------------------


def overview_tab(bundle: Bundle, snapshot: Snapshot, window: int, reveal: bool, forecasts: MovementForecasts) -> None:
    left, right = st.columns([2.75, 1], gap="small")
    with left:
        theme.title("ATC overview", f"{snapshot.airport.iata} · Forecast operational picture · {window_label(snapshot)}")
        map_section(bundle, snapshot, window)
    with right:
        controller_snapshot(bundle, snapshot, reveal, forecasts)
    outcomes_bar(reveal, "overview", "Historical replay shows forecasts and scheduled demand only.")


def weather_banner(bundle: Bundle, snapshot: Snapshot) -> tuple[str, bool]:
    row, reason = views.weather_feature_row(bundle, snapshot)
    iata = snapshot.airport.iata
    if row is None:
        return f"{iata} · {reason}", False
    if row["thunderstorm_flag"] == 1:
        return f"{iata} · Thunderstorm in the published TAF for {window_label(snapshot)}", True
    if row["cond_thunderstorm_flag"] == 1:
        return f"{iata} · Conditional thunderstorm group in the published TAF for {window_label(snapshot)}", True
    return f"{iata} · No thunderstorm in the published TAF for {window_label(snapshot)}", False


def hub_categories(bundle: Bundle, snapshot: Snapshot) -> dict[str, str]:
    categories = {}
    for icao, info in AIRPORTS.items():
        outlook = views.airport_outlook(bundle, icao, snapshot.asof_utc)
        row = next(iter(outlook.values()), None)
        categories[info["iata"]] = (
            "Unknown" if row is None else views.flight_category(row["obs_visibility_sm"], row["obs_ceiling_ft_agl"])
        )
    return categories


def on_map_airport() -> None:
    choice = st.session_state["ops-map"].airport
    if choice in AIRPORTS:
        st.session_state["airport"] = choice


def on_map_horizon() -> None:
    choice = st.session_state["ops-map"].horizon
    if choice in SCORED_HORIZONS:
        st.session_state["horizon"] = choice


def map_section(bundle: Bundle, snapshot: Snapshot, window: int) -> None:
    flights = bundle.table("flights")
    columns = ["origin", "dest", "direction", "flights"]
    routes = views.route_counts(flights, snapshot.airport, snapshot.asof_utc, window) if flights is not None else pd.DataFrame(columns=columns)
    rows = views.risk_rows(bundle, snapshot)
    radar = views.radar_time(snapshot.asof_utc)
    flagged = views.flagged_routes(rows, flights) if flights is not None else set()
    nodes = pd.DataFrame(columns=["code", "Arrival", "Departure", "flagged", "max_probability"])
    if not routes.empty:
        nodes = views.network_nodes(flights, rows, snapshot.airport, snapshot.asof_utc, window)
    codes = {info["iata"]: icao for icao, info in AIRPORTS.items()}
    payload, unmapped = map_view.map_payload(
        routes, nodes, snapshot.airport.iata, hub_categories(bundle, snapshot), flagged=flagged, radar=radar, codes=codes,
    )
    if payload is None:
        st.info("Map unavailable: no coordinates for the selected airport.")
        return
    text, alert = weather_banner(bundle, snapshot)
    note = f"Sampled {window}-hour connections are schematic, not flown routes"
    payload.update(
        title="Operational map", tag=None, age=None, height=430, viewKey=f"{snapshot.airport.icao}",
        banner={"text": text, "alert": alert}, flag=f"Observed radar {radar:%H:%M} UTC · no forecast layer published",
        layerButtons=[
            {"key": "weather", "label": "Weather", "disabled": False, "reason": ""},
            {"key": "connections", "label": "Connections", "disabled": routes.empty, "reason": "No sampled flights in this window"},
            {"key": "flagged", "label": "Affected flows", "disabled": not flagged, "reason": "No departure at or above threshold at this key"},
        ],
        stops=outputs.forecast_valid_labels(snapshot), validLabel=f"Forecast valid {clock(snapshot.target_hour_utc)} UTC",
        note=f"{note}. {unmapped} movements lack coordinates." if unmapped else f"{note}.",
    )
    with card("map"):
        components.ops_map(payload, "ops-map", on_airport_change=on_map_airport, on_horizon_change=on_map_horizon)


def controller_snapshot(bundle: Bundle, snapshot: Snapshot, reveal: bool, forecasts: MovementForecasts) -> None:
    html(f'<div class="card-title">{escape(snapshot.airport.iata)} · Controller snapshot</div>')
    movement_card(bundle, snapshot, reveal, forecasts)
    capacity_card(bundle, snapshot)
    weather_risk_card(bundle, snapshot)
    response_card(bundle, snapshot)
    with card("status"):
        card_title("Data status", glyph="database")
        open_items = sum(c.status == "unavailable" for c in bundle.capabilities)
        html(
            theme.status_row("green" if open_items == 0 else "amber", "Capabilities unavailable", f"{open_items} of {len(bundle.capabilities)}")
            + theme.status_row("partial", "Traffic coverage", "Reporting carriers")
            + theme.status_row("cyan" if reveal else "", "Outcomes", "Revealed" if reveal else "Hidden")
        )


def movement_card(bundle: Bundle, snapshot: Snapshot, reveal: bool, forecasts: MovementForecasts) -> None:
    target = snapshot.target_hour_utc
    incoming, outgoing = forecasts.at(target, "arrival"), forecasts.at(target, "departure")

    def cell(name: str, row) -> str:
        shown = f'{row.forecast:.0f} <small>/h</small>' if row else "—"
        return f'<div><div class="cap">{name}</div><div class="big {"" if row else "none"}">{shown}</div></div>'

    with card("movements"):
        card_title("Forecast movements", glyph="plane")
        html(f'<div class="split">{cell("Incoming (arrivals)", incoming)}{cell("Outgoing (departures)", outgoing)}</div>')
        if incoming and outgoing:
            st.caption(f"{incoming.forecast + outgoing.forecast:.0f} total · FORECAST")
        reasons = [forecasts.reasons[d] for d in ("arrival", "departure") if d in forecasts.reasons]
        if reasons:
            st.caption(" ".join(reasons))
        if forecasts.held:
            html(badge("PREVIEW · TEAM AGREEMENT PENDING", "amber"))
        last = outputs.last_completed_hour(bundle.table("traffic_hourly"), snapshot.airport, snapshot.asof_utc)
        if last:
            st.caption(f"Last observed: {last['incoming']} in / {last['outgoing']} out · {clock(last['hour_utc'])}–{clock(snapshot.asof_utc)} UTC · reporting carriers")
        else:
            st.caption("Last completed hour: no observed counts.")
        if reveal:
            actual_in, actual_out = views.actual_at(bundle.table("traffic_hourly"), snapshot.airport, target)
            st.caption(f"Actual {number(actual_in)} in / {number(actual_out)} out · {window_label(snapshot)}")


def capacity_card(bundle: Bundle, snapshot: Snapshot) -> None:
    arrivals, _ = views.scheduled_at(bundle.table("traffic_hourly"), snapshot.airport, snapshot.target_hour_utc)
    row, kind, reason = views.capacity_row(bundle, snapshot)
    with card("capacity"):
        card_title("Arrival demand / capacity", glyph="bars")
        if row is None:
            html(f'<div style="font-size:15px;font-weight:600">{number(arrivals)} scheduled / capacity unknown</div>')
            st.caption(f"AAR not available. {reason} Scheduled counts are reconstructed, not queue demand.")
            return
        if kind == "estimate":
            html(f'<div style="font-size:15px;font-weight:600">{number(arrivals)} scheduled</div>')
            html(badge("MODEL PROXY · NOT AAR", "amber"))
            st.metric(views.ESTIMATE_TITLE + " (arrivals/hour)", f"{row['aar_pred']:.1f}")
            st.caption(f"{views.estimate_note(row)}. Genuine AAR not available: {reason}")
            return
        html(f'<div style="font-size:15px;font-weight:600">{number(arrivals)} scheduled / {row["aar_pred"]:.0f} per hour</div>')
        st.metric("Predicted AAR (arrivals/hour)", f"{row['aar_pred']:.1f}")
        bounds = views.uncertainty(row)
        st.caption(f"Interval {bounds[0]:.1f}–{bounds[1]:.1f}" if bounds else "Uncertainty unknown")


def weather_risk_card(bundle: Bundle, snapshot: Snapshot) -> None:
    probabilities, reason = outputs.weather_probabilities(bundle, snapshot.airport, snapshot.asof_utc)
    weather = bundle.table("weather")
    with card("weather-risk"):
        if probabilities is not None:
            card_title("Weather risk", f"FORECAST · +{snapshot.horizon_hours}h · {window_label(snapshot)}", glyph="cloud")
            html(theme.bars({c: outputs.probability(probabilities, c, snapshot.horizon_hours) for c in outputs.PROBABILITY_CONDITIONS}))
        elif weather is not None:
            card_title("Weather base rates", "Past frequency, same season and hour. Not a forecast.", glyph="cloud")
            history = views.observed_history(weather, snapshot.airport.icao, snapshot.asof_utc, snapshot.target_hour_utc)
            html(theme.bars(views.condition_frequency(history)))
            st.caption("Weather probability model unavailable.")
        else:
            card_title("Weather risk", glyph="cloud")
            st.caption(reason)


def response_card(bundle: Bundle, snapshot: Snapshot) -> None:
    actions, reason = outputs.proposed_actions(bundle, snapshot)
    with card("response"):
        card_title("Review priorities", glyph="file")
        brief, problem = views.review_priorities(bundle, snapshot)
        if brief is not None and brief["status"] == "available":
            st.write(f"{brief['flagged_flights']} departures meet their review threshold.")
            st.caption("Review weather and airline/inbound-aircraft status. See Compare for ranked priorities and evidence.")
        else:
            st.caption("Departure review priorities unavailable: " + (problem or brief["summary"]))
        st.caption("Operational proposal")
        if not actions:
            html(badge("NOT AVAILABLE"))
            st.caption(reason)
        else:
            html(badge("PROPOSED · NOT EXECUTED", "amber"))
            for condition, row in actions.items():
                st.caption(f"{condition}: {row['action']}")
        review_brief_download(bundle, snapshot)


def review_brief_download(bundle: Bundle, snapshot: Snapshot) -> None:
    """One-click controller review brief for the snapshot on screen (no outcomes, no instructions)."""
    brief, text, reason = outputs.review_brief(bundle, snapshot)
    if brief is None:
        st.caption(reason)
        return
    st.caption(f"{brief['flagged_flights']} of {brief['sampled_flights_scored']} sampled departures flagged for review.")
    stem = f"review-brief-{snapshot.airport.icao}-{snapshot.asof_utc:%Y%m%dT%H%MZ}-{snapshot.horizon_hours}h"
    st.download_button("Download review brief", text, file_name=f"{stem}.md", mime="text/markdown",
                       key="review-brief-md", icon=":material/download:", width="stretch")


# --- Weather ------------------------------------------------------------------


def weather_tab(bundle: Bundle, snapshot: Snapshot) -> None:
    probabilities, reason = outputs.weather_probabilities(bundle, snapshot.airport, snapshot.asof_utc)
    row, feature_reason = views.weather_feature_row(bundle, snapshot)
    outlook = views.airport_outlook(bundle, snapshot.airport.icao, snapshot.asof_utc)
    with st.container(horizontal=True, vertical_alignment="bottom"):
        theme.title("Weather outlook", f"{snapshot.airport.iata} · Probability of conditions across +3h, +6h, +12h")
        st.space("stretch")
        source = "Probabilities from weather model" if probabilities is not None else "No weather probability model published"
        html(f'<div class="card-note" style="white-space:nowrap">Forecast cutoff {clock(snapshot.asof_utc)} UTC · {source}</div>')
    if snapshot.airport.heading is None:
        row, feature_reason = None, f"{snapshot.airport.icao} has no configured runway heading, so runway-relative wind is refused."
    probability_tiles(row, probabilities, snapshot, feature_reason, reason)
    from src.dashboard.weather_actions import render_weather_actions
    render_weather_actions(row, snapshot, bundle)
    weather = bundle.table("weather")
    histories = {}
    if weather is not None:
        targets = {lead: snapshot.asof_utc + pd.Timedelta(hours=lead) for lead in SCORED_HORIZONS}
        histories = {
            lead: views.observed_history(weather, snapshot.airport.icao, snapshot.asof_utc, target)
            for lead, target in targets.items()
        }
    left, right = st.columns([1.15, 1], gap="small")
    with left, card("heat"):
        condition_grid(probabilities, histories, snapshot)
    with right, card("taf"):
        taf_table(outlook, snapshot)
    left, right = st.columns([1.15, 1], gap="small")
    with left, card("categories"):
        category_section(probabilities, histories, snapshot)
    with right, card("ceiling"):
        ceiling_section(probabilities, outlook)
    sources_strip(bundle, snapshot, outlook, probabilities)


def probability_tiles(row, probabilities, snapshot: Snapshot, feature_reason, reason) -> None:
    icons = {"Thunderstorm": "storm", "IFR / LIFR": "cloud", "Visibility < 3 SM": "eye", "Gusts ≥ 25 kt": "wind"}
    lead = f"+{snapshot.horizon_hours}h · {window_label(snapshot)}"
    for column, condition in zip(st.columns(4, gap="small"), outputs.PROBABILITY_CONDITIONS):
        share = outputs.probability(probabilities, condition, snapshot.horizon_hours)
        if share is not None:
            tone = "red" if share >= outputs.ALERT_THRESHOLD else "amber"
            html(tile(condition, f"{share:.0%}", f"FORECAST · {lead}", tone, icons[condition], badge("FORECAST")), column)
        else:
            state = outputs.taf_state(row, condition) if row is not None else "Unknown"
            html(tile(condition, "—", f"Model probability unavailable · TAF: {state}", "muted", icons[condition], badge("UNAVAILABLE")), column)
    if probabilities is None:
        unavailable("Weather probabilities", reason)
    if row is None:
        unavailable("Cutoff-safe weather", feature_reason)
    else:
        st.caption(f"Runway-relative wind uses the fixed heading {snapshot.airport.heading:03d}°.")


def lead_columns(snapshot: Snapshot) -> list[tuple[str, str]]:
    columns = []
    for lead in SCORED_HORIZONS:
        start = snapshot.asof_utc + pd.Timedelta(hours=lead)
        suffix = " (+1d)" if start.date() != snapshot.asof_utc.date() else ""
        columns.append((f"+{lead}h", f"{clock(start)}–{clock(start + outputs.WINDOW)}{suffix}"))
    return columns


def condition_grid(probabilities, histories: dict, snapshot: Snapshot) -> None:
    highlight = SCORED_HORIZONS.index(snapshot.horizon_hours)
    if probabilities is not None:
        card_title("Condition probability by horizon", "Events can overlap, so these do not sum to 100%.", glyph="bars")
        values = {c: [outputs.probability(probabilities, c, lead) for lead in SCORED_HORIZONS] for c in outputs.PROBABILITY_CONDITIONS}
        html(theme.heatmap(lead_columns(snapshot), values, highlight))
        return
    card_title("Historical base rates by horizon", "Share of METARs before the cutoff, same season and time of day. Not a forecast.", glyph="bars")
    if not histories:
        st.caption("Weather observations are unavailable.")
        return
    frequency = {lead: views.condition_frequency(history) for lead, history in histories.items()}
    values = {name: [frequency[lead][name] for lead in SCORED_HORIZONS] for name in views.CONDITIONS}
    html(theme.heatmap(lead_columns(snapshot), values, highlight))
    st.caption(f"Based on {min(len(h) for h in histories.values()):,}+ reports per lead.")


def taf_table(outlook: dict, snapshot: Snapshot) -> None:
    with st.container(horizontal=True, vertical_alignment="center"):
        card_title("Published TAF outlook", glyph="file")
        st.space("stretch")
        html(badge("PUBLISHED FORECAST", "cyan"))
    if not outlook:
        st.caption("No published TAF at this cutoff.")
        return
    leads = [lead for lead in SCORED_HORIZONS if lead in outlook]
    first = outlook[leads[0]]
    st.caption(f"Issued {fmt_time(first['taf_issued_at_utc'])} · Available {fmt_time(first['taf_available_at_utc'])}. Published values, not modelled probabilities.")
    rows = [
        [
            f"+{lead}h · {clock(outlook[lead]['target_hour_utc'])}",
            chip(views.flight_category(outlook[lead]["visibility_sm"], outlook[lead]["ceiling_ft_agl"])),
            f"{views.weather_display('visibility_sm', outlook[lead])} SM",
            views.weather_display("ceiling_ft_agl", outlook[lead]),
            views.weather_display("wind_gust_kt", outlook[lead]),
            views.weather_display("thunderstorm_flag", outlook[lead]),
            f"{outlook[lead]['cond_groups']:.0f}",
        ]
        for lead in leads
    ]
    selected = leads.index(snapshot.horizon_hours) if snapshot.horizon_hours in leads else None
    html(theme.table(["Horizon", "Flight category", "Visibility", "Ceiling", "Gust", "Thunderstorm", "Conditional"], rows, selected))
    category = views.flight_category(first["obs_visibility_sm"], first["obs_ceiling_ft_agl"])
    html(
        f'<div class="strip" style="background:var(--bg-inset);font-size:12px">Observed at cutoff: {chip(category)} '
        f'<b>{views.known_value(first["obs_visibility_sm"], " SM", 1)} · {escape(views.weather_display("obs_ceiling_ft_agl", first))} · '
        f'{first["metar_observed_at_utc"]:%H:%M} UTC</b></div>'
    )


def category_section(probabilities, histories: dict, snapshot: Snapshot) -> None:
    clocks = [clock(snapshot.asof_utc + pd.Timedelta(hours=lead)) for lead in SCORED_HORIZONS]
    if probabilities is not None:
        card_title("Flight-category probabilities", "Mutually exclusive; each row sums to 100%.", glyph="bars")
        shares = {
            lead: {c: outputs.probability(probabilities, c, lead) for c in views.CATEGORIES} for lead in SCORED_HORIZONS
        }
    elif histories:
        card_title("Flight-category base rates", "Past frequency by flight category. Not a forecast.", glyph="bars")
        shares = {lead: views.category_frequency(history) for lead, history in histories.items()}
    else:
        card_title("Flight-category probabilities", glyph="bars")
        st.caption("Weather observations are unavailable.")
        return
    st.plotly_chart(plots.category_bars(shares, list(SCORED_HORIZONS), clocks), key="category-bars", **CHART)


def ceiling_section(probabilities, outlook: dict) -> None:
    modelled = None if probabilities is None else probabilities[probabilities["condition"] == "Ceiling"].sort_values("horizon_hours")
    if modelled is not None and not modelled.empty:
        card_title("Ceiling forecast & uncertainty", "Probability-model forecast · median and 80% interval (P10–P90)", glyph="trend")
        labels = [f"+{lead}h" for lead in modelled["horizon_hours"]]
        figure = plots.ceiling_by_lead(labels, list(modelled["value"]), list(modelled["lower"]), list(modelled["upper"]))
        st.plotly_chart(figure, key="ceiling", **CHART)
        return
    card_title("Ceiling forecast", "Published TAF point forecast. No uncertainty interval is published.", glyph="trend")
    leads = [lead for lead in SCORED_HORIZONS if lead in outlook]
    ceilings = [outlook[lead]["ceiling_ft_agl"] for lead in leads]
    if any(c < views.NO_CEILING_FT for c in ceilings):
        shown = [min(c, views.NO_CEILING_FT) for c in ceilings]
        st.plotly_chart(plots.ceiling_by_lead([f"+{lead}h" for lead in leads], shown), key="ceiling", **CHART)
    else:
        html(theme.empty("cloud", "No ceiling forecast", "The TAF reports no ceiling at any lead."))


def sources_strip(bundle: Bundle, snapshot: Snapshot, outlook: dict, probabilities) -> None:
    weather = bundle.table("weather")
    with card("sources"):
        card_title("Sources & forecast information", glyph="file")
        model = "Not published" if probabilities is None else ", ".join(map(str, probabilities["model_version"].unique()))
        first = next(iter(outlook.values()), None)
        valid = "Unknown" if first is None else f"{fmt_time(first['taf_group_valid_from_utc'])} to {fmt_time(first['taf_group_valid_to_utc'])}"
        st.caption(f"Forecast model: {model} · Cutoff: {clock(snapshot.asof_utc)} UTC · TAF group at +{next(iter(outlook), '—')}h valid: {valid}")
        if weather is not None:
            bulletins = views.bulletins_as_of(weather, snapshot)
            with st.expander(f"{len(bulletins)} bulletins known at cutoff and valid at target"):
                st.dataframe(bulletins, hide_index=True)


# --- Traffic ------------------------------------------------------------------


def traffic_tab(bundle: Bundle, snapshot: Snapshot, window: int, reveal: bool, forecasts: MovementForecasts) -> None:
    theme.title("Traffic volumes", f"{snapshot.airport.iata} · Observed movements and hourly incoming/outgoing forecasts")
    traffic = bundle.table("traffic_hourly")
    traffic_tiles(traffic, snapshot, forecasts)
    last = outputs.last_completed_hour(traffic, snapshot.airport, snapshot.asof_utc)
    if last:
        total = last["incoming"] + last["outgoing"]
        detail = f"{clock(last['hour_utc'])}–{clock(snapshot.asof_utc)} UTC: {last['incoming']} incoming · {last['outgoing']} outgoing · {total} total · OBSERVED · reporting carriers"
        theme.strip("clock", "Latest completed hour", detail)
    if traffic is None:
        unavailable("Reporting-carrier traffic", bundle.problem("traffic_hourly"))
    else:
        rows = outputs.hourly_movements(traffic, forecasts, snapshot.airport, snapshot.asof_utc, reveal)
        hourly_charts(rows, snapshot)
        hourly_table(rows, snapshot, reveal, forecasts)
        st.caption(
            f"Population: {', '.join(map(str, traffic['population'].unique()))}. Reconstructed "
            "retrospectively, not known at the cutoff, so these counts are not queue demand."
        )
    capacity, kind, reason = views.capacity_row(bundle, snapshot)
    if capacity is None:
        context = f"Arrival capacity context: AAR unavailable. {escape(reason)} AAR is not a traffic-volume prediction."
    elif kind == "estimate":
        context = f"Arrival capacity context: {capacity['aar_pred']:.0f}/h model proxy, not AAR · separate from scheduled demand"
    else:
        context = f"Arrival capacity context: {capacity['aar_pred']:.0f}/h · separate from scheduled demand"
    theme.notice(context, "quiet", "info")
    flights = bundle.table("flights")
    if flights is not None:
        movements = views.planning_movements(flights, snapshot.airport, snapshot.asof_utc, window)
        scored = views.scored_flights(flights, snapshot)
        with st.expander("Sampled flights behind the risk model"):
            st.caption(
                f"{movements['arrivals']} arrivals and {movements['departures']} departures over {window} h, "
                f"{len(scored)} departures in the target hour ({movements['coverage']} coverage). Movements are not unique "
                "flights, and a sample cannot establish whole-airport demand."
            )
            st.plotly_chart(plots.traffic_bars(movements["hourly"], movements["coverage"]), key="traffic", **CHART)
            st.dataframe(movements["hourly"], hide_index=True)
    with st.expander("Departure severe-delay risk (supporting context)", expanded=False):
        risk_section(bundle, snapshot, reveal)
    outcomes_bar(reveal, "traffic", "Post-cutoff counts are outcomes and stay hidden until revealed.")


def traffic_tiles(traffic, snapshot: Snapshot, forecasts: MovementForecasts) -> None:
    target = snapshot.target_hour_utc
    incoming, outgoing = forecasts.at(target, "arrival"), forecasts.at(target, "departure")
    arrivals, departures = views.scheduled_at(traffic, snapshot.airport, target)

    def forecast_tile(label, row, tone, glyph, direction):
        if row is None:
            return tile(label, "—", forecasts.reasons.get(direction, "Unavailable"), "muted", glyph, badge("UNAVAILABLE"))
        interval = f" · range {row.lower:.0f}–{row.upper:.0f}" if row.lower is not None else ""
        tag = badge("PREVIEW", "amber") if forecasts.held else badge("FORECAST")
        return tile(label, f"{row.forecast:.0f}", f"FORECAST {window_label(snapshot)}{interval}", tone, glyph, tag)

    total = (
        tile("Total movements", f"{incoming.forecast + outgoing.forecast:.0f}", f"FORECAST · {incoming.forecast:.0f} in + {outgoing.forecast:.0f} out", "", "swap")
        if incoming and outgoing else tile("Total movements", "—", "Needs both incoming and outgoing forecasts", "muted", "swap", badge("UNAVAILABLE"))
    )
    scheduled = (
        tile("Scheduled demand", "—", "No schedule at the target hour", "muted", "calendar")
        if pd.isna(arrivals) or pd.isna(departures)
        else tile("Scheduled demand", f"{arrivals + departures:.0f}", f"{arrivals:.0f} arrivals + {departures:.0f} departures · SCHEDULED", "", "calendar", badge("SCHEDULED"))
    )
    cards = [forecast_tile("Incoming", incoming, "cyan", "landing", "arrival"), forecast_tile("Outgoing", outgoing, "violet", "takeoff", "departure"), total, scheduled]
    for column, markup in zip(st.columns(4, gap="small"), cards):
        html(markup, column)


def hourly_charts(rows: pd.DataFrame, snapshot: Snapshot) -> None:
    left, right = st.columns(2, gap="small")
    for column, name, label, color, glyph in (
        (left, "incoming", "Incoming flights · hourly volume", plots.SERIES[0], "landing"),
        (right, "outgoing", "Outgoing flights · hourly volume", plots.SERIES[1], "takeoff"),
    ):
        with column, card(f"chart-{name}"):
            card_title(label, glyph=glyph)
            figure = plots.hourly_volume(rows, name, color, snapshot.asof_utc, snapshot.target_hour_utc)
            st.plotly_chart(figure, key=f"reporting-{name}", **CHART)


def movement_export(rows: pd.DataFrame, reveal: bool) -> pd.DataFrame:
    keep = ["hour_utc"] + [f"{d}_{k}" for d in ("incoming", "outgoing") for k in ("observed", "forecast", "lower", "upper", "scheduled")]
    if reveal:
        keep += ["incoming_actual", "outgoing_actual"]
    return rows[keep]


def hourly_table(rows: pd.DataFrame, snapshot: Snapshot, reveal: bool, forecasts: MovementForecasts) -> None:
    future = rows[rows["hour_utc"] >= snapshot.asof_utc].reset_index(drop=True)
    with card("hourly"):
        with st.container(horizontal=True, vertical_alignment="center"):
            card_title("Hourly movement forecast", glyph="table")
            st.space("stretch")
            st.download_button(
                "Export table", movement_export(rows, reveal).to_csv(index=False), "hourly-movements.csv", "text/csv",
                key="export-hourly", width="content",
            )
        issued = f"Forecast issued at {clock(snapshot.asof_utc)} UTC · reporting-carrier counts, not whole-airport totals"
        st.caption(issued + (" · forecasts exist only at +3h, +6h and +12h" if forecasts.rows else ""))
        headers = ["Hour (UTC)", "Incoming forecast", "Outgoing forecast", "Total forecast", "Scheduled in / out", "Scheduled total"]
        if reveal:
            headers += ["Actual in / out", "Actual total"]
        table = []
        for row in future.itertuples():
            has_both = pd.notna(row.incoming_forecast) and pd.notna(row.outgoing_forecast)
            cells = [
                clock(row.hour_utc), number(row.incoming_forecast), number(row.outgoing_forecast),
                number(row.incoming_forecast + row.outgoing_forecast) if has_both else "—",
                f"{number(row.incoming_scheduled)} / {number(row.outgoing_scheduled)}",
                number(row.incoming_scheduled + row.outgoing_scheduled),
            ]
            if reveal:
                cells += [f"{number(row.incoming_actual)} / {number(row.outgoing_actual)}", number(row.incoming_actual + row.outgoing_actual)]
            table.append(cells)
        selected = future.index[future["hour_utc"] == snapshot.target_hour_utc]
        html(theme.table(headers, table, int(selected[0]) if len(selected) else None, {1: "in", 2: "out"}))


def risk_section(bundle: Bundle, snapshot: Snapshot, reveal: bool) -> None:
    card_title("Departure severe-delay risk", f"Departures from {snapshot.airport.iata} only; inbound flights are never scored")
    rows = views.risk_rows(bundle, snapshot)
    if rows is None:
        unavailable("Flight risk", bundle.problem("predictions"))
        return
    if rows.empty:
        st.error(
            f"**Unsupported selection.** No held-out prediction exists for {snapshot.airport.icao} "
            f"at this cutoff and +{snapshot.horizon_hours} h. No other snapshot is substituted.",
            icon="🚫",
        )
        return
    thresholds = sorted(rows["threshold"].unique())
    left, middle, right = st.columns(3)
    left.metric("Flights scored", len(rows))
    middle.metric("At or above threshold", int(views.flagged(rows).sum()))
    right.metric("Selected threshold", " / ".join(f"{t:.3f}" for t in thresholds))
    schedule_only = int(rows["model_kind"].map(is_schedule_only).sum())
    if schedule_only:
        st.warning(
            f"**Schedule-only model** for {schedule_only} of {len(rows)} flights, with no accepted "
            "weather at this key. It uses no weather, so repeated scores across leads say nothing "
            "about weather sensitivity.", icon="⚠️",
        )
    st.caption(
        f"Model {', '.join(map(str, rows['model_version'].unique()))} · run {rows['run_id'].iloc[0]} · "
        f"coverage {', '.join(map(str, rows['coverage'].unique()))}. Probabilities, not delay minutes."
    )
    st.plotly_chart(plots.risk_bars(rows, thresholds[0] if len(thresholds) == 1 else None), key="risk", **CHART)
    flights = bundle.table("flights")
    table = rows
    if flights is not None and reveal:
        table = rows.merge(flights[["flight_id", *views.OUTCOME_COLUMNS]], how="left", on="flight_id")
    table = table.assign(
        Model=table["model_kind"].map(views.model_label),
        Flagged=views.flagged(table).map({True: "Above threshold", False: "Below threshold"}),
    )
    hidden = ("airport", "asof_utc", "target_hour_utc", "horizon_hours", "run_id", "model_kind")
    st.dataframe(views.mask_outcomes(table[[c for c in table.columns if c not in hidden]], reveal), hide_index=True)


# --- Compare ------------------------------------------------------------------


def compare_tab(bundle: Bundle, snapshot: Snapshot, window: int, reveal: bool, forecasts: MovementForecasts) -> None:
    results, reason = outputs.verify_events(bundle, snapshot)
    as_of = outputs.verification_as_of(snapshot)
    with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
        theme.title(
            "Forecast vs actual",
            f"{snapshot.airport.iata} · Forecast frozen {clock(snapshot.asof_utc)} UTC · Event window {window_label(snapshot)}",
        )
        st.space("stretch")
        html(badge("OUTCOMES REVEALED", "cyan") if reveal else badge("OUTCOMES HIDDEN"))
        st.button("Hide outcomes" if reveal else "Reveal outcomes", key="reveal-compare", on_click=set_reveal, args=(not reveal,), width="content")
        if reveal:
            html(f'<div class="card-note" style="white-space:nowrap">Reviewed as of {clock(as_of)} UTC</div>')
    basis = results[0].forecast_basis if results else "No saved forecast"
    policy = f"Alert when probability ≥ {outputs.ALERT_THRESHOLD:.0%}" if basis == "Model probability" else "Alert when the prevailing published TAF states the condition"
    html(f'<div class="strip" style="font-size:12px">{theme.icon("info")}<span>{escape(policy)} · Forecast basis: {escape(basis)} · Forecast saved before event window</span></div>')
    if not results:
        unavailable("Event verification", reason or "No saved forecast at this key.")
    elif not reveal:
        st.info("This comparison uses observed outcomes. Turn on **Reveal outcomes** to view it.", icon="🔒")
    else:
        revealed_summary(bundle, snapshot, results, forecasts)
    from src.dashboard.presentation_actions import review_actions_section, arrival_scenario_section
    with st.container(border=True):
        card_title("Proposed actions", "For human review. Nothing is transmitted.")
        review_actions_section(bundle, snapshot)
        arrival_scenario_section(bundle, snapshot, window)
    scenario_table(bundle, snapshot, results, reveal)
    if reveal:
        with st.expander("Departure-delay alerts at this key"):
            outcome_section(bundle, snapshot)
        with st.expander("Historical trends"):
            trends_section(bundle, snapshot)
    with st.expander("Published decision snapshot"):
        decision_section(bundle, snapshot, window)
    evidence_bar(snapshot, results, reveal)


def revealed_summary(bundle: Bundle, snapshot: Snapshot, results: list, forecasts: MovementForecasts) -> None:
    counts = outputs.alert_counts(results)
    tiles = [
        tile("Forecast alerts", counts["alerts"], "Issued at the cutoff", "cyan", "bell"),
        tile("Matched alerts", counts["matched"], "Alert and event observed", "green", "check"),
        tile("False alerts", counts["false"], "Alert, event not in reports", "red", "cross"),
        tile("Missed events", counts["missed"], "No alert, event observed", "amber", "alert"),
    ]
    for column, markup in zip(st.columns(4, gap="small"), tiles):
        html(markup, column)
    if counts["unscored"]:
        st.caption(f"{counts['unscored']} scenario(s) unscored: missing observations are not confirmed non-events.")
    left, right = st.columns([55, 45], gap="small")
    with left, card("traffic-vs"):
        traffic_versus(bundle, snapshot, forecasts)
    with right, card("happened"):
        happened_section(bundle, snapshot, results)


def traffic_versus(bundle: Bundle, snapshot: Snapshot, forecasts: MovementForecasts) -> None:
    card_title("Traffic forecast vs observed", f"Forecast saved {clock(snapshot.asof_utc)} · Actual {window_label(snapshot)} · reporting carriers", glyph="bars")
    target = snapshot.target_hour_utc
    actual_in, actual_out = views.actual_at(bundle.table("traffic_hourly"), snapshot.airport, target)
    incoming, outgoing = forecasts.at(target, "arrival"), forecasts.at(target, "departure")

    def value(number_):
        return None if pd.isna(number_) else number_

    groups = [("Incoming", incoming.forecast if incoming else None, value(actual_in)), ("Outgoing", outgoing.forecast if outgoing else None, value(actual_out))]
    st.plotly_chart(plots.forecast_actual_bars(groups), key="forecast-vs-actual", **CHART)
    forecast_total = incoming.forecast + outgoing.forecast if incoming and outgoing else None
    actual_total = None if pd.isna(actual_in) or pd.isna(actual_out) else actual_in + actual_out
    error = None if forecast_total is None or actual_total is None else actual_total - forecast_total
    delta = "—" if error is None else f"{error:+.0f}".replace("-", "−")
    html(
        f'<div class="totals"><div>Total forecast<b class="{"" if forecast_total is not None else "none"}">{number(forecast_total)}</b></div>'
        f'<div>Actual<b>{number(actual_total)}</b></div><div>Actual minus forecast<b class="{"red" if error else "none" if error is None else ""}">{delta}</b></div></div>'
    )
    reasons = [forecasts.reasons[d] for d in ("arrival", "departure") if d in forecasts.reasons]
    if reasons:
        st.caption(" ".join(reasons))


def happened_section(bundle: Bundle, snapshot: Snapshot, results: list) -> None:
    card_title("What actually happened", glyph="file")
    observations = outputs.event_observations(bundle.table("weather"), snapshot)
    entries = outputs.event_log(results, observations)
    if entries:
        html('<div class="log">' + "".join(f"<div><i></i><b>{clock(when)}</b><span>{escape(text)}</span></div>" for when, text in entries) + "</div>")
    else:
        html(theme.empty("alert", "No observation in this window", "Missing reports are not evidence that nothing happened."))
    st.caption(f"{len(observations)} METAR report(s) in {window_label(snapshot)}, available by {clock(results[0].verified_as_of_utc)} UTC.")
    if not observations.empty:
        with st.expander("Observation records"):
            columns = ["valid_from_utc", "available_at_utc", "visibility_sm", "ceiling_ft_agl", "wind_speed_kt", "wind_gust_kt", "thunderstorm_flag", "raw_text"]
            st.dataframe(observations[columns], hide_index=True)


def scenario_table(bundle: Bundle, snapshot: Snapshot, results: list, reveal: bool) -> None:
    actions, reason = outputs.proposed_actions(bundle, snapshot)
    with card("scenarios"):
        card_title("Predicted scenarios, outcomes & proposed actions", glyph="file")
        rows, classes = [], {}
        for index, result in enumerate(results):
            action = actions.get(result.condition)
            proposed = escape(str(action["action"])) if action is not None else escape(reason)
            actual = escape(result.actual) if reveal else "Hidden"
            outcome = escape(result.result) if reveal else "Hidden"
            rows.append(
                [
                    escape(result.condition), result.forecast_label if result.probability is not None else "—", escape(result.forecast_label) if result.probability is None else "Model",
                    actual, outcome, proposed,
                ]
            )
            classes[(index, 4)] = outputs.RESULT_TONE.get(result.result, "") if reveal else "dim"
            classes[(index, 5)] = "wrap" if action is not None else "wrap dim"
        html(theme.table(["Forecast scenario", "Probability", "Published TAF", "Actual event", "Result", "Action proposed at cutoff"], rows, cell_classes=classes))
        st.caption("Reroute and diversion ranking unavailable: verified route times and alternate eligibility are missing.")


def evidence_bar(snapshot: Snapshot, results: list, reveal: bool) -> None:
    with card("evidence"):
        st.caption(f"Event hits and misses do not measure probability calibration; see Evaluation. No proposed action is recorded as executed at {clock(snapshot.asof_utc)} UTC, and no causal benefit is inferred.")
        if results and reveal:
            with st.expander("Inspect forecast and observation evidence"):
                st.dataframe(
                    pd.DataFrame(
                        {
                            "Forecast key": r.forecast_key, "Event definition": r.definition, "Forecast basis": r.forecast_basis,
                            "Forecast": r.forecast_label, "Alert": r.alert, "Actual": r.actual, "Evidence UTC": r.evidence_utc,
                            "Usable reports": r.reports, "Outcome": r.result, "Verified as of": r.verified_as_of_utc,
                        }
                        for r in results
                    ),
                    hide_index=True,
                )


def outcome_section(bundle: Bundle, snapshot: Snapshot) -> None:
    card_title("Alerts against outcomes", "Departures over 45 minutes late at this exact key")
    rows = views.risk_rows(bundle, snapshot)
    flights = bundle.table("flights")
    if rows is None or rows.empty or flights is None:
        st.caption("No scored flights with outcomes at this key.")
        return
    table, counts = views.forecast_vs_actual(rows, flights)
    tiles = [
        tile("Forecast alerts", counts["alerts"]), tile("Matched alerts", counts["matched"]),
        tile("False alerts", counts["false"]), tile("Missed events", counts["missed"]),
    ]
    for column, markup in zip(st.columns(4, gap="small"), tiles):
        html(markup, column)
    if counts["excluded"]:
        st.caption(f"{counts['excluded']} flight(s) excluded: cancelled or no delay label, never counted as on time.")
    columns = ["flight_id", "probability_severe_delay", "threshold", "dep_delay_min", "result"]
    st.dataframe(table[columns], hide_index=True)
    st.caption("One snapshot says little about model quality. See Evaluation for held-out metrics.")


def decision_section(bundle: Bundle, snapshot: Snapshot, window: int) -> None:
    recommendations = bundle.docs.get("recommendations")
    if recommendations is None:
        unavailable("Decision support", bundle.problem("recommendations"))
        return
    published = (
        f"{recommendations.get('airport')} at {recommendations.get('asof_utc')} "
        f"with a {recommendations.get('horizon_hours')}-hour planning window"
    )
    mismatch = views.decision_mismatch(recommendations, snapshot.airport, snapshot.asof_utc, window)
    if mismatch:
        st.error(
            f"**No decision output for this selection** ({'; '.join(mismatch)}). "
            f"The only published snapshot is {published}, and it is not reused here.", icon="🚫",
        )
        return
    run = bundle.groups["decision"].manifest["run_id"]
    st.caption(f"Decision run {run} · {published}. Scenario values are simulated.")
    problems = views.queue_problems(bundle.table("queue"), snapshot.airport, snapshot.asof_utc, window)
    if problems:
        unavailable("Arrival queue", "; ".join(problems) + ".")
    else:
        rows = views.queue_rows(bundle.table("queue"), snapshot.airport, snapshot.asof_utc)
        st.plotly_chart(plots.queue_lines(rows), key="queue", **CHART)
        st.plotly_chart(plots.backlog_bars(rows), key="backlog", **CHART)
        st.dataframe(rows, hide_index=True)
    items, withheld = views.supported_recommendations(
        recommendations, not problems, bundle.table("eligible_flights") is not None
    )
    for reason in withheld:
        st.warning(f"Withheld: {reason}", icon="⛔")
    for item in items:
        with st.container(border=True):
            st.markdown(f"**{item['action']}** — needs human review")
            st.write(item.get("rationale", ""))
            if item.get("affected_flight_ids"):
                st.write("Affected flights:", item["affected_flight_ids"])
            else:
                st.caption("No flight-specific timing: eligibility evidence is not available.")
            st.json({k: item.get(k) for k in ("baseline", "proposed", "prerequisites", "source")}, expanded=False)
    if not items and not withheld:
        st.info("No action advised at this snapshot.")
    if recommendations.get("missing_inputs"):
        st.markdown("**Missing inputs**")
        st.write(recommendations["missing_inputs"])
    if recommendations.get("limitations"):
        st.markdown("**Limitations**")
        st.write(recommendations["limitations"])


def trends_section(bundle: Bundle, snapshot: Snapshot) -> None:
    card_title("Historical trends", "Observed sample cohorts by UTC period, not whole-airport impact or forecasts")
    metrics = bundle.table("normalized_metrics")
    if metrics is None:
        unavailable("Historical trends", bundle.problem("normalized_metrics"))
        return
    st.caption("Severe rate and minutes per flight use eligible departures (non-cancelled, known delay) as denominator.")
    period_col, split_col = st.columns([1, 2])
    period = period_col.segmented_control("Period", ["Week", "Month", "Day"], default="Week", required=True, key="trend-period")
    splits = sorted(metrics["split"].dropna().unique())
    chosen = split_col.multiselect("Splits", splits, default=splits, key="trend-splits")
    rollup = views.history_rollup(metrics[metrics["split"].isin(chosen)], period[0])
    st.plotly_chart(
        plots.trend_lines(rollup, "severe_delay_rate", "Severe-delay rate", "Share of eligible departures", True),
        key="trend-rate", **CHART,
    )
    st.plotly_chart(
        plots.trend_lines(rollup, "delay_minutes_per_flight", "Positive delay per eligible flight", "Minutes"),
        key="trend-minutes", **CHART,
    )
    st.dataframe(rollup, hide_index=True)
    aar_trend_section(bundle, snapshot)


def aar_trend_section(bundle: Bundle, snapshot: Snapshot) -> None:
    card_title("AAR observed versus predicted")
    rows = views.aar_trend(bundle.table("forecast"), snapshot.airport, snapshot.horizon_hours)
    if rows.empty:
        unavailable("AAR trend", "No held-out rows with a genuine observed AAR are published.")
        return
    st.plotly_chart(plots.aar_lines(rows, snapshot.airport.icao, snapshot.horizon_hours), key="aar-trend", **CHART)
    st.dataframe(rows[["target_hour_utc", "aar_observed", "aar_pred"]], hide_index=True)


# --- Evaluation ---------------------------------------------------------------


def evaluation_tab(bundle: Bundle, snapshot: Snapshot | None, reveal: bool) -> None:
    from src.dashboard.readiness import render_readiness
    render_readiness(bundle, snapshot)
    with st.container(horizontal=True, vertical_alignment="top"):
        theme.title("Evaluation & data coverage", "Models, baselines and evidence behind the replay")
        st.space("stretch")
        open_items = sum(c.status == "unavailable" for c in bundle.capabilities)
        html(badge(f"{open_items} CAPABILITIES UNAVAILABLE", "amber") if open_items else badge("ALL CAPABILITIES LOADED", "green"))
    html(
        '<div class="steps"><div class="step">TRAIN · 2023<span>Jan – Dec 2023</span></div>'
        '<div class="step">VALIDATE · 2024<span>Jan – Dec 2024</span></div>'
        '<div class="step">TEST · Jan – Jul 2025<span>Held out</span></div></div>'
    )
    st.caption("Chronological splits · threshold chosen on validation only")
    risk = bundle.docs.get("risk_evaluation")
    left, right = st.columns([56, 44], gap="small")
    with left, card("aar"):
        aar_evaluation(bundle, reveal)
    with right, card("delay"):
        delay_evaluation(bundle, risk, snapshot)
    left, right = st.columns([56, 44], gap="small")
    with left, card("coverage"):
        coverage_section(bundle)
    with right, card("integrity"):
        integrity_section(bundle, snapshot, reveal)
    throughput = bundle.docs.get("throughput_evaluation")
    if throughput and st.session_state.get("preview-held"):
        with card("throughput"):
            throughput_evaluation(throughput)
    with card("impact"):
        impact_section(risk)
    with card("storms"):
        storm_section(risk)
    with card("failures"):
        card_title("Failure cases")
        cases = views.failure_cards(risk, bundle.docs.get("capacity_evaluation"))
        if not reveal:
            st.info("Failure cases contain observed outcomes. Turn on **Reveal outcomes** to view them.", icon="🔒")
        elif cases:
            failure_section(cases)
        else:
            st.info("No failure case published.")
    evidence_section(bundle)
    outcomes_bar(reveal, "evaluation", "Reveal held-out outcomes for retrospective inspection.")


def aar_evaluation(bundle: Bundle, reveal: bool = False) -> None:
    card_title("Arrival capacity · AAR RMSE", "Lower is better · arrivals/hour", glyph="plane")
    document = bundle.docs.get("capacity_evaluation")
    metrics = (document or {}).get("metrics") or []
    if metrics:
        st.dataframe(pd.DataFrame(metrics), hide_index=True)
        estimate_evaluation(bundle, reveal)
        return
    rows = [
        [escape(info["iata"]), f"+{lead}h", "—", "—", "Not available"]
        for info in AIRPORTS.values() for lead in SCORED_HORIZONS
    ]
    html(theme.table(["Airport", "Horizon", "Historical baseline", "Pooled tree model", "Status"], rows))
    theme.notice("<b>Genuine FAA AAR labels not loaded.</b> Sampled arrival counts cannot substitute for capacity labels.")
    capability = bundle.capability("AAR forecast")
    if capability.reasons:
        st.caption(capability.reasons[0])
    if document and document.get("requested_extract"):
        with st.expander("Inspect capacity requirements"):
            st.json(document["requested_extract"], expanded=True)
    estimate_evaluation(bundle, reveal)


def estimate_evaluation(bundle: Bundle, reveal: bool) -> None:
    """Capacity proxy, shown inside the existing capacity panel and never as AAR accuracy."""
    document = bundle.docs.get("capacity_estimate_evaluation")
    capability = bundle.capability("Capacity estimate (proxy)")
    if document is None:
        st.caption("Capacity estimate (proxy) not loaded: " + "; ".join(capability.reasons))
        return
    st.markdown(f"**{views.ESTIMATE_TITLE}** · model proxy")
    st.caption(
        f"Method {document.get('method')} · target {document.get('validation_target')} · run {capability.run_id}. "
        "Metrics compare a frozen training-only frontier with observed high-demand throughput (held-out 2025); "
        "they are not facility AAR accuracy. Uncertainty bounds are not estimated."
    )
    table = views.estimate_metrics(document)
    if not table.empty:
        st.dataframe(table, hide_index=True)
    cohorts = pd.DataFrame(document.get("cohorts") or [])
    if not cohorts.empty:
        cohorts = cohorts[cohorts["split"] == "test"]
        if reveal:
            st.dataframe(cohorts, hide_index=True)
        else:
            st.dataframe(
                cohorts[["airport", "weather_regime", "n_snapshots", "n_unique_hours", "mean_estimate"]], hide_index=True,
            )
            st.caption("Observed throughput by weather regime is hidden until **Reveal outcomes** is on.")
    for limitation in document.get("limitations", [])[:3]:
        st.caption(f"Limitation: {limitation}")


def delay_evaluation(bundle: Bundle, document: dict | None, snapshot: Snapshot | None) -> None:
    card_title("Departure delay model", "Target: departure delay over 45 minutes · ATL/DFW departures only", glyph="takeoff")
    if document is None:
        unavailable("Delay risk", bundle.problem("risk_evaluation"))
        return
    st.caption(f"Run {document['run_id']} · status {document['status']} · model {document.get('model')}")
    metrics = pd.DataFrame(document.get("metrics", []))
    if metrics.empty:
        st.info("No measured metrics published.")
        return
    if snapshot:
        scope = metrics[
            (metrics["airport"] == snapshot.airport.icao) & (metrics["horizon_hours"] == snapshot.horizon_hours)
        ]
        names = [("precision", "Precision"), ("recall", "Recall"), ("pr_auc", "PR-AUC"), ("brier", "Brier score")]
        for column, (name, label) in zip(st.columns(4, gap="small"), names):
            row = scope[scope["metric"] == name]
            if len(row):
                value = row.iloc[0]
                html(tile(label, f"{value['value']:.3f}", f"Baseline {value['baseline_value']:.3f} · n={value['n']:,}"), column)
            else:
                html(tile(label, "—", "Not loaded", "muted"), column)
        calibration(document, snapshot)
    predictions = bundle.table("predictions")
    if predictions is not None:
        mix = ", ".join(f"{count:,} {label.lower()}" for label, count in views.model_mix(predictions).items())
        st.caption(f"Held-out predictions by model: {mix}.")
    note = views.calibration_note(document)
    if note:
        st.caption(note)
    with st.expander("All metrics"):
        st.dataframe(metrics, hide_index=True)
    with st.expander("Full report (candidates, reliability, exclusions)"):
        st.json({k: v for k, v in document.items() if "failure" not in k.lower() and k != "metrics"}, expanded=False)


def calibration(document: dict, snapshot: Snapshot) -> None:
    rows = views.reliability_rows(document, snapshot.airport.icao, snapshot.horizon_hours)
    if rows:
        html(f'<div class="card-note">Calibration (predicted probability vs. observed rate) · {escape(snapshot.airport.iata)} +{snapshot.horizon_hours}h</div>')
        st.plotly_chart(plots.reliability(rows), key="reliability", **CHART)
    else:
        html(theme.empty("bars", "Calibration results not loaded", "Load held-out evaluation outputs to inspect probability reliability."))


def throughput_evaluation(document: dict) -> None:
    card_title("Observed arrivals forecast · NOT AAR", "Held pending team agreement · arrivals/hour of reporting carriers", glyph="landing")
    overall = document.get("overall") or {}
    st.caption(str(document.get("not_aar", "")))
    columns = ["airport", "horizon_hours", "n", "rmse_weather", "rmse_schedule_only", "rmse_baseline", "interval_coverage"]
    st.dataframe(pd.DataFrame(document.get("metrics", []))[columns], hide_index=True)
    if overall:
        st.caption(f"Overall RMSE {overall.get('rmse_weather', 0):.2f} against baseline {overall.get('rmse_baseline', 0):.2f}; interval coverage {overall.get('interval_coverage', 0):.1%} (nominal {(document.get('uncertainty') or {}).get('nominal', 0):.0%}).")


def impact_section(document: dict | None) -> None:
    card_title("Against the status quo")
    impact = (document or {}).get("impact")
    if not impact:
        unavailable("Impact comparison", "No baseline comparison is published.")
        return
    st.caption(
        f"Measured prediction comparison, not an operational saving. Status quo: "
        f"{impact.get('status_quo')} Basis: {impact.get('basis')}"
    )
    st.dataframe(pd.DataFrame(impact.get("comparisons", [])), hide_index=True)
    if impact.get("limitations"):
        st.write("Limitations:", impact["limitations"])
    if document.get("alert_rates"):
        st.markdown("**Alert rates**")
        st.dataframe(pd.DataFrame(document["alert_rates"]), hide_index=True)


def storm_section(document: dict | None) -> None:
    card_title("Storm-event cohorts")
    cohorts = (document or {}).get("storm_cohorts")
    if not cohorts:
        unavailable("Storm-event cohorts", "No storm cohort evaluation is published.")
        return
    st.caption("Retrospective NOAA annotation of held-out rows. Storm logs are never model inputs.")
    st.dataframe(views.storm_table(cohorts), hide_index=True)


def failure_section(cases: list) -> None:
    for case in cases:
        if not isinstance(case, dict):
            st.json(case, expanded=False)
            continue
        with st.container(border=True):
            kind = str(case.get("kind", "Earlier example")).replace("_", " ").capitalize()
            st.markdown(f"**{kind}** · {case.get('airport', 'unknown airport')} · flight {case.get('flight_id')}")
            if case.get("explanation"):
                st.write("Likely reason:", case["explanation"])
            if case.get("remedy"):
                st.write("What would help:", case["remedy"])
            details = {k: v for k, v in case.items() if k not in ("kind", "explanation", "remedy")}
            st.json(details, expanded=False)


def coverage_section(bundle: Bundle) -> None:
    card_title("Source coverage & provenance", "Readiness comes from manifests, hashes, schemas and keys, not file presence", glyph="database")
    st.dataframe(
        pd.DataFrame(
            {"Capability": c.name, "Status": STATUS_LABEL[c.status], "Run": c.run_id, "Reasons": "; ".join(c.reasons)}
            for c in bundle.capabilities
        ),
        hide_index=True,
    )


def integrity_section(bundle: Bundle, snapshot: Snapshot | None, reveal: bool) -> None:
    card_title("Replay integrity", "Checked now on the loaded artifacts", glyph="clipboard")
    checks = views.integrity_checks(bundle, snapshot, reveal)
    html("".join(
        f'<div class="check"><span>{escape(label)}</span><b class="{state}">{escape(result)}</b></div>'
        for label, state, result in checks
    ))


def evidence_section(bundle: Bundle) -> None:
    problems = [
        {"Publication": name, "Artifact": artifact, "Problem": "; ".join(reasons)}
        for name, group in bundle.groups.items()
        for artifact, reasons in group.problems.items()
    ]
    with st.expander(f"Artifact checks ({len(problems)} open)"):
        if problems:
            st.dataframe(pd.DataFrame(problems), hide_index=True)
        else:
            st.success("All artifacts passed.")
    for name, group in bundle.groups.items():
        if group.manifest:
            with st.expander(f"{name}: run {group.manifest['run_id']} ({group.manifest['status']})"):
                st.write("Generated:", group.manifest["generated_at_utc"])
                st.write("Limitations:", group.manifest.get("limitations", []))
                st.write("Missing inputs:", group.manifest.get("missing_inputs", []))
    for name in ("data_access", "provenance"):
        if name in bundle.docs:
            with st.expander(name):
                st.code(json.dumps(bundle.docs[name], indent=2))
