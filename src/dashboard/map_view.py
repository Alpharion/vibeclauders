"""Map payloads for the Leaflet component. Radar and basemap tiles load in the viewer's browser."""
from __future__ import annotations

import pandas as pd

from src.dashboard.plots import CATEGORY_COLORS, FLAG, SERIES, airport_points, great_circle
from src.dashboard.theme import TOKENS

RADAR_WMS = "https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q-t.cgi"
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services"
BASEMAP = f"{ESRI}/Canvas/World_Dark_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}"
LABELS = f"{ESRI}/Canvas/World_Dark_Gray_Reference/MapServer/tile/{{z}}/{{y}}/{{x}}"
HEIGHT = 520


def node_group(node) -> tuple[str, str]:
    if node.flagged:
        return "Flagged departure", FLAG
    if node.Arrival and node.Departure:
        return "Arrivals and departures", SERIES[2]
    return ("Arrivals only", SERIES[0]) if node.Arrival else ("Departures only", SERIES[1])


def node_label(node) -> str:
    risk = "not scored" if pd.isna(node.max_probability) else f"highest risk {node.max_probability:.0%}"
    return f"{node.code}: {node.Arrival} arriving, {node.Departure} departing · {risk}"


def map_payload(
    routes: pd.DataFrame, nodes: pd.DataFrame, selected_iata: str, hubs: dict[str, str], points=None,
    flagged=frozenset(), radar: pd.Timestamp | None = None, codes: dict[str, str] | None = None,
) -> tuple[dict | None, int]:
    """Everything the page draws, plus the number of movements lacking coordinates."""
    points = airport_points() if points is None else points
    if selected_iata not in points:
        return None, int(routes["flights"].sum())
    usable = routes["origin"].isin(points) & routes["dest"].isin(points)
    unmapped = int(routes.loc[~usable, "flights"].sum())
    lines, markers, legend = [], [], {}
    for route in routes[usable].itertuples():
        lat, lon = great_circle(points[route.origin], points[route.dest])
        is_flagged = (route.origin, route.dest) in flagged
        color = FLAG if is_flagged else (SERIES[0] if route.direction == "Arrival" else SERIES[1])
        legend["Flagged flow" if is_flagged else f"{route.direction} route"] = ("line", color)
        lines.append(
            {
                "path": [[float(a), float(b)] for a, b in zip(lat, lon)], "color": color, "flagged": is_flagged,
                "weight": 3 if is_flagged else 2, "dash": "8 6" if is_flagged else None,
                "label": f"{route.origin} → {route.dest}: {route.flights} scheduled",
            }
        )
    for node in nodes[nodes["code"].isin(points)].itertuples():
        group, color = node_group(node)
        lat, lon = points[node.code]
        markers.append(
            {
                "lat": lat, "lon": lon, "code": node.code, "color": color, "label": node_label(node),
                "radius": 4 + min(node.Arrival + node.Departure, 4), "hub": False,
            }
        )
    markers.extend(hub_markers(hubs, selected_iata, points, codes))
    for marker in markers:
        if marker["hub"]:
            legend[f"Hub {marker['category']}"] = ("area", marker["color"])
    payload = {
        "lines": lines, "markers": markers, "legend": [{"label": k, "kind": v[0], "color": v[1]} for k, v in legend.items()],
        "bounds": [[m["lat"], m["lon"]] for m in markers], "basemap": BASEMAP, "labels": LABELS, "radar": None,
    }
    if radar is not None:
        payload["radar"] = radar_payload(radar)
    return payload, unmapped


def hub_markers(hubs: dict[str, str], selected_iata: str, points, codes: dict[str, str] | None) -> list[dict]:
    markers = []
    for code, category in hubs.items():
        if code in points:
            lat, lon = points[code]
            markers.append(
                {
                    "lat": lat, "lon": lon, "code": code, "color": CATEGORY_COLORS[category], "category": category,
                    "label": f"{code}: {category} at cutoff", "radius": 10 if code == selected_iata else 8,
                    "hub": True, "icao": (codes or {}).get(code),
                }
            )
    return markers


def radar_payload(moment: pd.Timestamp) -> dict:
    return {"url": RADAR_WMS, "time": moment.strftime("%Y-%m-%dT%H:%M:%SZ")}


def live_payload(hubs: dict[str, str], selected_iata: str, radar: pd.Timestamp | None, codes: dict[str, str]) -> dict:
    """Stations and current radar only: no routes, aircraft or forecast layers."""
    points = airport_points()
    markers = hub_markers(hubs, selected_iata, points, codes)
    return {
        "lines": [], "markers": markers, "bounds": [[24.5, -106], [39, -74]], "basemap": BASEMAP, "labels": LABELS,
        "radar": radar_payload(radar) if radar is not None else None, "stops": [], "validLabel": "",
        "legend": [
            {"label": "Light", "kind": "area", "color": TOKENS["green"]},
            {"label": "Moderate", "kind": "area", "color": TOKENS["amber"]},
            {"label": "Heavy", "kind": "area", "color": TOKENS["red"]},
        ],
    }
