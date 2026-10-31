import pandas as pd
from src.dashboard.weather_actions import recommendations

CUTOFF = pd.Timestamp("2025-01-01T12:00Z")


def test_prevailing_and_conditional_weather_have_specific_reviews():
    row = pd.Series(dict(available_at_utc=CUTOFF, thunderstorm_flag=1,
                         visibility_sm=6, cond_min_visibility_sm=2,
                         ceiling_ft_agl=500, wind_gust_kt=25))
    items, problem = recommendations(row, CUTOFF)
    assert problem is None
    assert len(items) == 4
    assert items[1]["Forecast basis"] == "Conditional TAF group"
    assert all(item["Evidence"] and item["Recommended review"] for item in items)


def test_future_weather_is_refused():
    items, problem = recommendations(pd.Series(dict(available_at_utc=CUTOFF + pd.Timedelta(seconds=1), thunderstorm_flag=1)), CUTOFF)
    assert not items and problem


def test_missing_weather_is_not_a_trigger():
    assert recommendations(None, CUTOFF)[1]
    assert recommendations(pd.Series(dict(available_at_utc=CUTOFF, thunderstorm_flag=pd.NA)), CUTOFF) == ([], None)


def test_conditional_weather_still_triggers_when_prevailing_is_unknown():
    row = pd.Series(dict(available_at_utc=CUTOFF, visibility_sm=pd.NA, cond_min_visibility_sm=1))
    assert recommendations(row, CUTOFF)[0][0]["Forecast basis"] == "Conditional TAF group"
