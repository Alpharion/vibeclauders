"""Checks for the opt-in negative weather experiment, separate from production."""
import numpy as np
import pandas as pd

from src.data_capacity import capacity_estimate as ce
from src.data_capacity.weather_accuracy import classify_candidate, decision, eligible


def weather(n=1):
    return pd.DataFrame({"ceiling_ft_agl": [30000.] * n, "visibility_sm": [6.01] * n,
                         "crosswind_kt": [2.] * n, "tailwind_kt": [0.] * n,
                         "crosswind_gust_kt": [3.] * n, "wind_speed_kt": [5.] * n,
                         "wind_gust_kt": [7.] * n, "cond_groups": [0] * n})


def test_conditional_hazards_are_risk_not_certain_severe_weather():
    f = weather(3)
    f["cond_groups"] = 1
    f["cond_thunderstorm_flag"] = [1, 0, 0]
    f["cond_frozen_precip_flag"] = [0, 1, 0]
    f["cond_max_probability"] = [.3, .4, np.nan]
    f["cond_min_visibility_sm"] = [6, 6, 1]
    assert classify_candidate(f).tolist() == ["mvfr"] * 3
    f["thunderstorm_flag"] = [1, 0, 0]
    f["frozen_precip_flag"] = [0, 1, 0]
    assert classify_candidate(f).tolist() == ["convective", "winter", "mvfr"]


def test_unknown_wind_only_resolves_when_peak_bounds_thresholds():
    f = weather(4)
    f[["crosswind_kt", "tailwind_kt", "crosswind_gust_kt"]] = np.nan
    f["wind_speed_kt"] = [5, 12, np.nan, 0]
    f["wind_gust_kt"] = [9, 20, np.nan, 0]
    assert classify_candidate(f).tolist() == ["vfr", "unknown", "unknown", "vfr"]


def test_gust_directionality_and_priority():
    f = weather(3)
    f["crosswind_gust_kt"] = [16, 3, 16]
    f["wind_gust_kt"] = [20, 20, 20]
    f["ceiling_ft_agl"] = [30000, 30000, 500]
    assert classify_candidate(f).tolist() == ["wind", "vfr", "ifr"]


def test_future_and_unavailable_weather_excluded():
    f = weather(4)
    f["airport"], f["scheduled_arrivals"], f["observed_arrivals"] = "KATL", 50, 40
    f["asof_utc"] = pd.Timestamp("2024-10-01", tz="UTC")
    f["available_at_utc"] = f.asof_utc
    f["taf_available_at_utc"] = f.asof_utc
    f["taf_groups_used"] = 1
    f["status"] = ["available", "unavailable", "partial", "partial"]
    f.loc[2, "available_at_utc"] += pd.Timedelta(hours=1)
    f.loc[3, "taf_available_at_utc"] += pd.Timedelta(hours=1)
    assert eligible(f, {"demand_thresholds": {"KATL": 40}}).tolist() == [True, False, False, False]


def test_candidate_fit_ignores_all_held_out_labels_and_reproduces():
    f = pd.concat([weather(40), weather(40)], ignore_index=True)
    f["airport"], f["horizon_hours"] = "KATL", 3
    f["target_hour_utc"] = pd.date_range("2023-01-01", periods=80, freq="h", tz="UTC")
    f["scheduled_arrivals"] = 50
    f["observed_arrivals"] = np.arange(80)
    f["split"] = ["train"] * 40 + ["validate"] * 40
    f["weather_regime"] = classify_candidate(f)
    original = ce.fit(f)
    f.loc[f.split != "train", "observed_arrivals"] = 9999
    f.loc[f.split != "train", "scheduled_arrivals"] = 9999
    assert original == ce.fit(f)
    assert ce.predict(f, original).aar_pred.eq(35.1).all()
    assert all(c["support_n"] <= 40 for c in original["cells"])


def test_guardrails_require_all_six_cells_and_each_limit():
    cells = [{"incumbent": {"pinball": 10, "rmse": 20}, "candidate": {"pinball": 9.8, "rmse": 20}} for _ in range(6)]
    assert decision(cells)["adopt"]
    assert not decision(cells[:5])["adopt"]
    cells[0]["candidate"]["pinball"] = 10.6
    assert not decision(cells)["adopt"]
