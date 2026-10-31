"""Geographic map: Leaflet, so it needs no WebGL. Radar and basemap tiles load in the viewer's browser."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

from src.dashboard.plots import CATEGORY_COLORS, FLAG, SERIES, airport_points, great_circle

STATIC = Path(__file__).resolve().parent / "static"
RADAR_WMS = "https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q-t.cgi"
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services"
BASEMAP = f"{ESRI}/Elevation/World_Hillshade_Dark/MapServer/tile/{{z}}/{{y}}/{{x}}"
LABELS = f"{ESRI}/Canvas/World_Dark_Gray_Reference/MapServer/tile/{{z}}/{{y}}/{{x}}"
HEIGHT = 520


@lru_cache(maxsize=1)
def _library() -> tuple[str, str]:
    return (STATIC / "leaflet.js").read_text(encoding="utf-8"), (STATIC / "leaflet.css").read_text(encoding="utf-8")


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
    flagged=frozenset(), radar: pd.Timestamp | None = None, connections: bool = True,
) -> tuple[dict | None, int]:
    """Everything the page draws, plus the number of movements lacking coordinates."""
    points = airport_points() if points is None else points
    if selected_iata not in points:
        return None, int(routes["flights"].sum())
    usable = routes["origin"].isin(points) & routes["dest"].isin(points)
    unmapped = int(routes.loc[~usable, "flights"].sum())
    lines, markers, legend = [], [], {}
    if connections:
        for route in routes[usable].itertuples():
            lat, lon = great_circle(points[route.origin], points[route.dest])
            is_flagged = (route.origin, route.dest) in flagged
            color = FLAG if is_flagged else (SERIES[0] if route.direction == "Arrival" else SERIES[1])
            legend["Flagged flow" if is_flagged else f"{route.direction} route"] = color
            lines.append(
                {
                    "path": [[float(a), float(b)] for a, b in zip(lat, lon)], "color": color,
                    "weight": 3.5 if is_flagged else 2, "dash": "8 7" if is_flagged else None,
                    "label": f"{route.origin} → {route.dest}: {route.flights} scheduled",
                }
            )
        for node in nodes[nodes["code"].isin(points)].itertuples():
            group, color = node_group(node)
            legend[group] = color
            lat, lon = points[node.code]
            markers.append(
                {
                    "lat": lat, "lon": lon, "code": node.code, "color": color, "label": node_label(node),
                    "radius": 5 + min(node.Arrival + node.Departure, 6), "hub": False,
                }
            )
    for code, category in hubs.items():
        if code in points:
            lat, lon = points[code]
            legend[f"Hub {category}"] = CATEGORY_COLORS[category]
            markers.append(
                {
                    "lat": lat, "lon": lon, "code": code, "color": CATEGORY_COLORS[category],
                    "label": f"{code}: {category} at cutoff", "radius": 13 if code == selected_iata else 10, "hub": True,
                }
            )
    payload = {
        "lines": lines, "markers": markers, "legend": legend, "centre": [37.5, (points[selected_iata][1] - 96) / 2],
        "basemap": BASEMAP, "labels": LABELS, "radar": None,
    }
    if radar is not None:
        payload["radar"] = {"url": RADAR_WMS, "time": radar.strftime("%Y-%m-%dT%H:%M:%SZ")}
    return payload, unmapped


def map_page(payload: dict) -> str:
    script, style = _library()
    data = json.dumps(payload).replace("</", "<\\/")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{style}
html,body,#map{{height:{HEIGHT}px;margin:0;background:#0A1520;font-family:sans-serif}}
.code{{background:transparent;border:0;box-shadow:none;color:#fff;font-weight:600;font-size:12px;text-shadow:0 0 3px #000,0 0 3px #000}}
.code::before{{display:none}}
.key{{background:rgba(10,21,32,.88);color:#DCE6F1;padding:8px 10px;border-radius:6px;font-size:11.5px;line-height:1.6}}
.key i{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}}
</style></head><body><div id="map"></div><script>{script}</script><script>
const data={data};
const map=L.map('map',{{zoomSnap:.25}});
L.tileLayer(data.basemap,{{maxZoom:12,attribution:'Tiles © Esri'}}).addTo(map);
if(data.radar){{L.tileLayer.wms(data.radar.url,{{layers:'nexrad-n0q-wmst',format:'image/png',transparent:true,opacity:.75,time:data.radar.time,attribution:'NEXRAD via Iowa Environmental Mesonet'}}).addTo(map);}}
data.lines.forEach(l=>L.polyline(l.path,{{color:l.color,weight:l.weight,dashArray:l.dash,opacity:.9}}).bindTooltip(l.label,{{sticky:true}}).addTo(map));
data.markers.forEach(m=>{{
 if(m.hub)L.circleMarker([m.lat,m.lon],{{radius:m.radius+7,color:m.color,weight:0,fillColor:m.color,fillOpacity:.25}}).addTo(map);
 L.circleMarker([m.lat,m.lon],{{radius:m.radius,color:'#fff',weight:m.hub?2.5:1,fillColor:m.color,fillOpacity:1}}).bindPopup(m.label)
  .bindTooltip(m.code,{{permanent:true,direction:'right',offset:[m.radius,0],className:'code'}}).addTo(map);
}});
const key=L.control({{position:'bottomleft'}});
key.onAdd=()=>{{const d=L.DomUtil.create('div','key');Object.entries(data.legend).forEach(([k,c])=>{{const r=document.createElement('div');const i=document.createElement('i');i.style.background=c;r.append(i,k);d.append(r);}});return d;}};
key.addTo(map);
L.tileLayer(data.labels,{{maxZoom:12,pane:'shadowPane'}}).addTo(map);
map.fitBounds(data.markers.map(m=>[m.lat,m.lon]),{{padding:[45,45],maxZoom:6}});
</script></body></html>"""
