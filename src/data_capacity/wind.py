"""Runway-relative wind components.

Convention: ``wind_dir_deg`` is the meteorological direction the wind blows
FROM (true degrees, as in METAR/TAF). ``heading_deg`` is the fixed runway
heading flights take off/land on (challenge: ATL 080, DFW 180).

    headwind  =  speed * cos(dir - heading)   (positive = into the aircraft nose)
    crosswind = |speed * sin(dir - heading)|  (nonnegative magnitude, kt)
    tailwind  = max(0, -headwind)             (nonnegative magnitude, kt)

Calm wind (speed 0) gives 0/0. Variable (VRB) or missing direction with
nonzero speed is unknown -> NaN, never 0.
"""
from __future__ import annotations

import numpy as np


def components(speed_kt, dir_deg, heading_deg):
    speed = np.asarray(speed_kt, dtype="float64")
    direction = np.asarray(dir_deg, dtype="float64")
    rel = np.deg2rad(direction - heading_deg)
    head = speed * np.cos(rel)
    cross = np.abs(speed * np.sin(rel))
    tail = np.maximum(0.0, -head)
    calm = speed == 0
    cross = np.where(calm, 0.0, cross)
    tail = np.where(calm, 0.0, tail)
    # direction unknown with nonzero (or unknown) speed stays NaN through the math
    cross = np.where(np.isnan(direction) & ~calm, np.nan, cross)
    tail = np.where(np.isnan(direction) & ~calm, np.nan, tail)
    # clean -0.0 / floating noise so magnitudes are exact for cardinal angles
    return np.round(cross, 6) + 0.0, np.round(tail, 6) + 0.0
