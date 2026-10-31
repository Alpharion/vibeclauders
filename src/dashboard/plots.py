"""Plotly figures. Airport colours follow registry order, so a filter never repaints them."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src.shared import AIRPORTS

SERIES = ["#3987e5", "#d95926"]
AIRPORT_COLORS = dict(zip(AIRPORTS, SERIES))
INK = "#f0efec"
INK_SECONDARY = "#c3c2b7"
GRID = "#3a3a37"
SURFACE = "#10151D"


def _layout(figure: go.Figure, title: str, y_title: str, height: int = 320) -> go.Figure:
    figure.update_layout(
        title={"text": title, "font": {"size": 15, "color": INK}},
        template=None,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"color": INK_SECONDARY},
        height=height,
        margin={"l": 56, "r": 20, "t": 72, "b": 44},
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0},
        bargap=0.3,
        bargroupgap=0.08,
    )
    figure.update_xaxes(gridcolor=SURFACE, linecolor=GRID)
    figure.update_yaxes(title=y_title, gridcolor=GRID, zeroline=False, rangemode="tozero")
    return figure


def risk_bars(rows: pd.DataFrame, threshold: float) -> go.Figure:
    ordered = rows.sort_values("probability_severe_delay")
    labels = ordered["flight_id"].str[:8]
    if "flight_number" in ordered:
        labels = ordered["carrier"].fillna("").astype(str) + ordered["flight_number"].fillna("").astype(str)
        labels = labels.where(labels != "", ordered["flight_id"].str[:8])
    figure = go.Figure(
        go.Bar(
            x=ordered["probability_severe_delay"],
            y=labels,
            orientation="h",
            marker={"color": SERIES[0], "cornerradius": 4},
            hovertemplate="%{y}: %{x:.1%}<extra></extra>",
        )
    )
    figure.add_vline(
        x=threshold, line={"color": INK, "dash": "dot", "width": 2},
        annotation_text=f"Threshold {threshold:.3f}", annotation_font_color=INK,
    )
    _layout(figure, "Severe-delay probability, flights in target hour", "", 150 + 26 * len(rows))
    figure.update_layout(hovermode="closest")
    figure.update_xaxes(title="Probability of departure delay over 45 min", tickformat=".0%")
    figure.update_yaxes(type="category")
    return figure


def traffic_bars(hourly: pd.DataFrame, coverage: str) -> go.Figure:
    figure = go.Figure()
    for index, column in enumerate(("arrivals", "departures")):
        figure.add_bar(
            x=hourly["hour_utc"], y=hourly[column], name=column.title(),
            marker={"color": SERIES[index], "cornerradius": 4},
        )
    return _layout(figure, f"Scheduled movements per hour ({coverage} traffic)", "Movements")


def queue_lines(rows: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    figure.add_scatter(
        x=rows["target_hour_utc"], y=rows["demand_count"], name="Arrival demand",
        line={"color": SERIES[0], "width": 2}, mode="lines+markers", marker={"size": 8},
    )
    figure.add_scatter(
        x=rows["target_hour_utc"], y=rows["capacity"], name="Capacity (floored AAR)",
        line={"color": SERIES[1], "width": 2}, mode="lines+markers", marker={"size": 8},
    )
    return _layout(figure, "Arrival demand versus predicted capacity", "Arrivals per hour")


def backlog_bars(rows: pd.DataFrame) -> go.Figure:
    figure = go.Figure(
        go.Bar(
            x=rows["target_hour_utc"], y=rows["end_backlog"],
            marker={"color": SERIES[0], "cornerradius": 4},
            hovertemplate="%{y} aircraft<extra></extra>",
        )
    )
    return _layout(figure, "Simulated end-of-hour arrival backlog", "Aircraft")


def trend_lines(rollup: pd.DataFrame, column: str, title: str, y_title: str, percent=False) -> go.Figure:
    figure = go.Figure()
    for icao, color in AIRPORT_COLORS.items():
        rows = rollup[rollup["airport"] == icao]
        if rows.empty:
            continue
        figure.add_scatter(
            x=rows["period"], y=rows[column], name=icao, mode="lines+markers",
            line={"color": color, "width": 2}, marker={"size": 8},
            customdata=rows["eligible_departures"],
            hovertemplate=f"{icao}: %{{y:{'.1%' if percent else '.1f'}}} (n=%{{customdata}})<extra></extra>",
        )
    _layout(figure, title, y_title)
    if percent:
        figure.update_yaxes(tickformat=".0%")
    return figure
