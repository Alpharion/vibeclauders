"""Plotly figures. Airport colours follow registry order, so a filter never repaints them."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.shared import AIRPORTS

REFERENCE_PATH = Path(__file__).resolve().parents[2] / "data" / "reference" / "airports.json"

SERIES = ["#22B8F0", "#A78BFA", "#4ADE9A"]
FLAG = "#F2B95D"
INK = "#E7EEF6"
INK_SECONDARY = "#AFC1D2"
GRID = "#2B4257"
SURFACE = "rgba(0,0,0,0)"


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


def risk_bars(rows: pd.DataFrame, threshold: float | None) -> go.Figure:
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
    if threshold is not None:  # Mixed models have one threshold each; the table flags them.
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


@lru_cache(maxsize=1)
def airport_points() -> dict[str, tuple[float, float]]:
    """IATA to (latitude, longitude). Airports without coordinates are simply absent."""
    records = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))["airports"]
    points = {
        r["iata"]: (r["latitude"], r["longitude"])
        for r in records
        if r.get("iata") and r.get("latitude") is not None and r.get("longitude") is not None
    }
    for info in AIRPORTS.values():
        points.setdefault(info["iata"], (info["lat"], info["lon"]))
    return points


def great_circle(start: tuple[float, float], end: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    """Display connection between two points, not a flown or proposed route."""

    def unit(point):
        lat, lon = np.radians(point)
        return np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])

    a, b = unit(start), unit(end)
    angle = np.arccos(np.clip(a @ b, -1, 1))
    if angle < 1e-8:
        return np.array([start[0], end[0]]), np.array([start[1], end[1]])
    t = np.linspace(0, 1, 28)[:, None]
    xyz = (np.sin((1 - t) * angle) * a + np.sin(t * angle) * b) / np.sin(angle)
    lat = np.degrees(np.arctan2(xyz[:, 2], np.hypot(xyz[:, 0], xyz[:, 1])))
    return lat, np.degrees(np.arctan2(xyz[:, 1], xyz[:, 0]))


def route_map(routes: pd.DataFrame, selected_iata: str, points=None, flagged=frozenset()) -> tuple[go.Figure | None, int]:
    """Return the map and the number of movements lacking coordinates."""
    points = airport_points() if points is None else points
    if selected_iata not in points:
        return None, int(routes["flights"].sum())
    figure, unmapped, seen, codes = go.Figure(), 0, set(), {selected_iata}
    for route in routes.itertuples():
        if route.origin not in points or route.dest not in points:
            unmapped += route.flights
            continue
        codes.update((route.origin, route.dest))
        lat, lon = great_circle(points[route.origin], points[route.dest])
        is_flagged = (route.origin, route.dest) in flagged
        group = "Flagged departure" if is_flagged else route.direction
        color = FLAG if is_flagged else (SERIES[0] if route.direction == "Arrival" else SERIES[1])
        label = f"{route.origin} → {route.dest}: {route.flights} scheduled {route.direction.lower()}(s)"
        figure.add_scattergeo(
            lat=lat, lon=lon, mode="lines", name=group, legendgroup=group, showlegend=group not in seen,
            line={"color": color, "width": 2, "dash": "dash" if is_flagged else "solid"},
            text=[label] * len(lat), hovertemplate="%{text}<extra></extra>",
        )
        seen.add(group)
    ordered = sorted(codes)
    figure.add_scattergeo(
        lat=[points[c][0] for c in ordered], lon=[points[c][1] for c in ordered], text=ordered,
        mode="markers+text", textposition="top center", textfont={"color": INK, "size": 12},
        marker={"size": [15 if c == selected_iata else 8 for c in ordered], "color": INK, "line": {"color": SERIES[0], "width": 2}},
        showlegend=False, hovertemplate="%{text}<extra></extra>",
    )
    figure.update_geos(
        scope="north america", showland=True, landcolor="#16293A", showlakes=True, lakecolor="#0A1520",
        bgcolor="rgba(0,0,0,0)", showcountries=True, countrycolor=GRID, showsubunits=True, subunitcolor=GRID,
        showcoastlines=True, coastlinecolor=GRID, lataxis_range=[22, 50], lonaxis_range=[-125, -65],
    )
    _layout(figure, "", "", 470)
    figure.update_layout(hovermode="closest", margin={"l": 0, "r": 0, "t": 8, "b": 0})
    return figure, unmapped


def ceiling_by_lead(leads: list[str], ceilings: list[float]) -> go.Figure:
    figure = go.Figure(
        go.Scatter(
            x=leads, y=ceilings, mode="lines+markers+text", text=[f"{c:,.0f} ft" for c in ceilings],
            textposition="top center", textfont={"color": INK}, line={"color": SERIES[0], "width": 2},
            marker={"size": 9}, hovertemplate="%{x}: %{y:,.0f} ft<extra></extra>",
        )
    )
    _layout(figure, "", "Ceiling (ft AGL)", 250)
    figure.update_layout(margin={"l": 56, "r": 20, "t": 22, "b": 34}, hovermode="closest")
    return figure


def aar_lines(rows: pd.DataFrame, icao: str, horizon: int) -> go.Figure:
    figure = go.Figure()
    for column, name, color in (
        ("aar_observed", "Observed AAR", SERIES[0]), ("aar_pred", "Predicted AAR", SERIES[1])
    ):
        figure.add_scatter(
            x=rows["target_hour_utc"], y=rows[column], name=name, mode="lines",
            line={"color": color, "width": 2},
        )
    return _layout(figure, f"{icao}: held-out AAR at +{horizon} h", "Arrivals per hour")


def trend_lines(rollup: pd.DataFrame, column: str, title: str, y_title: str, percent=False) -> go.Figure:
    figure = go.Figure()
    for index, icao in enumerate(AIRPORTS):
        color = SERIES[index % len(SERIES)]
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
