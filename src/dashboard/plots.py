import numpy as np
import pandas as pd
import plotly.graph_objects as go
from src.shared import AIRPORTS
from src.dashboard.data import airports

CYAN, PURPLE, AMBER, RED, GREY = "#43D7EB", "#A69AF5", "#F2B95D", "#FF6F7D", "#7E8EA2"

def style(fig, height=330):
    fig.update_layout(template="plotly_dark", height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=12, r=12, t=26, b=12), font=dict(family="Arial", color="#DCE6F1", size=12), legend=dict(orientation="h", y=1.12), hovermode="x unified")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#263442", zerolinecolor="#263442")
    return fig

def volume_chart(moves, start, end):
    bins = pd.date_range(start.floor("h"), end.ceil("h"), freq="h", inclusive="left")
    fig = go.Figure()
    for direction, colour in [("Inbound", CYAN), ("Outbound", PURPLE)]:
        counts = moves[moves.direction == direction].groupby(moves.movement_utc.dt.floor("h")).size().reindex(bins, fill_value=0)
        fig.add_bar(x=bins, y=counts, name=direction, marker_color=colour)
    fig.update_layout(barmode="group")
    fig.update_yaxes(title="Scheduled sample movements", dtick=1)
    return style(fig)

def arc(lat1, lon1, lat2, lon2):
    """Great-circle display connection, not a flown or proposed route."""
    a = np.array([np.cos(np.radians(lat1))*np.cos(np.radians(lon1)), np.cos(np.radians(lat1))*np.sin(np.radians(lon1)), np.sin(np.radians(lat1))])
    b = np.array([np.cos(np.radians(lat2))*np.cos(np.radians(lon2)), np.cos(np.radians(lat2))*np.sin(np.radians(lon2)), np.sin(np.radians(lat2))])
    angle = np.arccos(np.clip(np.dot(a, b), -1, 1))
    if angle < 1e-8:
        return [lat1, lat2], [lon1, lon2]
    t = np.linspace(0, 1, 28)
    xyz = (np.sin((1-t)*angle)[:, None]*a + np.sin(t*angle)[:, None]*b)/np.sin(angle)
    return np.degrees(np.arctan2(xyz[:, 2], np.sqrt(xyz[:, 0]**2+xyz[:, 1]**2))), np.degrees(np.arctan2(xyz[:, 1], xyz[:, 0]))

def traffic_map(moves, selected):
    lookup, fig = airports(), go.Figure()
    groups = moves.groupby(["origin", "dest"])
    codes = set()
    missing = 0
    for (origin, dest), group in groups:
        if origin not in lookup or dest not in lookup:
            missing += len(group)
            continue
        codes.update([origin, dest])
        a, b = lookup[origin], lookup[dest]
        lat, lon = arc(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
        scored = group.get("probability_severe_delay", pd.Series(dtype=float)).dropna()
        flagged = int(group.get("flagged", pd.Series(dtype=bool)).fillna(False).sum())
        colour = RED if flagged else (CYAN if len(scored) else GREY)
        hover = f"{origin} → {dest}<br>{len(group)} scheduled sample flight(s)<br>{len(scored)} scored · {flagged} flagged"
        fig.add_trace(go.Scattergeo(lat=lat, lon=lon, mode="lines", line=dict(color=colour, width=2 if flagged else 1.3), opacity=.9 if flagged else .55, text=[hover]*len(lat), hovertemplate="%{text}<extra></extra>", showlegend=False))
    codes.add(AIRPORTS[selected]["iata"])
    points = [lookup[x] for x in sorted(codes) if x in lookup]
    fig.add_trace(go.Scattergeo(lat=[x["latitude"] for x in points], lon=[x["longitude"] for x in points], text=[x["iata"] for x in points], mode="markers+text", textposition="top center", textfont=dict(size=10), marker=dict(size=[13 if x["iata"] == AIRPORTS[selected]["iata"] else 6 for x in points], color=CYAN, line=dict(color="#D8FAFF", width=1)), hovertemplate="%{text}<extra></extra>", showlegend=False))
    fig.update_geos(scope="north america", projection_type="natural earth", showland=True, landcolor="#22303D", showocean=True, oceancolor="#15232F", showlakes=True, lakecolor="#15232F", bgcolor="rgba(0,0,0,0)", showcountries=True, countrycolor="#42505F", showsubunits=True, subunitcolor="#354555", lataxis_range=[18, 53], lonaxis_range=[-129, -59])
    style(fig, 475)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), hovermode="closest")
    return fig, missing

def weather_chart(table, field, title, cutoff):
    fig = go.Figure()
    for kind, colour in [("observation", GREY), ("forecast", CYAN)]:
        part = table[table.kind == kind].sort_values("valid_from_utc")
        if not part.empty and field in part:
            fig.add_trace(go.Scatter(x=part.valid_from_utc, y=part[field], name=kind.title(), mode="lines+markers", line=dict(color=colour, dash="dash" if kind == "forecast" else "solid", shape="hv")))
    fig.add_vline(x=cutoff.timestamp()*1000, line_color=AMBER, line_dash="dot")
    fig.update_yaxes(title=title)
    return style(fig, 235)
