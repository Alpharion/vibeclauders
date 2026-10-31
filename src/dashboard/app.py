from datetime import datetime, time, timezone
from html import escape
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from src.shared import AIRPORTS
from src.dashboard import data, plots

CSS = """
<style>
.block-container{padding-top:1.8rem;max-width:1680px;padding-bottom:2rem}
header[data-testid=stHeader]{background:transparent}
[data-testid=stSidebar]{background:#131C26;border-right:1px solid #283545}
h1{font-size:1.95rem!important;letter-spacing:-.055rem} h2{font-size:1.35rem!important}
h3{font-size:1.03rem!important;font-weight:600!important}
[data-testid=stMetric]{background:#19232F;border:1px solid #2B394A;border-radius:10px;padding:16px}
[data-testid=stMetricLabel]{color:#A6B7C9;font-size:.8rem}
[data-testid=stMetricValue]{font-size:1.9rem;color:#E6F7FF}
.eyebrow{color:#58D4E7;font-size:11px;letter-spacing:2px;font-weight:700;margin-bottom:8px}
.subtitle{color:#9CAEC2;font-size:14px;margin-bottom:20px;max-width:900px}
.badge{display:inline-block;padding:5px 10px;border-radius:5px;background:#243343;color:#BCEFF8;font-size:11px;letter-spacing:.4px}
.badge.warn{background:#44321D;color:#FFD49C}
.station{padding:14px 16px;margin:8px 0;background:#19232F;border:1px solid #2A394A;border-radius:8px}
.station.active{border-color:#43D7EB;background:#1A2D3B}
.station b{font-size:16px}.station .muted{color:#93A7BD;font-size:12px;margin-top:6px}
.station .number{color:#7BE4F0;float:right;font-size:14px}
.empty{background:#17212C;border:1px dashed #3B5063;border-radius:10px;padding:22px;margin:10px 0 18px}
.empty strong{color:#D4E7F5}.empty p{color:#9EAFBF;font-size:13px;margin-bottom:0}
.legend{display:flex;gap:18px;color:#A4B4C6;font-size:12px;flex-wrap:wrap}
.footer{color:#879DB3;border-top:1px solid #2A394A;padding-top:14px;font-size:12px;margin-top:24px}
button[data-baseweb=tab]{font-size:14px!important;padding:12px 25px!important}
[data-testid=stDataFrame]{border:1px solid #293849;border-radius:8px}
</style>
"""

def empty(title, detail):
    st.markdown(f'<div class="empty"><strong>{escape(title)}</strong><p>{escape(detail)}</p></div>', unsafe_allow_html=True)

def stamp(value):
    try:
        return pd.Timestamp(value).tz_convert("UTC").strftime("%d %b %Y · %H:%M UTC")
    except (ValueError, TypeError):
        return str(value)

def number(value, suffix=""):
    return "—" if value is None or pd.isna(value) else f"{value:,.0f}{suffix}"

def weather_category(vis, ceiling):
    if vis is None or pd.isna(vis):
        return "Unknown"
    if vis < 1 or (ceiling is not None and ceiling < 500):
        return "LIFR"
    if vis < 3 or (ceiling is not None and ceiling < 1000):
        return "IFR"
    if vis <= 5 or (ceiling is not None and ceiling <= 3000):
        return "MVFR"
    return "VFR" if ceiling is not None else "Unknown ceiling"

def live_forecast_table(records, airport):
    rows = []
    for message in records:
        if message.get("icaoId") != airport:
            continue
        for forecast in message.get("fcsts", []):
            row = {"From UTC": pd.to_datetime(forecast.get("timeFrom"), unit="s", utc=True), "To UTC": pd.to_datetime(forecast.get("timeTo"), unit="s", utc=True), "Condition": forecast.get("changeIndicator") or "Prevailing", "Wind kt": forecast.get("wspd"), "Direction °": forecast.get("wdir"), "Gust kt": forecast.get("wgst"), "Visibility SM": forecast.get("visib"), "Weather": forecast.get("wxString", "—")}
            row["Clouds"] = "; ".join(f"{x.get('cover', '')} {x.get('base', '—')} ft" for x in forecast.get("clouds", []))
            rows.append(row)
    return pd.DataFrame(rows)

def live_view(airport):
    st.caption("Public METAR/TAF from NOAA Aviation Weather Center. No current flight-demand feed is connected.")
    if st.button("Fetch / refresh public weather", type="primary", key="refresh_weather"):
        data.live_weather.clear()
        with st.spinner("Retrieving current airport weather…"):
            st.session_state["live_bundle"] = data.live_weather()
    bundle = st.session_state.get("live_bundle")
    if not bundle:
        empty("Live weather ready to connect", "Fetch the public AWC observations and forecasts. Historical flights will not be overlaid as current traffic.")
        return
    st.caption("Retrieved " + stamp(bundle["retrieved_at_utc"]))
    for error in bundle.get("errors", []):
        st.warning(error)
    message = next((x for x in bundle.get("metar", []) if x.get("icaoId") == airport), None)
    if message:
        cols = st.columns(5)
        cols[0].metric("Reported category", message.get("fltCat") or "—")
        cols[1].metric("Temperature", number(message.get("temp"), " °C"))
        cols[2].metric("Visibility", str(message.get("visib", "—")) + " SM")
        cols[3].metric("Wind", f"{message.get('wdir', '—')}° / {message.get('wspd', '—')} kt")
        ceilings = [c["base"] for c in message.get("clouds", []) if c.get("cover") in ["BKN", "OVC", "VV"] and c.get("base") is not None]
        cols[4].metric("Ceiling", number(min(ceilings), " ft") if ceilings else "Not reported")
        observed = pd.to_datetime(message.get("obsTime"), unit="s", utc=True)
        age = (pd.Timestamp.now(tz="UTC") - observed).total_seconds()/60
        st.caption(f"Observation {stamp(observed)} · age {max(0, age):.0f} min · receipt {message.get('receiptTime', 'unknown')}")
        if age > 90:
            st.warning("The latest returned observation is more than 90 minutes old.")
        with st.expander("Original METAR and source"):
            st.code(message.get("rawOb", "No raw message"), language=None)
            st.write(f"{data.PUBLIC_WEATHER}/metar?ids={airport}&format=json")
    else:
        empty("Current observation unavailable", "The provider returned no METAR for this airport.")
    st.subheader("Location-specific terminal forecast")
    forecast = live_forecast_table(bundle.get("taf", []), airport)
    if not forecast.empty:
        st.dataframe(forecast, hide_index=True, width="stretch")
        st.caption("Conditional TEMPO / probability groups are displayed separately; they do not replace prevailing conditions.")
    else:
        empty("Current forecast unavailable", "No decoded TAF periods were returned for the selected airport.")
    for message in bundle.get("taf", []):
        if message.get("icaoId") == airport:
            st.caption(f"Forecast issued {stamp(pd.to_datetime(message.get('issueTime'), unit='s', utc=True))}")
            with st.expander("Original TAF"):
                st.code(message.get("rawTAF", "No raw message"), language=None)

def historical_weather(airport, asof, horizon):
    weather, error = data.artifact_table("artifacts/capacity/weather.parquet", ("airport", "issued_at_utc", "valid_from_utc", "valid_to_utc", "kind", "source"))
    capacity, _ = data.artifact_table("artifacts/capacity/forecast.parquet", ("airport", "asof_utc", "target_hour_utc", "horizon_hours", "aar_pred", "status", "source"))
    forecast = data.scope_predictions(capacity, airport, asof, horizon)
    left, right = st.columns([1, 3.1])
    with left:
        st.subheader("Airport watchlist")
        for code, info in AIRPORTS.items():
            available = pd.DataFrame()
            if not weather.empty:
                target = asof + pd.Timedelta(hours=horizon)
                available = weather[(weather.airport == code) & (weather.issued_at_utc <= asof) & (weather.valid_from_utc <= target) & (weather.valid_to_utc > target) & (weather.kind == "forecast")]
            label = "Forecast not connected" if available.empty else f"{len(available)} source period(s) at +{horizon}h"
            st.markdown(f'<div class="station {"active" if code == airport else ""}"><b>{info["iata"]}</b> <span class="number">+{horizon}h</span><div class="muted">{info["name"]}<br>{escape(label)}</div></div>', unsafe_allow_html=True)
        st.caption("Challenge runway headings")
        st.write("ATL **080°** · DFW **180°**")
        st.caption("These fixed scoring assumptions do not describe a verified current runway configuration.")
    with right:
        st.subheader(f"{AIRPORTS[airport]['iata']} · Location forecast")
        st.caption(f"Evidence cutoff {stamp(asof)} · target {stamp(asof + pd.Timedelta(hours=horizon))}")
        c1, c2, c3 = st.columns(3)
        pred = pd.to_numeric(forecast.get("aar_pred", pd.Series(dtype=float)), errors="coerce")
        c1.metric("Predicted AAR", number(pred.iloc[0], " / h") if len(pred) else "—")
        c2.metric("Forecast horizon", f"{horizon} hours")
        c3.metric("Source periods", "—" if weather.empty else len(weather[(weather.airport == airport) & (weather.issued_at_utc <= asof)]))
        if weather.empty:
            empty("Archived forecasts not connected", "The data agent's timestamped weather artifact will populate this view. Weather merged into the challenge CSV is not treated as a forecast available at this cutoff.")
            if error:
                st.caption(error)
            return
        eligible = weather[(weather.airport == airport) & (weather.issued_at_utc <= asof) & (weather.valid_to_utc > asof - pd.Timedelta(hours=1)) & (weather.valid_from_utc <= asof + pd.Timedelta(hours=12))].copy()
        if eligible.empty:
            empty("No eligible evidence for this cutoff", "Choose a time within the archived coverage. Later-issued forecasts are excluded.")
            return
        # Use the most recent eligible bulletin; retain conditional groups in the source table.
        fc = eligible[eligible.kind == "forecast"]
        if not fc.empty:
            latest = fc.issued_at_utc.max()
            eligible = pd.concat([eligible[eligible.kind == "observation"], fc[fc.issued_at_utc == latest]])
        prevailing = eligible
        if "condition" in prevailing:
            prevailing = prevailing[prevailing.condition.fillna("Prevailing").isin(["Prevailing", "FM", "", "observation"])]
        for row in [("visibility_sm", "Visibility · SM", "ceiling_ft_agl", "Ceiling · ft AGL"), ("wind_speed_kt", "Wind speed · kt", "wind_gust_kt", "Gust · kt")]:
            cols = st.columns(2)
            for col, field, title in [(cols[0], row[0], row[1]), (cols[1], row[2], row[3])]:
                with col:
                    if field in prevailing and prevailing[field].notna().any():
                        st.plotly_chart(plots.weather_chart(prevailing, field, title, asof), width="stretch", key=f"weather_{field}")
                    else:
                        empty(title, "This field is unavailable in the eligible evidence.")
        with st.expander("Evidence and conditional forecast periods"):
            st.dataframe(eligible, hide_index=True, width="stretch")
        if forecast.empty:
            st.info("AAR prediction is unavailable for this exact cutoff and horizon.")

def traffic_view(flights, airport, asof, horizon, mode, reveal):
    if mode == "Live weather":
        empty("Live traffic is not connected", "Current weather does not establish current flight demand. Switch to historical replay for the supplied sample and any connected model outputs.")
        return
    end = asof + pd.Timedelta(hours=horizon)
    moves = data.movements(flights, airport, asof, end)
    risk, risk_error = data.artifact_table("artifacts/risk/predictions.parquet", ("flight_id", "airport", "asof_utc", "horizon_hours", "probability_severe_delay", "threshold"))
    selected = data.validate_risk(data.scope_predictions(risk, airport, asof, horizon))
    moves = moves.merge(selected[["flight_id", "probability_severe_delay", "threshold"]] if not selected.empty else pd.DataFrame(columns=["flight_id", "probability_severe_delay", "threshold"]), how="left", on="flight_id", validate="many_to_one")
    moves["flagged"] = moves.probability_severe_delay.ge(moves.threshold)
    sample = flights.coverage.ne("complete").any()
    st.subheader("Airport flight volumes")
    st.caption(f"{stamp(asof)} → {stamp(end)} · {'SAMPLE movements — not complete airport demand' if sample else 'Complete coverage as declared by provider'}")
    cols = st.columns(5)
    for col, title, value in zip(cols, ["Scheduled arrivals", "Scheduled departures", "Total movements", "Scored departures", "Flagged >45-min risk"], [int(moves.direction.eq("Inbound").sum()), int(moves.direction.eq("Outbound").sum()), len(moves), len(moves[moves.probability_severe_delay.notna()]) if len(selected) else None, int(moves.flagged.sum()) if len(selected) else None]):
        col.metric(title, number(value))
    st.caption("Below-threshold risk is not proof that a flight is unaffected. Inbound queue impact needs complete demand and capacity evidence.")
    a, b, c = st.columns([1, 1, 2])
    direction = a.segmented_control("Direction", ["All", "Inbound", "Outbound"], default="All", key="direction") or "All"
    status = b.segmented_control("Risk", ["All", "Flagged", "Unscored"], default="All", key="risk_filter") or "All"
    show_context = c.checkbox("Show both airports' flight connections", value=False)
    filtered = moves.copy()
    if direction != "All":
        filtered = filtered[filtered.direction == direction]
    if status == "Flagged":
        filtered = filtered[filtered.flagged]
    elif status == "Unscored":
        filtered = filtered[filtered.probability_severe_delay.isna()]
    left, right = st.columns([1, 1.3])
    with left:
        rows = []
        for code, info in AIRPORTS.items():
            m = data.movements(flights, code, asof, end)
            rows.append({"Airport": info["iata"], "Arrivals": int(m.direction.eq("Inbound").sum()), "Departures": int(m.direction.eq("Outbound").sum()), "Total": len(m), "Coverage": "Sample" if sample else "Complete"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Airport movements count each endpoint; do not sum them as unique network flights.")
        st.plotly_chart(plots.volume_chart(moves, asof, end), width="stretch", key="volumes")
    with right:
        st.subheader("Geographic connections")
        map_moves = filtered
        if show_context:
            other = "KDFW" if airport == "KATL" else "KATL"
            context = data.movements(flights, other, asof, end)
            context["flagged"] = False
            map_moves = pd.concat([filtered, context], ignore_index=True).drop_duplicates(["flight_id", "origin", "dest"])
        fig, missing = plots.traffic_map(map_moves, airport)
        st.plotly_chart(fig, width="stretch", key="traffic_map")
        st.markdown('<div class="legend"><span>● Grey: unscored</span><span style="color:#43D7EB">● Cyan: scored, not flagged</span><span style="color:#FF6F7D">● Red: flagged</span></div>', unsafe_allow_html=True)
        st.caption(f"Schematic airport connections, not flown paths or live aircraft positions. {missing} movement(s) lack map coordinates.")
    capacity, _ = data.artifact_table("artifacts/capacity/forecast.parquet", ("airport", "asof_utc", "target_hour_utc", "horizon_hours", "aar_pred", "status", "source"))
    cap = data.scope_predictions(capacity, airport, asof, horizon)
    if cap.empty:
        empty("Demand versus capacity: awaiting AAR model", "Sample arrival counts are not airport capacity. No runway-capacity shortfall or airport-wide recovery estimate is inferred from this sample.")
    else:
        st.subheader("Predicted arrival acceptance rate")
        st.dataframe(cap, hide_index=True, width="stretch")
        st.caption("Capacity is supplied by the model artifact. Comparing it with sampled movement counts would not establish an airport-wide shortfall.")
    st.subheader("Flights in selected window")
    columns = ["carrier", "flight_number", "origin", "dest", "direction", "movement_utc", "probability_severe_delay"]
    if reveal:
        columns += [x for x in ["dep_delay_min", "arr_delay_min", "cancelled", "diverted"] if x in filtered]
    st.dataframe(filtered[columns].sort_values("movement_utc"), hide_index=True, width="stretch", column_config={"probability_severe_delay": st.column_config.ProgressColumn("P(departure delay >45m)", min_value=0, max_value=1, format="percent")})
    if selected.empty:
        st.caption(risk_error or "No valid risk predictions for this exact airport, cutoff and horizon.")
    st.download_button("Download this filtered flight view", filtered[columns].to_csv(index=False).encode("utf-8"), "selected-flight-view.csv", "text/csv")

def compare_view(airport, asof, horizon, mode):
    st.subheader("Early decisions, with an inspectable basis")
    st.caption("Ground metering and verified candidate actions. No automatic clearances or unverified diversion rankings.")
    if mode == "Live weather":
        empty("Live recommendations unavailable", "Current filed demand, capacity and aircraft eligibility inputs are not connected.")
        return
    rec = data.report("artifacts/risk/recommendations.json")
    matching = rec.get("airport") in [airport, AIRPORTS[airport]["iata"]] and pd.to_datetime(rec.get("asof_utc"), utc=True, errors="coerce") == asof and rec.get("horizon_hours") == horizon
    if rec.get("status") != "available" or not matching:
        empty("No supported recommendation for this snapshot", "The recommendation agent must supply matching demand, capacity, known initial backlog and eligible-flight evidence. No hold, reroute or diversion benefit is assumed.")
        missing = rec.get("missing_inputs", []) or ["Verified demand and initial backlog", "Matching AAR forecast", "Validated candidate options and eligibility"]
        for item in missing:
            st.write(f"• {item}")
    else:
        items = rec.get("recommendations", [])
        if not items:
            st.info("No additional intervention is supplied for this snapshot.")
        for index, item in enumerate(items):
            with st.container(border=True):
                st.subheader(item.get("action", "Proposed action"))
                st.write(item.get("rationale", "Rationale not supplied"))
                c1, c2 = st.columns(2)
                c1.write("**Baseline**")
                c1.json(item.get("baseline", {}))
                c2.write("**Proposed · simulated effects**")
                c2.json(item.get("proposed", {}))
                with st.expander("Affected flights, evidence and prerequisites"):
                    st.json({key: item.get(key) for key in ["affected_flight_ids", "revised_times", "prerequisites", "source"]})
                st.caption("Decision support for qualified review; no action is sent to operational systems.")
    st.divider()
    a, b, c = st.columns(3)
    with a:
        st.markdown("**01 · Establish the shortfall**")
        st.caption("Weather forecast → verified capacity → complete demand → queue and recovery.")
    with b:
        st.markdown("**02 · Compare eligible actions**")
        st.caption("Meter not-yet-departed flights. Check available future capacity and preserve movement counts.")
    with c:
        st.markdown("**03 · Review secondary impacts**")
        st.caption("Consider alternate demand and previously unaffected traffic only when the required evidence exists.")

def evidence_view():
    st.subheader("Data readiness & honest evaluation")
    st.caption("Measured prediction quality is separate from simulated intervention benefits.")
    rows = []
    for name, relative in [("Archived weather", "artifacts/capacity/weather.parquet"), ("AAR forecasts", "artifacts/capacity/forecast.parquet"), ("Delay predictions", "artifacts/risk/predictions.parquet"), ("Recommendations", "artifacts/risk/recommendations.json")]:
        rows.append({"Component": name, "Artifact": relative, "Status": "Connected" if (data.ROOT / relative).exists() else "Not connected"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    for label, path in [("Arrival capacity", "artifacts/capacity/evaluation.json"), ("Departure delay risk", "artifacts/risk/evaluation.json")]:
        with st.container(border=True):
            st.subheader(label)
            report = data.report(path)
            if report.get("metrics"):
                st.dataframe(pd.DataFrame(report["metrics"]), hide_index=True, width="stretch")
                st.write("Split:", report.get("split", "Not supplied"))
                st.write("Model:", report.get("model", "Not supplied"))
            else:
                st.info("No measured model evaluation supplied yet.")
            for limitation in report.get("limitations", []):
                st.caption(str(limitation))
    provenance = data.report("data/processed/provenance.json")
    if provenance.get("sources"):
        st.dataframe(pd.DataFrame(provenance["sources"]), hide_index=True, width="stretch")
    with st.expander("Public data sources and ownership", expanded=True):
        st.markdown("""
- **Historical forecasts / observations:** [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/request/taf.php) — data agent.
- **Public flight performance:** [BTS TranStats](https://www.transtats.bts.gov/) — data agent; supplied CSV bootstraps the UI.
- **Genuine AAR / demand:** [FAA ASPM](https://www.aspm.faa.gov/) — data agent; access remains to be verified.
- **Storm-event history:** [NOAA NCEI](https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/) — retrospective annotation, not advance features.
- **Current weather:** [AWC METAR / TAF API](https://aviationweather.gov/data/api/) — dashboard live-weather retrieval.
- **Airport locations:** [OpenFlights](https://github.com/jpatokal/openflights/blob/master/data/airports.dat) — public coordinate metadata.
""")
    st.caption("The supplied CSV has 148,273 flights and 25,299 ATL/DFW-related records. It has no explicit AAR labels, wind direction or forecast issue timestamps.")

def main():
    st.set_page_config(page_title="Weather & Traffic | Airport planning", page_icon="✈", layout="wide", initial_sidebar_state="expanded")
    st.markdown(CSS, unsafe_allow_html=True)
    flights, error = data.flights()
    if error:
        st.error(error)
    if flights.empty:
        st.warning("Connect a valid flight dataset to enable historical replay.")
        evidence_view()
        return
    with st.sidebar:
        st.markdown("### ◈ WEATHER / TRAFFIC")
        st.caption("Airport planning workspace")
        st.divider()
        mode = st.radio("Workspace", ["Historical replay", "Live weather"], key="workspace")
        airport = st.selectbox("Airport", list(AIRPORTS), format_func=lambda x: f"{AIRPORTS[x]['iata']} · {AIRPORTS[x]['name']}")
        lo, hi = flights.scheduled_dep_utc.min(), flights.scheduled_dep_utc.max()
        # The final UTC date can contain only overnight flights from the last source day.
        default_day = max(lo.date(), (hi - pd.Timedelta(days=1)).date())
        selected_date = st.date_input("Replay date · UTC", value=default_day, min_value=lo.date(), max_value=hi.date(), disabled=mode == "Live weather")
        hour = st.slider("Planning cutoff · UTC hour", 0, 23, 14, disabled=mode == "Live weather")
        horizon = st.segmented_control("Forecast horizon", [3, 6, 12], default=6, format_func=lambda x: f"+{x}h") or 6
        asof = pd.Timestamp(datetime.combine(selected_date, time(hour)), tz="UTC")
        reveal = st.checkbox("Reveal actual outcomes", value=False, disabled=mode == "Live weather", help="Expose historical outcomes only for comparison; they are never input to the forecast views.")
        st.divider()
        st.markdown("**Coverage**")
        st.caption(f"{len(flights):,} target-airport flight records\n\n{lo:%d %b %Y} — {hi:%d %b %Y}")
        st.caption("Flight sample ≠ complete airport demand. No fabricated predictions.")
        if st.button("Reload model artifacts"):
            st.cache_data.clear()
            st.rerun()
    st.markdown('<div class="eyebrow">AIRPORT OPERATIONS · DECISION SUPPORT</div>', unsafe_allow_html=True)
    title, status = st.columns([4, 1])
    title.title(f"Weather & Traffic / {AIRPORTS[airport]['iata']}")
    status.markdown(f'<span class="badge {"warn" if mode == "Historical replay" else ""}">{"HISTORICAL · SAMPLE DATA" if mode == "Historical replay" else "LIVE WEATHER · NO LIVE TRAFFIC"}</span>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Understand the forecast. See exposed demand. Review supported actions.</div>', unsafe_allow_html=True)
    st.caption(f"{stamp(asof) if mode == 'Historical replay' else 'Current AWC source timestamps'} · {horizon}-hour horizon · {'Outcomes revealed for evaluation' if reveal else 'Actual outcomes hidden'}")
    weather_tab, traffic_tab, compare_tab, evidence_tab = st.tabs(["Weather", "Traffic", "Compare", "Evidence & evaluation"])
    with weather_tab:
        if mode == "Live weather":
            live_view(airport)
        else:
            historical_weather(airport, asof, horizon)
    with traffic_tab:
        traffic_view(flights, airport, asof, horizon, mode, reveal)
    with compare_tab:
        compare_view(airport, asof, horizon, mode)
    with evidence_tab:
        evidence_view()
    st.markdown('<div class="footer">Planning prototype · Verified evidence where available · Human review required · No operational commands are transmitted</div>', unsafe_allow_html=True)
