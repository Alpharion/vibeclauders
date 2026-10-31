import pandas as pd

from src.dashboard import map_view, plots, views

POINTS = {"ATL": (33.6, -84.4), "LAS": (36.1, -115.2)}
ROUTES = pd.DataFrame(
    {"origin": ["ATL", "ATL"], "dest": ["LAS", "ZZZ"], "direction": ["Departure", "Departure"], "flights": [2, 3]}
)
NODES = pd.DataFrame({"code": ["LAS", "ZZZ"], "Arrival": [0, 0], "Departure": [2, 3], "max_probability": [0.4, None], "flagged": [False, False]})
HUBS = {"ATL": "IFR"}


def payload(**kwargs):
    return map_view.map_payload(ROUTES, NODES, "ATL", HUBS, POINTS, **kwargs)


def test_missing_coordinates_are_counted_not_guessed():
    data, unmapped = payload()
    assert unmapped == 3
    assert len(data["lines"]) == 1
    assert [m["code"] for m in data["markers"]] == ["LAS", "ATL"]


def test_map_disabled_without_selected_airport_coordinates():
    data, unmapped = map_view.map_payload(ROUTES, NODES, "ZZZ", HUBS, POINTS)
    assert data is None and unmapped == 5


def test_hub_colour_follows_flight_category():
    data, _ = payload()
    hub = next(m for m in data["markers"] if m["hub"])
    assert hub["color"] == plots.CATEGORY_COLORS["IFR"]


def test_flagged_route_is_marked():
    data, _ = payload(flagged={("ATL", "LAS")})
    assert data["lines"][0]["color"] == plots.FLAG and "Flagged flow" in [item["label"] for item in data["legend"]]


def test_live_map_has_no_routes_or_forecast_layers():
    data = map_view.live_payload(HUBS, "ATL", None, {"ATL": "KATL"})
    assert data["lines"] == [] and all(m["hub"] for m in data["markers"])
    assert data["stops"] == []


def test_radar_frame_is_never_after_the_cutoff():
    cutoff = pd.Timestamp("2025-05-26T19:00:00Z")
    frame = views.radar_time(cutoff)
    assert frame < cutoff
    data, _ = payload(radar=frame)
    assert data["radar"]["time"] == "2025-05-26T18:50:00Z"
    assert payload()[0]["radar"] is None


def test_component_passes_payload_separately_from_executable_code(monkeypatch):
    from src.dashboard import components
    captured = {}
    monkeypatch.setattr(components, "_map_component", lambda: lambda **kwargs: captured.update(kwargs))
    data, _ = payload()
    data["legend"].append({"label": "</script>", "kind": "line", "color": "#fff"})
    components.ops_map(data, "test-map")
    assert captured["data"] is data
    assert "</script>" in captured["data"]["legend"][-1]["label"]


def test_great_circle_ends_at_both_airports():
    lat, lon = plots.great_circle(POINTS["ATL"], POINTS["LAS"])
    assert abs(lat[0] - 33.6) < 1e-6 and abs(lon[-1] + 115.2) < 1e-6


def test_real_reference_covers_scored_airports():
    assert {"ATL", "DFW"} <= set(plots.airport_points())
