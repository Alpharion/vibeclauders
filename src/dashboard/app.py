"""Historical replay for an airport flow planner. Read-only: nothing is transmitted."""
from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from src.dashboard import live, plots, theme, views
from src.dashboard.data import SCORED_HORIZONS, Bundle, fingerprint, is_schedule_only, load_bundle
from src.dashboard.theme import card_title, grid, html, pill, tile
from src.dashboard.views import Snapshot, resolve_airport
from src.shared import AIRPORTS

REPO_ROOT = Path(__file__).resolve().parents[2]
STATUS_LABEL = {"available": "Available", "partial": "Partial", "unavailable": "Unavailable"}
HISTORICAL, LIVE = "Historical replay", "Live weather"


@st.cache_data(show_spinner="Validating published artifacts…", max_entries=2)
def cached_bundle(root: str, stamp: str) -> Bundle:
    return load_bundle(Path(root))


def data_root() -> Path:
    return Path(os.environ.get("DASHBOARD_DATA_ROOT", REPO_ROOT))


def fmt_time(value) -> str:
    return "unknown" if pd.isna(value) else pd.Timestamp(value).strftime("%Y-%m-%d %H:%M UTC")


def clock(value) -> str:
    return pd.Timestamp(value).strftime("%H:%M")


def unavailable(capability: str, reason: str) -> None:
    st.warning(f"**{capability} unavailable.** {reason}", icon="⛔")


def airport_name(icao: str) -> str:
    info = AIRPORTS[icao]
    return f"{info['iata']} · {info.get('name', icao)}"


def known(value, suffix: str = "", digits: int = 0) -> str:
    return "Unknown" if pd.isna(value) else f"{value:,.{digits}f}{suffix}"


# --- Page frame ---------------------------------------------------------------


def top_bar() -> str:
    left, right = st.columns([3, 1])
    codes = " / ".join(info["iata"] for info in AIRPORTS.values())
    badge = '<span class="badge amber">HISTORICAL · SAMPLE DATA</span>' if st.session_state.get("mode") != LIVE else ""
    html(f'<div class="brand"><b>Weather &amp; Traffic</b><span>{escape(codes)}</span>{badge}</div>', left)
    return right.radio("Mode", [HISTORICAL, LIVE], horizontal=True, key="mode", label_visibility="collapsed")


def controls(bundle: Bundle) -> tuple[Snapshot | None, int, bool]:
    index = views.replay_index(bundle)
    choices = [icao for icao in AIRPORTS if icao in set(index["airport"])] or list(AIRPORTS)
    airport_col, date_col, hour_col, lead_col, target_col = st.columns([2, 2, 1.6, 2, 1.3])
    icao = airport_col.selectbox("Airport", choices, key="airport", format_func=airport_name)
    airport = resolve_airport(icao)
    horizon = lead_col.radio(
        "Forecast lead (hours)", SCORED_HORIZONS, horizontal=True, key="horizon", format_func=lambda h: f"+{h}h",
    )

    st.session_state.setdefault("window", 6)
    rows = index[index["airport"] == icao]
    busiest = views.busiest_cutoffs(index, icao, horizon)
    st.sidebar.markdown("**Replay context**")
    if not rows.empty:
        jump_to(bundle, icao, busiest)
    window = st.sidebar.number_input("Planning window (hours)", 1, 24, key="window")
    reveal = st.sidebar.toggle(
        "Reveal outcomes", False, key="reveal",
        help="Actual outcomes stay hidden during replay until you choose to reveal them.",
    )
    st.sidebar.caption("Forecasts issued by cutoff · Outcomes " + ("revealed" if reveal else "hidden"))
    if rows.empty:
        return None, window, reveal

    default_cutoff = busiest["asof_utc"].iloc[0] if len(busiest) else rows["asof_utc"].iloc[0]
    counts = views.scored_counts(index, icao, horizon)
    dates = sorted(rows["asof_utc"].dt.strftime("%Y-%m-%d").unique())
    per_date = counts.groupby(counts.index.strftime("%Y-%m-%d")).sum()
    date_key = f"date-{icao}"
    st.session_state.setdefault(date_key, default_cutoff.strftime("%Y-%m-%d"))
    date = date_col.selectbox(
        "Replay cutoff", dates, key=date_key, format_func=lambda d: f"{d} · {per_date.get(d, 0)} scored",
    )
    on_date = rows[rows["asof_utc"].dt.strftime("%Y-%m-%d") == date]
    hours = sorted(on_date["asof_utc"].dt.strftime("%H:%M").unique())
    hour_key = f"hour-{icao}-{date}"
    if default_cutoff.strftime("%Y-%m-%d") == date:
        st.session_state.setdefault(hour_key, default_cutoff.strftime("%H:%M"))
    hour = hour_col.selectbox(
        "Hour (UTC)", hours, key=hour_key,
        format_func=lambda h: f"{h} · {counts.get(views.utc(f'{date} {h}'), 0)} scored",
    )
    snapshot = Snapshot(airport, views.utc(f"{date} {hour}"), horizon)
    html(f'<div class="target">Target<b>{clock(snapshot.target_hour_utc)} UTC</b></div>', target_col)
    return snapshot, window, reveal


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

    st.sidebar.selectbox(
        "Jump to", list(targets), index=None, key=f"jump-{icao}", on_change=apply,
        placeholder="Busiest cutoffs and published decision",
    )


def station_card(bundle: Bundle, icao: str, snapshot: Snapshot | None, active: bool) -> str:
    """One airport at the shared cutoff: observed conditions, then TAF category by lead."""
    info = AIRPORTS[icao]
    head = f'<div class="head">{escape(info["iata"])} · <span>{escape(info.get("name", icao))}</span></div>'
    outlook = views.airport_outlook(bundle, icao, snapshot.asof_utc) if snapshot else {}
    if not outlook:
        body = '<div class="line">No weather evidence at this cutoff.</div>'
    else:
        row = next(iter(outlook.values()))
        category = views.flight_category(row["obs_visibility_sm"], row["obs_ceiling_ft_agl"])
        gust = row["obs_wind_gust_kt"]
        wind = known(row["obs_wind_speed_kt"], " kt")
        if pd.notna(gust) and gust != row["obs_wind_speed_kt"]:
            wind += f", gust {gust:.0f}"
        chips = "".join(
            f"<span>+{lead}h</span>" + pill(
                views.flight_category(outlook[lead]["visibility_sm"], outlook[lead]["ceiling_ft_agl"])
                if lead in outlook else "Unknown"
            )
            for lead in SCORED_HORIZONS
        )
        body = (
            f'<div class="now">{pill(category)}<span>{known(row["temperature_c"], "°C")}</span></div>'
            f'<div class="line">Wind {escape(wind)}<br>Visibility {known(row["obs_visibility_sm"], " SM", 1)}'
            f'<br>Ceiling {escape(views.weather_display("obs_ceiling_ft_agl", row))}</div>'
            f'<div class="label">Forecast at cutoff</div><div class="chips">{chips}</div>'
        )
    return f'<div class="station {"active" if active else ""}">{head}{body}</div>'


def rail(bundle: Bundle, snapshot: Snapshot | None, selected: str, stations, sources) -> None:
    for icao in AIRPORTS:
        html(station_card(bundle, icao, snapshot, icao == selected), stations)
    html('<div class="card-title" style="margin-top:14px">Data sources</div>', sources)
    rows = "".join(
        f'<div class="source-row"><span class="dot {c.status}"></span>{escape(c.name)}: {STATUS_LABEL[c.status]}</div>'
        for c in bundle.capabilities
    )
    html(rows, sources)


def reveal_strip(reveal: bool) -> None:
    if not reveal:
        html(
            '<div class="banner quiet"><b>Actual outcomes hidden.</b> Replay shows forecasts and '
            "schedules only. Use Reveal outcomes in the side panel for retrospective review.</div>"
        )


# --- Overview -----------------------------------------------------------------


def overview_tab(bundle: Bundle, snapshot: Snapshot, window: int) -> None:
    iata = snapshot.airport.iata
    theme.title(
        "ATC overview",
        f"{iata} · Forecast picture for {clock(snapshot.target_hour_utc)}–"
        f"{clock(snapshot.target_hour_utc + pd.Timedelta(hours=1))} UTC",
    )
    map_col, side = st.columns([2.3, 1])
    with map_col, st.container(border=True):
        card_title("Operational map")
        html(weather_banner(bundle, snapshot))
        route_section(bundle, snapshot, window)
    with side:
        controller_snapshot(bundle, snapshot, window)


def weather_banner(bundle: Bundle, snapshot: Snapshot) -> str:
    row, reason = views.weather_feature_row(bundle, snapshot)
    iata = escape(snapshot.airport.iata)
    if row is None:
        return f'<div class="banner quiet">{iata} · {escape(reason)}</div>'
    if row["thunderstorm_flag"] == 1:
        return f'<div class="banner">{iata} · Thunderstorm forecast at the target hour</div>'
    if row["cond_thunderstorm_flag"] == 1:
        return f'<div class="banner">{iata} · Conditional thunderstorm group at the target hour</div>'
    return f'<div class="banner quiet">{iata} · No thunderstorm in the forecast for the target hour</div>'


def route_section(bundle: Bundle, snapshot: Snapshot, window: int) -> None:
    flights = bundle.table("flights")
    if flights is None:
        unavailable("Map", bundle.problem("flights"))
        return
    routes = views.route_counts(flights, snapshot.airport, snapshot.asof_utc, window)
    if routes.empty:
        st.info(f"No sampled flights are scheduled in the {window}-hour window after this cutoff.")
        return
    flagged = views.flagged_routes(views.risk_rows(bundle, snapshot), flights)
    figure, unmapped = plots.route_map(routes, snapshot.airport.iata, flagged=flagged)
    if figure is None:
        st.info("Map unavailable: no coordinates for the selected airport.")
        return
    st.plotly_chart(figure, key="routes")
    note = f"Schematic sampled connections for the {window}-hour window, not flown routes or live traffic. No radar layer."
    st.caption(f"{note} {unmapped} movements lack coordinates." if unmapped else note)


def controller_snapshot(bundle: Bundle, snapshot: Snapshot, window: int) -> None:
    html(f'<div class="card-title">{escape(snapshot.airport.iata)} · Controller snapshot</div>')
    with st.container(border=True):
        card_title("Departure risk", "Flights scored at this exact cutoff and lead")
        rows = views.risk_rows(bundle, snapshot)
        if rows is None or rows.empty:
            st.caption("No held-out prediction at this key.")
        else:
            st.metric("At or above threshold", f"{int(views.flagged(rows).sum())} of {len(rows)}")
    with st.container(border=True):
        card_title("Arrival capacity")
        row, reason = views.aar_row(bundle, snapshot)
        if row is None:
            st.caption(f"AAR not available. {reason}")
        else:
            st.metric("Predicted AAR (arrivals/hour)", f"{row['aar_pred']:.1f}")
            bounds = views.uncertainty(row)
            st.caption(f"Interval {bounds[0]:.1f}–{bounds[1]:.1f}" if bounds else "Uncertainty unknown")
    with st.container(border=True):
        card_title("Weather at target hour", "Forecast known at the cutoff")
        row, reason = views.weather_feature_row(bundle, snapshot)
        if row is None:
            st.caption(reason)
        else:
            html(grid(["Measure", "Forecast"], [
                ["Crosswind", f"{views.weather_display('crosswind_kt', row)} kt"],
                ["Tailwind", f"{views.weather_display('tailwind_kt', row)} kt"],
                ["Visibility", f"{views.weather_display('visibility_sm', row)} SM"],
                ["Gust", views.weather_display("wind_gust_kt", row)],
            ]))
    with st.container(border=True):
        card_title("Proposed response")
        response_summary(bundle, snapshot, window)


def response_summary(bundle: Bundle, snapshot: Snapshot, window: int) -> None:
    recommendations = bundle.docs.get("recommendations")
    if recommendations is None:
        st.caption("No decision output is available.")
    elif views.decision_mismatch(recommendations, snapshot.airport, snapshot.asof_utc, window):
        st.caption("No published decision for this selection. See Compare.")
    else:
        count = len(recommendations.get("recommendations", []))
        st.caption(f"{count} supported action(s). Missing inputs: {len(recommendations.get('missing_inputs', []))}. See Compare.")


# --- Weather ------------------------------------------------------------------


def weather_tab(bundle: Bundle, snapshot: Snapshot) -> None:
    theme.title("Weather outlook", f"{snapshot.airport.iata} · Published forecast across +3h, +6h and +12h")
    row, reason = views.weather_feature_row(bundle, snapshot)
    outlook = views.airport_outlook(bundle, snapshot.airport.icao, snapshot.asof_utc)
    if snapshot.airport.heading is None:
        row, reason = None, f"{snapshot.airport.icao} has no configured runway heading, so runway-relative wind is refused."
    else:
        st.caption(f"Runway-relative wind uses the fixed heading {snapshot.airport.heading:03d}°.")
    if row is None:
        unavailable("Cutoff-safe weather", reason)
    else:
        weather_tiles(row, snapshot)
    if outlook:
        condition_table(outlook, snapshot)
    weather = bundle.table("weather")
    if weather is not None:
        bulletins = views.bulletins_as_of(weather, snapshot)
        with st.expander(f"{len(bulletins)} bulletins known at cutoff and valid at target"):
            st.dataframe(bulletins, hide_index=True)


def weather_tiles(row: pd.Series, snapshot: Snapshot) -> None:
    lead = f"+{snapshot.horizon_hours}h forecast"
    storm = row["thunderstorm_flag"] == 1
    category = views.flight_category(row["visibility_sm"], row["ceiling_ft_agl"])
    tiles = [
        tile("Thunderstorm", "Forecast" if storm else "Not forecast", lead, "alert" if storm else ""),
        tile("Flight category", category, lead, "warn" if category != "VFR" else ""),
        tile("Crosswind", f"{views.weather_display('crosswind_kt', row)} kt", f"Heading {snapshot.airport.heading:03d}°"),
        tile("Tailwind", f"{views.weather_display('tailwind_kt', row)} kt", f"Heading {snapshot.airport.heading:03d}°"),
    ]
    for column, markup in zip(st.columns(4), tiles):
        html(markup, column)


def condition_table(outlook: dict[int, pd.Series], snapshot: Snapshot) -> None:
    leads = [lead for lead in SCORED_HORIZONS if lead in outlook]
    left, right = st.columns([1.4, 1])
    measures = [
        ("Flight category", lambda r: pill(views.flight_category(r["visibility_sm"], r["ceiling_ft_agl"]))),
        ("Visibility (SM)", lambda r: views.weather_display("visibility_sm", r)),
        ("Ceiling (ft AGL)", lambda r: views.weather_display("ceiling_ft_agl", r)),
        ("Wind (kt)", lambda r: views.weather_display("wind_speed_kt", r)),
        ("Gust (kt)", lambda r: views.weather_display("wind_gust_kt", r)),
        ("Crosswind (kt)", lambda r: views.weather_display("crosswind_kt", r)),
        ("Tailwind (kt)", lambda r: views.weather_display("tailwind_kt", r)),
        ("Precipitation", lambda r: views.weather_display("precip_flag", r)),
        ("Thunderstorm", lambda r: views.weather_display("thunderstorm_flag", r)),
        ("Conditional groups", lambda r: known(r["cond_groups"])),
    ]
    headers = ["Condition"] + [f"+{lead}h · {clock(outlook[lead]['target_hour_utc'])}" for lead in leads]
    rows = [[label] + [getter(outlook[lead]) for lead in leads] for label, getter in measures]
    highlight = leads.index(snapshot.horizon_hours) + 1 if snapshot.horizon_hours in leads else None
    with left, st.container(border=True):
        card_title("Conditions by lead", "Published TAF values, not modelled probabilities")
        html(grid(headers, rows, highlight))
    with right:
        with st.container(border=True):
            card_title("Ceiling by lead", "Point forecast. No uncertainty interval is published.")
            ceilings = [outlook[lead]["ceiling_ft_agl"] for lead in leads]
            if any(c < views.NO_CEILING_FT for c in ceilings):
                st.plotly_chart(plots.ceiling_by_lead([f"+{lead}h" for lead in leads], ceilings), key="ceiling")
            else:
                st.caption("No ceiling is forecast at any lead.")
        observed = outlook[leads[0]]
        with st.container(border=True):
            card_title("Observed at cutoff")
            category = views.flight_category(observed["obs_visibility_sm"], observed["obs_ceiling_ft_agl"])
            html(
                f"{pill(category)} &nbsp; {known(observed['obs_visibility_sm'], ' SM', 1)} · "
                f"{escape(views.weather_display('obs_ceiling_ft_agl', observed))} · "
                f"temperature {known(observed['temperature_c'], '°C', 1)}"
            )
            st.caption(f"METAR {fmt_time(observed['metar_observed_at_utc'])} · TAF {fmt_time(observed['taf_issued_at_utc'])}")


# --- Traffic ------------------------------------------------------------------


def traffic_tab(bundle: Bundle, snapshot: Snapshot, window: int, reveal: bool) -> None:
    theme.title("Traffic volumes", f"{snapshot.airport.iata} · Scheduled sample movements and departure risk")
    flights = bundle.table("flights")
    if flights is None:
        unavailable("Flight traffic", bundle.problem("flights"))
    else:
        movements = views.planning_movements(flights, snapshot.airport, snapshot.asof_utc, window)
        scored = views.scored_flights(flights, snapshot)
        coverage = movements["coverage"]
        tiles = [
            tile("Incoming", movements["arrivals"], f"SCHEDULED · {window} h from cutoff · {coverage}"),
            tile("Outgoing", movements["departures"], f"SCHEDULED · {window} h from cutoff · {coverage}"),
            tile("Airport movements", movements["movements"], "Arrivals plus departures, not unique flights"),
            tile("Target-hour departures", len(scored), f"SCHEDULED · {views.coverage_label(scored)}"),
        ]
        for column, markup in zip(st.columns(4), tiles):
            html(markup, column)
        with st.container(border=True):
            card_title("Hourly movements", "A sample cannot establish whole-airport demand. No traffic forecast is published.")
            st.plotly_chart(plots.traffic_bars(movements["hourly"], coverage), key="traffic")
            st.dataframe(movements["hourly"], hide_index=True)
    with st.container(border=True):
        reporting_traffic_section(bundle, snapshot, window, reveal)
    with st.container(border=True):
        risk_section(bundle, snapshot, reveal)


def reporting_traffic_section(bundle: Bundle, snapshot: Snapshot, window: int, reveal: bool) -> None:
    traffic = bundle.table("traffic_hourly")
    card_title("Reporting-carrier traffic")
    if traffic is None:
        unavailable("Reporting-carrier traffic", bundle.problem("traffic_hourly"))
        return
    rows = views.reporting_traffic(traffic, snapshot.airport, snapshot.asof_utc, window, reveal)
    if rows.empty:
        st.info("No reporting-carrier counts in this window.")
        return
    st.dataframe(rows, hide_index=True)
    st.caption(
        f"Population: {', '.join(map(str, traffic['population'].unique()))}. Reconstructed "
        "retrospectively, not known at the cutoff, so these counts are not queue demand."
    )


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
    st.plotly_chart(plots.risk_bars(rows, thresholds[0] if len(thresholds) == 1 else None), key="risk")
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


def compare_tab(bundle: Bundle, snapshot: Snapshot, window: int, reveal: bool) -> None:
    theme.title(
        "Forecast vs actual",
        f"{snapshot.airport.iata} · Forecast frozen {clock(snapshot.asof_utc)} UTC · "
        f"Event window {clock(snapshot.target_hour_utc)} UTC, +1 h",
    )
    with st.container(border=True):
        card_title("Proposed actions", "For human review. Nothing is transmitted.")
        decision_section(bundle, snapshot, window)
    if not reveal:
        st.info("This comparison uses observed outcomes. Turn on **Reveal outcomes** to view it.", icon="🔒")
        return
    with st.container(border=True):
        outcome_section(bundle, snapshot)
    with st.container(border=True):
        trends_section(bundle, snapshot)


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
    for column, markup in zip(st.columns(4), tiles):
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
        st.plotly_chart(plots.queue_lines(rows), key="queue")
        st.plotly_chart(plots.backlog_bars(rows), key="backlog")
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
    period = period_col.radio("Period", ["Week", "Month", "Day"], horizontal=True, key="trend-period")
    splits = sorted(metrics["split"].dropna().unique())
    chosen = split_col.multiselect("Splits", splits, default=splits, key="trend-splits")
    rollup = views.history_rollup(metrics[metrics["split"].isin(chosen)], period[0])
    st.plotly_chart(
        plots.trend_lines(rollup, "severe_delay_rate", "Severe-delay rate", "Share of eligible departures", True),
        key="trend-rate",
    )
    st.plotly_chart(
        plots.trend_lines(rollup, "delay_minutes_per_flight", "Positive delay per eligible flight", "Minutes"),
        key="trend-minutes",
    )
    st.dataframe(rollup, hide_index=True)
    aar_trend_section(bundle, snapshot)


def aar_trend_section(bundle: Bundle, snapshot: Snapshot) -> None:
    card_title("AAR observed versus predicted")
    rows = views.aar_trend(bundle.table("forecast"), snapshot.airport, snapshot.horizon_hours)
    if rows.empty:
        unavailable("AAR trend", "No held-out rows with a genuine observed AAR are published.")
        return
    st.plotly_chart(plots.aar_lines(rows, snapshot.airport.icao, snapshot.horizon_hours), key="aar-trend")
    st.dataframe(rows[["target_hour_utc", "aar_observed", "aar_pred"]], hide_index=True)


# --- Evaluation ---------------------------------------------------------------


def evaluation_tab(bundle: Bundle, snapshot: Snapshot | None, reveal: bool) -> None:
    theme.title("Evaluation & data coverage", "Measured prediction quality, separate from any simulated benefit")
    html(
        '<div class="steps"><div class="step">TRAIN · 2023<span>Jan – Dec 2023</span></div>'
        '<div class="step">VALIDATE · 2024<span>Jan – Dec 2024</span></div>'
        '<div class="step">TEST · Jan – Jul 2025<span>Held out</span></div></div>'
    )
    st.caption("Chronological splits · threshold chosen on validation only")
    risk = bundle.docs.get("risk_evaluation")
    left, right = st.columns(2)
    with left, st.container(border=True):
        aar_evaluation(bundle)
    with right, st.container(border=True):
        delay_evaluation(bundle, risk, snapshot)
    with st.container(border=True):
        impact_section(risk)
    with st.container(border=True):
        storm_section(risk)
    with st.container(border=True):
        card_title("Failure cases")
        cases = views.failure_cards(risk, bundle.docs.get("capacity_evaluation"))
        if not reveal:
            st.info("Failure cases contain observed outcomes. Turn on **Reveal outcomes** to view them.", icon="🔒")
        elif cases:
            failure_section(cases)
        else:
            st.info("No failure case published.")
    left, right = st.columns(2)
    with left, st.container(border=True):
        coverage_section(bundle)
    with right, st.container(border=True):
        integrity_section(bundle, snapshot, reveal)
    evidence_section(bundle)


def aar_evaluation(bundle: Bundle) -> None:
    card_title("Arrival capacity · AAR RMSE", "Lower is better · arrivals/hour")
    document = bundle.docs.get("capacity_evaluation")
    metrics = (document or {}).get("metrics") or []
    if metrics:
        st.dataframe(pd.DataFrame(metrics), hide_index=True)
        return
    rows = [
        [escape(info["iata"]), f"+{lead}h", "—", "—", "Not available"]
        for info in AIRPORTS.values() for lead in SCORED_HORIZONS
    ]
    html(grid(["Airport", "Lead", "Historical baseline", "Pooled tree model", "Status"], rows))
    html(
        '<div class="banner" style="margin-top:10px"><b>Genuine FAA AAR labels not loaded.</b> '
        "Sampled arrival counts cannot substitute for capacity labels.</div>"
    )
    st.caption(bundle.capability("AAR forecast").reasons[0] if bundle.capability("AAR forecast").reasons else "")


def delay_evaluation(bundle: Bundle, document: dict | None, snapshot: Snapshot | None) -> None:
    card_title("Departure delay model", "Target: departure delay over 45 minutes · ATL/DFW departures only")
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
        for column, (name, label) in zip(st.columns(4), names):
            row = scope[scope["metric"] == name]
            if len(row):
                value = row.iloc[0]
                html(tile(label, f"{value['value']:.3f}", f"Baseline {value['baseline_value']:.3f} · n={value['n']:,}"), column)
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
    card_title("Source coverage & provenance", "Readiness comes from manifests, hashes, schemas and keys, not file presence")
    st.dataframe(
        pd.DataFrame(
            {"Capability": c.name, "Status": STATUS_LABEL[c.status], "Run": c.run_id, "Reasons": "; ".join(c.reasons)}
            for c in bundle.capabilities
        ),
        hide_index=True,
    )


def integrity_section(bundle: Bundle, snapshot: Snapshot | None, reveal: bool) -> None:
    card_title("Replay integrity", "Checked now on the loaded artifacts")
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


# --- Live ---------------------------------------------------------------------


def live_screen() -> None:
    icao_col, fetch_col, badge_col = st.columns([2, 1, 3])
    icao = icao_col.selectbox("Airport", list(AIRPORTS), key="live-airport", format_func=airport_name)
    fetch_col.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
    if fetch_col.button("Fetch current weather", type="primary", key="live-fetch"):
        with st.spinner("Retrieving current weather…"):
            st.session_state["live_bundle"] = live.fetch_live_weather()
    html('<div style="padding-top:30px;text-align:right"><span class="badge cyan">OBSERVED · NO LIVE TRAFFIC</span></div>', badge_col)
    theme.title("Live weather", "Latest observations and source freshness. Separate from replay.")
    st.caption(
        "Current public METAR/TAF from the NOAA Aviation Weather Center. It changes no historical "
        "panel, and no current flight data is connected."
    )
    bundle = st.session_state.get("live_bundle")
    for name in AIRPORTS:
        html(live_station_card(bundle, name, name == icao), st.sidebar)
    if bundle is None:
        st.info("Nothing is fetched until you ask, so replay and offline demos need no network.")
        return
    st.caption(f"Retrieved {fmt_time(bundle['retrieved_at_utc'])}")
    for error in bundle["errors"]:
        st.warning(f"**Live source failed.** {error}", icon="⛔")
    live_observation(bundle, icao)
    live_forecast(bundle, icao)


def live_station_card(bundle: dict | None, icao: str, active: bool) -> str:
    info = AIRPORTS[icao]
    message = live.for_airport(bundle["metar"], icao) if bundle else None
    body = '<div class="line">No observation fetched.</div>'
    if message:
        category = message.get("fltCat") or "Unknown"
        category = category if category in ("VFR", "MVFR", "IFR", "LIFR") else "Unknown"
        body = (
            f'<div class="now">{pill(category)}<span>{escape(str(message.get("temp", "?")))}°C</span></div>'
            f'<div class="line">Wind {escape(str(message.get("wdir", "?")))}° / {escape(str(message.get("wspd", "?")))} kt'
            f'<br>Visibility {escape(str(message.get("visib", "?")))} SM</div>'
        )
    return (
        f'<div class="station {"active" if active else ""}"><div class="head">{escape(info["iata"])} · '
        f'<span>{escape(info.get("name", icao))}</span></div>{body}</div>'
    )


def live_observation(bundle: dict, icao: str) -> None:
    message = live.for_airport(bundle["metar"], icao)
    if message is None:
        st.info("No current observation returned for this airport.")
        return
    ceiling = live.ceiling_ft(message)
    columns = st.columns(5)
    columns[0].metric("Reported category", message.get("fltCat") or "Unknown")
    columns[1].metric("Temperature (°C)", message.get("temp", "Unknown"))
    columns[2].metric("Visibility (SM)", str(message.get("visib", "Unknown")))
    columns[3].metric("Wind", f"{message.get('wdir', '?')}° / {message.get('wspd', '?')} kt")
    columns[4].metric("Ceiling (ft)", "None reported" if ceiling is None else f"{ceiling:,}")
    age = live.observation_age_minutes(message, pd.Timestamp.now(tz="UTC"))
    if age is not None and age > live.STALE_OBSERVATION_MINUTES:
        st.warning(f"**Stale observation.** The latest report is {age:.0f} minutes old.", icon="⚠️")
    st.code(message.get("rawOb", "No raw message"), language=None)


def live_forecast(bundle: dict, icao: str) -> None:
    forecast = live.for_airport(bundle["taf"], icao)
    table = live.forecast_table(forecast)
    if table.empty:
        st.info("No current forecast returned for this airport.")
        return
    with st.container(border=True):
        card_title("Terminal forecast")
        st.dataframe(table, hide_index=True)
        st.caption(f"Issued {fmt_time(forecast.get('issueTime'))}. Conditional groups do not replace prevailing conditions.")
        st.code(forecast.get("rawTAF", "No raw message"), language=None)


# --- Entry point --------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="Weather & Traffic", page_icon="🛬", layout="wide", initial_sidebar_state="expanded")
    html(theme.CSS)
    mode = top_bar()
    if mode == LIVE:
        live_screen()
        return
    root = data_root()
    bundle = cached_bundle(str(root), fingerprint(root))
    stations = st.sidebar.container()
    snapshot, window, reveal = controls(bundle)
    rail(bundle, snapshot, st.session_state["airport"], stations, st.sidebar.container())
    tabs = st.tabs(["Overview", "Weather", "Traffic", "Compare", "Evaluation"])
    if snapshot is None:
        with tabs[0]:
            unavailable("Replay", "No snapshot is published.")
    else:
        with tabs[0]:
            overview_tab(bundle, snapshot, window)
            reveal_strip(reveal)
        with tabs[1]:
            weather_tab(bundle, snapshot)
        with tabs[2]:
            traffic_tab(bundle, snapshot, window, reveal)
        with tabs[3]:
            compare_tab(bundle, snapshot, window, reveal)
    with tabs[4]:
        evaluation_tab(bundle, snapshot, reveal)
    html('<div class="footnote">Decision support · Human review required · No operational commands transmitted · UTC throughout</div>')
