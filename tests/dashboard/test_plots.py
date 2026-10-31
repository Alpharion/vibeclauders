import pandas as pd

from src.dashboard import plots

POINTS = {"ATL": (33.6, -84.4), "LAS": (36.1, -115.2)}
ROUTES = pd.DataFrame(
    {"origin": ["ATL", "ATL"], "dest": ["LAS", "ZZZ"], "direction": ["Departure", "Departure"], "flights": [2, 3]}
)


def test_missing_coordinates_are_counted_not_guessed():
    figure, unmapped = plots.route_map(ROUTES, "ATL", POINTS)
    assert unmapped == 3
    assert len(figure.data) == 2


def test_map_disabled_without_selected_airport_coordinates():
    figure, unmapped = plots.route_map(ROUTES, "ZZZ", POINTS)
    assert figure is None and unmapped == 5


def test_great_circle_ends_at_both_airports():
    lat, lon = plots.great_circle(POINTS["ATL"], POINTS["LAS"])
    assert abs(lat[0] - 33.6) < 1e-6 and abs(lon[-1] + 115.2) < 1e-6


def test_real_reference_covers_scored_airports():
    assert {"ATL", "DFW"} <= set(plots.airport_points())
