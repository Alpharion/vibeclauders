"""Plotly figures. Airport colours follow registry order, so a filter never repaints them."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.dashboard.theme import TOKENS
from src.shared import AIRPORTS

REFERENCE_PATH = Path(__file__).resolve().parents[2] / "data" / "reference" / "airports.json"

SERIES = [TOKENS["cyan"], TOKENS["violet"], TOKENS["green"]]
FLAG = TOKENS["amber"]
CATEGORY_COLORS = {
    "VFR": TOKENS["cat-vfr"], "MVFR": TOKENS["cat-mvfr"], "IFR": TOKENS["cat-ifr"], "LIFR": TOKENS["cat-lifr"],
    "Unknown": TOKENS["text-secondary"],
}
INK = TOKENS["text-primary"]
INK_SECONDARY = TOKENS["text-secondary"]
GRID = TOKENS["border"]
SURFACE = "rgba(0,0,0,0)"
SCHEDULED = "rgba(241,245,249,.13)"
CONFIG = {"displayModeBar": False, "responsive": True}


def _layout(figure: go.Figure, title: str, y_title: str, height: int = 320) -> go.Figure:
    figure.update_layout(
        title={"text": title, "font": {"size": 15, "color": INK}},
        template=None,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"color": INK_SECONDARY, "family": "Inter, system-ui, sans-serif", "size": 12},
        height=height,
        margin={"l": 56, "r": 20, "t": 72, "b": 44},
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0},
        bargap=0.3,
        bargroupgap=0.08,
    )
    figure.update_xaxes(gridcolor=SURFACE, linecolor=GRID, tickcolor=GRID)
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


def category_bars(frequency: dict[str, dict[str, float] | None], leads: list[int], clocks: list[str]) -> go.Figure:
    """One stacked bar per lead, so conditions read in time order from the top."""
    labels = [f"+{lead}h · {clock}" for lead, clock in zip(leads, clocks)]
    gap = {"color": TOKENS["bg-card"], "width": 2}
    figure = go.Figure()
    for category, color in CATEGORY_COLORS.items():
        if category == "Unknown":
            continue
        values = [(frequency[lead] or {}).get(category) for lead in leads]
        figure.add_bar(
            y=labels, x=values, name=category, orientation="h", marker={"color": color, "line": gap},
            text=[f"{v:.0%}" if v and v >= 0.06 else "" for v in values], textposition="inside",
            textfont={"color": TOKENS["text-on-accent"]}, hovertemplate=f"{category}: %{{x:.1%}}<extra></extra>",
        )
    _layout(figure, "", "", 240)
    figure.update_layout(barmode="stack", hovermode="closest", margin={"l": 92, "r": 12, "t": 34, "b": 30}, bargap=0.35)
    figure.update_xaxes(tickformat=".0%", range=[0, 1])
    figure.update_yaxes(title="", autorange="reversed", gridcolor=SURFACE)
    return figure


def hourly_volume(rows: pd.DataFrame, name: str, color: str, asof: pd.Timestamp, target: pd.Timestamp) -> go.Figure:
    """Observed, scheduled, saved forecast and any revealed actual, each a separate mark."""
    figure = go.Figure()
    figure.add_bar(
        x=rows["hour_utc"], y=rows[f"{name}_scheduled"], name="Scheduled", marker={"color": SCHEDULED, "cornerradius": 3},
        text=rows[f"{name}_scheduled"], textposition="inside", insidetextanchor="start", textfont={"color": INK_SECONDARY, "size": 11},
        hovertemplate="Scheduled %{y}<extra></extra>",
    )
    forecast = rows[rows[f"{name}_forecast"].notna()]
    if not forecast.empty:
        figure.add_scatter(
            x=forecast["hour_utc"], y=forecast[f"{name}_forecast"], name="Forecast", mode="markers+text",
            marker={"color": color, "size": 10}, text=[f"{v:.0f}" for v in forecast[f"{name}_forecast"]],
            textposition="top right", textfont={"color": INK},
            error_y={
                "type": "data", "symmetric": False, "color": color, "thickness": 2, "width": 5,
                "array": forecast[f"{name}_upper"] - forecast[f"{name}_forecast"],
                "arrayminus": forecast[f"{name}_forecast"] - forecast[f"{name}_lower"],
            },
            hovertemplate="Forecast %{y:.1f}<extra></extra>",
        )
    figure.add_scatter(
        x=rows["hour_utc"], y=rows[f"{name}_observed"], name="Observed", mode="lines+markers+text",
        line={"color": INK, "width": 2}, marker={"size": 8, "color": INK},
        text=[f"{v:.0f}" if pd.notna(v) else "" for v in rows[f"{name}_observed"]], textposition="top center",
        textfont={"color": INK}, hovertemplate="Observed %{y:.0f}<extra></extra>",
    )
    if rows[f"{name}_actual"].notna().any():
        figure.add_scatter(
            x=rows["hour_utc"], y=rows[f"{name}_actual"], name="Actual (revealed)", mode="lines+markers",
            line={"color": INK, "width": 2, "dash": "dot"}, marker={"size": 8, "color": TOKENS["bg-card"], "line": {"color": INK, "width": 2}},
            hovertemplate="Actual %{y:.0f}<extra></extra>",
        )
    # add_vline's annotation does Timestamp + int arithmetic that pandas rejects; draw the same
    # dotted cutoff line as a shape and position its label separately
    cutoff_x = (pd.Timestamp(asof) - pd.Timedelta(minutes=30)).isoformat()
    figure.add_shape(type="line", x0=cutoff_x, x1=cutoff_x, y0=0, y1=1, xref="x", yref="paper",
                     line={"color": INK_SECONDARY, "dash": "dot", "width": 1})
    figure.add_annotation(x=cutoff_x, y=1, xref="x", yref="paper", text="Cutoff", showarrow=False,
                          xanchor="left", yanchor="bottom", font={"color": INK_SECONDARY})
    figure.add_vrect(x0=target - pd.Timedelta(minutes=30), x1=target + pd.Timedelta(minutes=30), fillcolor=color, opacity=0.1, line_width=0)
    _layout(figure, "", "Flights / hour", 300)
    figure.update_layout(barmode="overlay", margin={"l": 48, "r": 12, "t": 34, "b": 30}, hovermode="x unified")
    figure.update_xaxes(tickformat="%H", dtick=3_600_000, title="Hour (UTC)")
    return figure


def forecast_actual_bars(groups: list[tuple[str, float | None, float | None]]) -> go.Figure:
    """Saved forecast against actual. A missing forecast stays absent rather than drawn at zero."""
    labels = [g[0] for g in groups]
    figure = go.Figure()
    figure.add_bar(
        x=labels, y=[g[1] for g in groups], name="Forecast saved at cutoff",
        marker={"color": "rgba(40,198,244,.12)", "line": {"color": SERIES[0], "width": 2}},
        text=[f"{g[1]:.0f}" if g[1] is not None else "No forecast" for g in groups], textposition="outside",
        textfont={"color": SERIES[0]}, hovertemplate="Forecast %{y:.1f}<extra></extra>",
    )
    figure.add_bar(
        x=labels, y=[g[2] for g in groups], name="Actual", marker={"color": INK},
        text=[f"{g[2]:.0f}" if g[2] is not None else "Missing" for g in groups], textposition="outside",
        textfont={"color": INK}, hovertemplate="Actual %{y:.0f}<extra></extra>",
    )
    _layout(figure, "", "Flights", 210)
    figure.update_layout(barmode="group", bargap=0.45, bargroupgap=0.12, margin={"l": 44, "r": 12, "t": 30, "b": 26}, hovermode="closest")
    high = max([v for g in groups for v in g[1:] if v is not None] or [1])
    figure.update_yaxes(range=[0, high * 1.3])
    return figure


def ceiling_by_lead(leads: list[str], ceilings: list[float], lower=None, upper=None) -> go.Figure:
    """Published point forecast; a band appears only when a model publishes bounds."""
    figure = go.Figure()
    if lower is not None and upper is not None:
        figure.add_scatter(x=leads, y=upper, mode="lines", line={"width": 0}, hoverinfo="skip", showlegend=False)
        figure.add_scatter(
            x=leads, y=lower, mode="lines", line={"width": 0}, fill="tonexty", fillcolor="rgba(40,198,244,.2)",
            name="P10–P90", hoverinfo="skip",
        )
    figure.add_scatter(
        x=leads, y=ceilings, mode="lines+markers+text", text=[f"{c:,.0f} ft" for c in ceilings],
        textposition="top center", textfont={"color": INK}, line={"color": SERIES[0], "width": 2},
        marker={"size": 9}, hovertemplate="%{x}: %{y:,.0f} ft<extra></extra>", showlegend=False,
    )
    figure.add_hline(y=1000, line={"color": FLAG, "dash": "dash", "width": 1}, annotation_text="IFR below 1,000 ft", annotation_font_color=FLAG)
    _layout(figure, "", "Ceiling (ft AGL)", 220)
    figure.update_yaxes(range=[0, max([*ceilings, *(upper or [])]) * 1.3])
    figure.update_layout(margin={"l": 56, "r": 20, "t": 22, "b": 34}, hovermode="closest")
    return figure


def reliability(rows: list[dict]) -> go.Figure:
    """Predicted probability against observed rate. Point size is left constant: n is in the tooltip."""
    figure = go.Figure()
    high = max(max(r["mean_probability"], r["observed_severe_rate"]) for r in rows) * 1.1
    figure.add_scatter(x=[0, high], y=[0, high], mode="lines", line={"color": GRID, "dash": "dash"}, hoverinfo="skip", showlegend=False)
    figure.add_scatter(
        x=[r["mean_probability"] for r in rows], y=[r["observed_severe_rate"] for r in rows], mode="lines+markers",
        line={"color": SERIES[0], "width": 2}, marker={"size": 8}, customdata=[r["n"] for r in rows], showlegend=False,
        hovertemplate="Predicted %{x:.1%}, observed %{y:.1%} (n=%{customdata})<extra></extra>",
    )
    _layout(figure, "", "Observed rate", 190)
    figure.update_layout(margin={"l": 52, "r": 12, "t": 10, "b": 40}, hovermode="closest")
    figure.update_xaxes(title="Predicted probability", tickformat=".0%")
    figure.update_yaxes(tickformat=".0%")
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
