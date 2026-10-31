"""Validity intervals of decoded weather (SYNTHETIC IEM-format text) and
platform-independent JSON bytes."""
import json

import pandas as pd
import pytest

from src.data_capacity.config import CAPACITY_DIR, PROCESSED_DIR, resolve_airports
from src.data_capacity.io import write_json
from src.data_capacity.weather import decode_metar, decode_taf, group_end_from_raw, taf_validity_end

ATL = resolve_airports(["KATL"])[0]
HDR = "station,valid,fx_valid,raw,is_tempo,fx_valid_end,sknt,drct,gust,visibility,presentwx,skyc,skyl,ws_level,ws_drct,ws_sknt,product_id,ftype,is_amendment\n"
PID = "202305301737-KFFC-FTUS42-TAFATL"


def taf():
    rows = [
        f"KATL,2023-05-30 17:37,2023-05-30 17:37,18008KT P6SM SCT050,False,,8.0,180.0,0.0,6.01,[],['SCT'],[5000],,,,{PID},Observation,False",
        # FM group starting 27 h after issue: inside the 30 h period, beyond the old 24 h cap
        f"KATL,2023-05-30 17:37,2023-05-31 21:00,FM312100 23006KT 6SM BR OVC007,False,,6.0,230.0,0.0,6.0,['BR'],['OVC'],[700],,,,{PID},Forecast,False",
        # month-end PROB group; IEM's fx_valid_end (May 18) is wrong
        f"KATL,2023-05-30 17:37,2023-05-31 19:00,PROB30 3119/3124 4SM TSRA BR BKN040CB,False,2023-05-18 00:00,,,,4.0,\"['TSRA', 'BR']\",['BKN'],[4000],,,,{PID},Probability 30,False",
        # an amendment whose FM group starts at its issue minute supersedes the initial group
        "KATL,2023-05-30 20:00,2023-05-30 20:00,18008KT P6SM SCT050,False,,8.0,180.0,0.0,6.01,[],['SCT'],[5000],,,,202305302000-KFFC-FTUS42-TAFATL-AAA,Observation,True",
        "KATL,2023-05-30 20:00,2023-05-30 20:00,FM302000 20010KT P6SM BKN030,False,,10.0,200.0,0.0,6.01,[],['BKN'],[3000],,,,202305302000-KFFC-FTUS42-TAFATL-AAA,Forecast,True",
    ]
    return HDR + "\n".join(rows) + "\n"


def test_no_inverted_or_empty_taf_intervals():
    w = decode_taf(taf(), ATL, "synthetic")
    assert (w.valid_to_utc > w.valid_from_utc).all()
    assert w.attrs["dropped_empty_groups"] == 1  # the superseded initial group


def test_last_prevailing_group_runs_to_period_end():
    w = decode_taf(taf(), ATL, "synthetic")
    fm = w[(w.bulletin_id == PID) & (w.condition == "FM")].iloc[0]
    # 17:37 belongs to the 18Z cycle: period 30/18Z..01/00Z
    assert fm.valid_to_utc == pd.Timestamp("2023-06-01 00:00", tz="UTC")


def test_month_end_conditional_group_parsed_from_raw():
    w = decode_taf(taf(), ATL, "synthetic")
    prob = w[w.condition == "PROB"].iloc[0]
    assert prob.valid_to_utc == pd.Timestamp("2023-06-01 00:00", tz="UTC") and prob.probability == 0.3


@pytest.mark.parametrize("raw,start,end", [
    ("TEMPO 0113/0115 BKN014", "2023-03-01 13:00", "2023-03-01 15:00"),
    ("TEMPO 3122/0102 TSRA", "2023-05-31 22:00", "2023-06-01 02:00"),
    ("TEMPO 2822/0102 TSRA", "2024-02-28 22:00", "2024-03-01 02:00"),  # leap year: no 29th wrap error
    ("TEMPO 2822/0102 TSRA", "2023-02-28 22:00", "2023-03-01 02:00"),
])
def test_group_end_rollovers(raw, start, end):
    assert group_end_from_raw(raw, pd.Timestamp(start, tz="UTC")) == pd.Timestamp(end, tz="UTC")


def test_taf_period_cycle_assignment():
    issued = pd.Series(pd.to_datetime(["2024-03-04 23:30", "2024-03-05 01:48", "2024-03-05 17:22"], utc=True))
    assert taf_validity_end(issued).tolist() == [pd.Timestamp("2024-03-06 06:00", tz="UTC")] * 2 + [
        pd.Timestamp("2024-03-07 00:00", tz="UTC")]


def test_metar_same_minute_reports_not_zero_length():
    hdr = "station,valid,tmpf,drct,sknt,gust,vsby,skyc1,skyl1,skyc2,skyl2,skyc3,skyl3,skyc4,skyl4,wxcodes,metar\n"
    rows = ["ATL,2024-06-01 07:52,77,90,4,,10,FEW,25000,,,,,,,,KATL 010752Z 09004KT 10SM FEW250",
            "ATL,2024-06-01 07:52,77,90,4,,10,FEW,25000,,,,,,,,SPECI KATL 010752Z 09004KT 10SM FEW250 RMK",
            "ATL,2024-06-01 08:52,78,90,5,,10,FEW,25000,,,,,,,,KATL 010852Z 09005KT 10SM FEW250"]
    w = decode_metar(hdr + "\n".join(rows) + "\n", ATL, "synthetic")
    first = w[w.issued_at_utc == pd.Timestamp("2024-06-01 07:52", tz="UTC")]
    assert (first.valid_to_utc == pd.Timestamp("2024-06-01 08:52", tz="UTC")).all()


def test_json_is_written_with_lf_only(tmp_path):
    p = tmp_path / "x.json"
    write_json(p, {"a": [1, 2], "b": {"c": None}})
    data = p.read_bytes()
    assert b"\r" not in data and data.endswith(b"}\n")
    assert json.loads(data) == {"a": [1, 2], "b": {"c": None}}


@pytest.mark.skipif(not (CAPACITY_DIR / "weather.parquet").exists(), reason="no published weather")
def test_published_weather_has_no_inverted_validity():
    w = pd.read_parquet(CAPACITY_DIR / "weather.parquet")
    assert not (w.valid_to_utc.notna() & (w.valid_to_utc <= w.valid_from_utc)).any()
    cond = w[w.condition.isin(["TEMPO", "PROB"])]
    assert cond.valid_to_utc.notna().all()


@pytest.mark.parametrize("path", [CAPACITY_DIR / "manifest.json", CAPACITY_DIR / "evaluation.json",
                                  CAPACITY_DIR / "data_access.json", PROCESSED_DIR / "provenance.json"])
def test_published_json_is_lf(path):
    if not path.exists():
        pytest.skip("not published")
    assert b"\r\n" not in path.read_bytes()


def test_decoding_is_independent_of_source_row_order():
    # IEM returns the same rows in varying order between downloads
    lines = taf().splitlines()
    shuffled = "\n".join([lines[0]] + lines[1:][::-1]) + "\n"
    a = decode_taf(taf(), ATL, "s").reset_index(drop=True)
    b = decode_taf(shuffled, ATL, "s").reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)
