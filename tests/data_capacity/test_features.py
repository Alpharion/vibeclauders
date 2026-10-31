"""Cutoff safety of weather features using SYNTHETIC IEM-format TAF/METAR text."""
import pandas as pd
import pytest

from src.data_capacity.config import CAPACITY_DIR, resolve_airports
from src.data_capacity.features import build_features, validate_features
from src.data_capacity.weather import decode_metar, decode_taf

ATL = resolve_airports(["KATL"])[0]
TAF_HEADER = "station,valid,fx_valid,raw,is_tempo,fx_valid_end,sknt,drct,gust,visibility,presentwx,skyc,skyl,ws_level,ws_drct,ws_sknt,product_id,ftype,is_amendment\n"


def taf_text():
    rows = [
        # routine TAF issued 05:20: benign all day
        'KATL,2024-06-01 05:20,2024-06-01 05:20,08010KT P6SM FEW250,False,,10.0,80.0,0.0,6.01,[],[\'FEW\'],[25000],,,,202406010520-KFFC-FTUS42-TAFATL,Observation,False',
        'KATL,2024-06-01 05:20,2024-06-01 06:00,TEMPO 0106/0110 2SM TSRA BKN008CB,True,2024-06-01 10:00,,,,2.0,"[\'TSRA\']",[\'BKN\'],[800],,,,202406010520-KFFC-FTUS42-TAFATL,Temporary,False',
        # amendment issued 08:40: thunderstorms, strong crosswind from 170 at 14:00
        'KATL,2024-06-01 08:40,2024-06-01 08:40,08010KT P6SM FEW250,False,,10.0,80.0,0.0,6.01,[],[\'FEW\'],[25000],,,,202406010840-KFFC-FTUS42-TAFATL-AAA,Observation,True',
        'KATL,2024-06-01 08:40,2024-06-01 14:00,FM011400 17020G35KT 1SM +TSRA OVC005CB,False,,20.0,170.0,35.0,1.0,"[\'+TSRA\']",[\'OVC\'],[500],,,,202406010840-KFFC-FTUS42-TAFATL-AAA,Forecast,True',
    ]
    return TAF_HEADER + "\n".join(rows) + "\n"


def metar_text():
    hdr = "station,valid,tmpf,drct,sknt,gust,vsby,skyc1,skyl1,skyc2,skyl2,skyc3,skyl3,skyc4,skyl4,wxcodes,metar\n"
    rows = [
        "ATL,2024-06-01 07:52,77.00,,4.00,,10.00,FEW,25000.00,,,,,,,,KATL 010752Z VRB04KT 10SM FEW250 25/20 A3000",
        "ATL,2024-06-01 08:52,80.60,90.00,8.00,,10.00,FEW,25000.00,,,,,,,,KATL 010852Z 09008KT 10SM FEW250 27/20 A3000",
    ]
    return hdr + "\n".join(rows) + "\n"


@pytest.fixture(scope="module")
def feats():
    w = pd.concat([decode_taf(taf_text(), ATL, "synthetic"), decode_metar(metar_text(), ATL, "synthetic")])
    f = build_features(w, ATL, "2024-06-01", "2024-06-01")
    return f.set_index(["asof_utc", "horizon_hours"])


def key(asof, h):
    return (pd.Timestamp(asof, tz="UTC"), h)


def test_future_amendment_excluded(feats):
    # cutoff 08:00 (+6 -> 14:00 target): amendment issued 08:40 must not be visible
    before = feats.loc[key("2024-06-01 08:00", 6)]
    assert before.taf_bulletin_id.endswith("TAFATL")
    assert before.thunderstorm_flag == 0 and before.crosswind_kt == pytest.approx(0)
    # cutoff 09:00 (+5 is not scored; +3 -> 12:00 target is before FM1400) and 11:00 (+3 -> 14:00)
    after = feats.loc[key("2024-06-01 11:00", 3)]
    assert after.taf_bulletin_id.endswith("AAA")
    assert after.thunderstorm_flag == 1 and after.precip_flag == 1
    assert after.crosswind_kt == pytest.approx(20 * abs(__import__("math").sin(__import__("math").radians(90))))
    assert after.wind_gust_kt == 35 and after.ceiling_ft_agl == 500


def test_amendment_cannot_rewrite_earlier_snapshot(feats):
    w_all = pd.concat([decode_taf(taf_text(), ATL, "s"), decode_metar(metar_text(), ATL, "s")])
    w_early = w_all[w_all["issued_at_utc"] < pd.Timestamp("2024-06-01 08:00", tz="UTC")]
    a = build_features(w_all, ATL, "2024-06-01", "2024-06-01").set_index(["asof_utc", "horizon_hours"])
    b = build_features(w_early, ATL, "2024-06-01", "2024-06-01").set_index(["asof_utc", "horizon_hours"])
    early = [k for k in a.index if k[0] <= pd.Timestamp("2024-06-01 08:45", tz="UTC")]
    cols = ["crosswind_kt", "thunderstorm_flag", "visibility_sm", "taf_bulletin_id"]
    pd.testing.assert_frame_equal(a.loc[early, cols], b.loc[early, cols])


def test_tempo_does_not_replace_prevailing(feats):
    r = feats.loc[key("2024-06-01 06:00", 3)]  # target 09:00 inside TEMPO 06-10
    assert r.visibility_sm == pytest.approx(6.01) and r.thunderstorm_flag == 0
    assert r.cond_thunderstorm_flag == 1 and r.cond_min_visibility_sm == 2.0


def test_metar_latency_and_variable_wind(feats):
    r = feats.loc[key("2024-06-01 08:00", 3)]
    # 07:52 obs available 08:02 (> 08:00): none usable yet within 2h window
    assert pd.isna(r.metar_observed_at_utc)
    r = feats.loc[key("2024-06-01 09:00", 3)]
    assert r.metar_observed_at_utc == pd.Timestamp("2024-06-01 07:52", tz="UTC")  # 08:52 available 09:02
    assert pd.isna(r.obs_crosswind_kt) and r.obs_wind_speed_kt == 4  # VRB -> unknown direction


def test_no_taf_before_first_issue_and_contract_validation(feats):
    r = feats.loc[key("2024-06-01 04:00", 3)]
    assert r.status == "unavailable" and pd.isna(r.crosswind_kt)  # missing stays null, not 0
    assert validate_features(feats.reset_index()) == []


def test_validator_catches_leakage(feats):
    bad = feats.reset_index()
    bad.loc[0, "available_at_utc"] = bad.loc[0, "asof_utc"] + pd.Timedelta(minutes=1)
    assert any("after cutoff" in e for e in validate_features(bad))


@pytest.mark.skipif(not (CAPACITY_DIR / "weather_features.parquet").exists(), reason="no published features")
def test_published_features_valid_and_cover_both_airports_all_horizons():
    f = pd.read_parquet(CAPACITY_DIR / "weather_features.parquet")
    assert validate_features(f) == []
    assert set(f.airport) == {"KATL", "KDFW"} and set(f.horizon_hours) == {3, 6, 12}
    assert (f.status == "available").mean() > 0.99
