"""Historical replay for an airport flow planner. Read-only: nothing is transmitted."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from src.dashboard import plots, views
from src.dashboard.data import (
    SCORED_HORIZONS, WEATHER_FEATURES, Bundle, fingerprint, is_schedule_only, load_bundle,
)
from src.dashboard.views import Snapshot, resolve_airport
from src.shared import AIRPORTS

REPO_ROOT = Path(__file__).resolve().parents[2]
STATUS_MARK = {"available": "✅ Available", "partial": "⚠️ Partial", "unavailable": "⛔ Unavailable"}
WEATHER_LABELS = {
    "crosswind_kt": "Crosswind (kt)", "tailwind_kt": "Tailwind (kt)",
    "wind_speed_kt": "Wind (kt)", "wind_gust_kt": "Gust (kt)", "visibility_sm": "Visibility (SM)",
    "ceiling_ft_agl": "Ceiling (ft AGL)", "temperature_c": "Temperature (°C)",
    "precip_flag": "Precipitation", "thunderstorm_flag": "Thunderstorm",
}


@st.cache_data(show_spinner="Validating published artifacts…", max_entries=2)
def cached_bundle(root: str, stamp: str) -> Bundle:
    return load_bundle(Path(root))


def data_root() -> Path:
    return Path(os.environ.get("DASHBOARD_DATA_ROOT", REPO_ROOT))


def fmt_time(value) -> str:
    return "unknown" if pd.isna(value) else pd.Timestamp(value).strftime("%Y-%m-%d %H:%M UTC")


def unavailable(capability: str, reason: str) -> None:
    st.warning(f"**{capability} unavailable.** {reason}", icon="⛔")


def sidebar(bundle: Bundle) -> tuple[Snapshot | None, int, bool]:
    st.sidebar.title("Replay snapshot")
    index = views.replay_index(bundle)
    choices = [icao for icao in AIRPORTS if icao in set(index["airport"])] or list(AIRPORTS)
    icao = st.sidebar.selectbox("Airport", choices, key="airport")
    airport = resolve_airport(icao)
    horizon = st.sidebar.radio(
        "Forecast lead (hours)", SCORED_HORIZONS, index=0, horizontal=True, key="horizon",
    )
    window = st.sidebar.number_input("Planning window (hours)", 1, 24, 6, key="window")
    reveal = st.sidebar.toggle(
        "Reveal outcomes", False, key="reveal",
        help="Actual outcomes stay hidden during replay until you choose to reveal them.",
    )
    rows = index[index["airport"] == icao]
    if rows.empty:
        st.sidebar.info("No replay cutoffs are published for this airport.")
        return None, window, reveal

    dates = sorted(rows["asof_utc"].dt.strftime("%Y-%m-%d").unique())
    scored = rows[(rows["horizon_hours"] == horizon) & (rows["predictions"] > 0)]
    default_cutoff = scored.loc[scored["predictions"].idxmax(), "asof_utc"] if len(scored) else rows["asof_utc"].iloc[0]
    date = st.sidebar.selectbox(
        "Cutoff date (UTC)", dates, index=dates.index(default_cutoff.strftime("%Y-%m-%d")),
        key=f"date-{icao}",
    )
    on_date = rows[rows["asof_utc"].dt.strftime("%Y-%m-%d") == date]
    hours = sorted(on_date["asof_utc"].dt.strftime("%H:%M").unique())
    default_hour = default_cutoff.strftime("%H:%M")
    hour = st.sidebar.selectbox(
        "Cutoff hour (UTC)", hours, index=hours.index(default_hour) if default_hour in hours else 0,
        key=f"hour-{icao}-{date}",
    )
    return Snapshot(airport, views.utc(f"{date} {hour}"), horizon), window, reveal


def header(bundle: Bundle, snapshot: Snapshot | None) -> None:
    st.title("Arrival & departure risk replay")
    st.caption(
        "For an ATC / airport flow planner reviewing a historical cutoff. "
        "Decision support only: every advisory needs human review and no action is sent."
    )
    states = [f"{c.name}: {STATUS_MARK[c.status]}" for c in bundle.capabilities]
    st.markdown(" · ".join(states))
    if snapshot:
        st.info(
            f"**{snapshot.airport.icao}** · cutoff {fmt_time(snapshot.asof_utc)} · "
            f"+{snapshot.horizon_hours} h lead · scored departures in "
            f"[{fmt_time(snapshot.target_hour_utc)}, +1 h)"
        )


def forecast_tab(bundle: Bundle, snapshot: Snapshot, reveal: bool) -> None:
    st.subheader("Weather at the target hour")
    st.caption(f"Runway-relative wind uses the fixed heading {snapshot.airport.heading:03d}°.")
    row, reason = views.weather_feature_row(bundle, snapshot)
    if row is None:
        unavailable("Cutoff-safe weather", reason)
    else:
        columns = st.columns(5)
        for index, name in enumerate(WEATHER_FEATURES):
            value = "Unknown" if pd.isna(row[name]) else f"{row[name]:g}"
            columns[index % 5].metric(WEATHER_LABELS[name], value)
        st.caption(f"Latest input available {fmt_time(row['available_at_utc'])} · source {row['source_id']}")
    weather = bundle.table("weather")
    if weather is not None:
        bulletins = views.bulletins_as_of(weather, snapshot)
        with st.expander(f"{len(bulletins)} bulletins known at cutoff and valid at target"):
            st.dataframe(bulletins, hide_index=True)

    st.subheader("Predicted airport arrival rate")
    row, reason = views.aar_row(bundle, snapshot)
    if row is None:
        unavailable("AAR forecast", f"{reason} This is an unmet core requirement; no proxy is shown.")
    else:
        bounds = views.uncertainty(row)
        st.metric("Predicted AAR (arrivals/hour)", f"{row['aar_pred']:.1f}")
        st.caption(
            (f"Interval {bounds[0]:.1f}–{bounds[1]:.1f}" if bounds else "Uncertainty unknown")
            + f" · model {row['model_version']} · features available {fmt_time(row['features_available_at_utc'])}"
        )

    st.subheader("Departure severe-delay risk")
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
    threshold = float(rows["threshold"].iloc[0])
    flagged = int((rows["probability_severe_delay"] >= threshold).sum())
    left, middle, right = st.columns(3)
    left.metric("Flights scored", len(rows))
    middle.metric("At or above threshold", flagged)
    right.metric("Selected threshold", f"{threshold:.3f}")
    kinds = rows["model_kind"].unique()
    if all(is_schedule_only(kind) for kind in kinds):
        st.warning(
            "**Schedule-only model.** It uses no weather, so repeated scores across leads say "
            "nothing about weather sensitivity.", icon="⚠️",
        )
    st.caption(
        f"Applies to departures from {snapshot.airport.iata} only; inbound flights are never scored. "
        f"Model {', '.join(map(str, rows['model_version'].unique()))} · run {rows['run_id'].iloc[0]} · "
        f"coverage {', '.join(map(str, rows['coverage'].unique()))}. Probabilities, not delay minutes."
    )
    st.plotly_chart(plots.risk_bars(rows, threshold), key="risk")
    flights = bundle.table("flights")
    table = rows
    if flights is not None and reveal:
        table = rows.merge(flights[["flight_id", *views.OUTCOME_COLUMNS]], how="left", on="flight_id")
    shown = [c for c in table.columns if c not in ("airport", "asof_utc", "target_hour_utc", "horizon_hours", "run_id")]
    st.dataframe(views.mask_outcomes(table[shown], reveal), hide_index=True)


def traffic_tab(bundle: Bundle, snapshot: Snapshot, window: int) -> None:
    flights = bundle.table("flights")
    if flights is None:
        unavailable("Flight traffic", bundle.problem("flights"))
        return
    scored = views.scored_flights(flights, snapshot)
    st.subheader("Scored hour")
    st.metric(f"Departures scheduled from {snapshot.airport.iata} in the target hour", len(scored))
    st.caption(f"Coverage: {views.coverage_label(scored)}.")

    st.subheader(f"Cumulative planning window: {window} h from cutoff")
    movements = views.planning_movements(flights, snapshot.airport, snapshot.asof_utc, window)
    arrivals, departures, total = st.columns(3)
    arrivals.metric("Arrivals", movements["arrivals"])
    departures.metric("Departures", movements["departures"])
    total.metric("Airport movements", movements["movements"])
    st.caption(
        f"Coverage: {movements['coverage']}. Movements count arrivals plus departures, not unique "
        "flights, and a sample cannot establish whole-airport demand. This window is separate from "
        "the scored hour."
    )
    st.plotly_chart(plots.traffic_bars(movements["hourly"], movements["coverage"]), key="traffic")
    st.dataframe(movements["hourly"], hide_index=True)


def decision_tab(bundle: Bundle, snapshot: Snapshot, window: int) -> None:
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


def trends_tab(bundle: Bundle, reveal: bool) -> None:
    metrics = bundle.table("normalized_metrics")
    if metrics is None:
        unavailable("Historical trends", bundle.problem("normalized_metrics"))
        return
    if not reveal:
        st.info("Historical trends use observed outcomes. Turn on **Reveal outcomes** to view them.", icon="🔒")
        return
    st.caption(
        "Observed sample cohorts by UTC period, not whole-airport impact or forecasts. Severe rate "
        "and minutes per flight use eligible departures (non-cancelled, known delay) as denominator."
    )
    period = st.radio("Period", ["Week", "Month", "Day"], horizontal=True, key="trend-period")
    splits = sorted(metrics["split"].dropna().unique())
    chosen = st.multiselect("Splits", splits, default=splits, key="trend-splits")
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
    st.subheader("AAR observed versus predicted")
    unavailable(
        "AAR trend",
        "The contract has no published observed-AAR column for held-out rows (contract change requested).",
    )


def evaluation_section(title: str, document: dict | None, missing: str) -> None:
    st.subheader(title)
    if document is None:
        unavailable(title, missing)
        return
    st.caption(f"Run {document['run_id']} · status {document['status']} · model {document.get('model')}")
    st.write("Split:", document.get("split"))
    metrics = pd.DataFrame(document.get("metrics", []))
    if metrics.empty:
        st.info("No measured metrics published.")
    else:
        st.dataframe(metrics, hide_index=True)
    with st.expander("Full report (candidates, reliability, exclusions)"):
        visible = {k: v for k, v in document.items() if "failure" not in k.lower() and k != "metrics"}
        st.json(visible, expanded=False)


def evaluation_tab(bundle: Bundle, reveal: bool) -> None:
    st.caption("Measured prediction quality. It is separate from any simulated operational benefit.")
    evaluation_section("Delay risk", bundle.docs.get("risk_evaluation"), bundle.problem("risk_evaluation"))
    evaluation_section("AAR capacity", bundle.docs.get("capacity_evaluation"), bundle.problem("capacity_evaluation"))
    st.subheader("Failure cases")
    cases = views.find_failure_cases(bundle.docs.get("risk_evaluation"))
    cases += views.find_failure_cases(bundle.docs.get("capacity_evaluation"))
    if not reveal:
        st.info("Failure cases contain observed outcomes. Turn on **Reveal outcomes** to view them.", icon="🔒")
    elif cases:
        st.json(cases, expanded=False)
    else:
        st.info("No failure case published.")


def evidence_tab(bundle: Bundle) -> None:
    st.subheader("Capability readiness")
    st.caption("Determined by validating manifests, hashes, schemas and keys; file presence alone counts for nothing.")
    st.dataframe(
        pd.DataFrame(
            {
                "Capability": c.name,
                "Status": STATUS_MARK[c.status],
                "Run": c.run_id,
                "Reasons": "; ".join(c.reasons),
            }
            for c in bundle.capabilities
        ),
        hide_index=True,
    )
    st.subheader("Artifact checks")
    problems = [
        {"Publication": name, "Artifact": artifact, "Problem": "; ".join(reasons)}
        for name, group in bundle.groups.items()
        for artifact, reasons in group.problems.items()
    ]
    st.dataframe(pd.DataFrame(problems), hide_index=True) if problems else st.success("All artifacts passed.")
    st.subheader("Publications")
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


def main() -> None:
    st.set_page_config(page_title="Flow replay", page_icon="🛬", layout="wide")
    root = data_root()
    bundle = cached_bundle(str(root), fingerprint(root))
    snapshot, window, reveal = sidebar(bundle)
    header(bundle, snapshot)
    tabs = st.tabs(["Forecast & risk", "Traffic", "Decision support", "Trends", "Evaluation", "Evidence"])
    with tabs[0]:
        forecast_tab(bundle, snapshot, reveal) if snapshot else unavailable("Replay", "No snapshot is published.")
    with tabs[1]:
        traffic_tab(bundle, snapshot, window) if snapshot else unavailable("Traffic", "No snapshot is published.")
    with tabs[2]:
        decision_tab(bundle, snapshot, window) if snapshot else unavailable("Decision support", "No snapshot is published.")
    with tabs[3]:
        trends_tab(bundle, reveal)
    with tabs[4]:
        evaluation_tab(bundle, reveal)
    with tabs[5]:
        evidence_tab(bundle)
