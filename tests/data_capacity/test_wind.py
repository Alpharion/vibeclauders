import numpy as np
import pytest

from src.data_capacity.config import resolve_airports
from src.data_capacity.wind import components


@pytest.mark.parametrize("direction,cross,tail", [
    (80, 0, 0),     # straight headwind on ATL 080
    (260, 0, 10),   # straight tailwind
    (170, 10, 0),   # pure crosswind from the right
    (350, 10, 0),   # pure crosswind from the left -> magnitude
    (125, 10 * np.sin(np.deg2rad(45)), 0),
])
def test_atl_heading_080(direction, cross, tail):
    c, t = components([10], [direction], 80.0)
    assert c[0] == pytest.approx(cross, abs=1e-6)
    assert t[0] == pytest.approx(tail, abs=1e-6)


def test_dfw_heading_180_tailwind_from_north():
    c, t = components([12], [360], 180.0)
    assert c[0] == pytest.approx(0, abs=1e-6) and t[0] == pytest.approx(12)


def test_calm_is_zero_but_variable_or_missing_direction_is_unknown():
    c, t = components([0, 5, 7], [0, np.nan, np.nan], 80.0)
    assert c[0] == 0 and t[0] == 0
    assert np.isnan(c[1]) and np.isnan(t[1]) and np.isnan(c[2])


def test_magnitudes_nonnegative():
    d = np.arange(0, 360, 5)
    c, t = components(np.full(d.shape, 15.0), d, 180.0)
    assert (c >= 0).all() and (t >= 0).all()


def test_registry_headings_match_challenge():
    atl, dfw = resolve_airports(["KATL", "DFW"])
    assert atl.runway_heading_deg == 80 and dfw.runway_heading_deg == 180


def test_unknown_airport_is_unsupported_not_guessed():
    from src.data_capacity.config import UnsupportedAirport

    with pytest.raises(UnsupportedAirport):
        resolve_airports(["KORD"])
