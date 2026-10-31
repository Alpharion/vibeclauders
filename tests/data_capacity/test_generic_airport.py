"""The pipeline is airport-generic: a third airport works through a TEST-ONLY
registry and SYNTHETIC fixtures, with no airport-specific code. Nothing here is
published; ATL and DFW remain the only airports in real artifacts."""
import math

import numpy as np
import pandas as pd
import pytest

from src.data_capacity import capacity
from src.data_capacity.__main__ import main
from src.data_capacity.config import CAPACITY_DIR, UnsupportedAirport, load_registry, resolve_airports
from src.data_capacity.features import FEATURE_COLUMNS, build_features, validate_features
from src.data_capacity.flights import USECOLS, build_flights
from src.data_capacity.traffic import build_traffic
from src.data_capacity.weather import decode_metar, decode_taf

TEST_REGISTRY = load_registry({
    "KATL": {"iata": "ATL", "timezone": "America/New_York", "heading": 80},
    "KORD": {"iata": "ORD", "timezone": "America/Chicago", "heading": 270},   # synthetic third airport
    "KNOH": {"iata": "NOH", "timezone": "America/Chicago"},                    # heading missing
    "KNOZ": {"iata": "NOZ", "heading": 90},                                    # timezone missing
})
ORD = resolve_airports(["ORD"], TEST_REGISTRY)[0]


def test_third_airport_resolves_from_registry_only():
    assert (ORD.icao, ORD.timezone, ORD.runway_heading_deg) == ("KORD", "America/Chicago", 270.0)
    assert (ORD.metar_station, ORD.taf_station) == ("ORD", "KORD")


@pytest.mark.parametrize("code,missing", [("KNOH", "runway heading"), ("NOZ", "timezone"), ("KXXX", "not in the airport registry")])
def test_incomplete_or_unknown_airport_is_refused(code, missing):
    with pytest.raises(UnsupportedAirport, match=missing):
        resolve_airports([code], TEST_REGISTRY)


def test_cli_refuses_airport_absent_from_shared_registry(capsys):
    assert main(["run", "--airports", "KATL", "KORD", "--cache-only"]) == 2
    assert "KORD" in capsys.readouterr().err


def flight_rows():
    base = {c: None for c in USECOLS}
    base.update(FL_DATE="2024-06-10", OP_UNIQUE_CARRIER="UA", OP_CARRIER_FL_NUM=1.0, TAIL_NUM="N1", ORIGIN="ORD",
                DEST="LGA", CRS_DEP_TIME=800, CRS_ARR_TIME=1110, CRS_ELAPSED_TIME=130.0, DISTANCE=733.0,
                DEP_DELAY=0.0, ARR_DELAY=0.0, TAXI_OUT=12.0, TAXI_IN=6.0, CANCELLED=0.0, DIVERTED=0.0)
    inbound = dict(base, OP_CARRIER_FL_NUM=2.0, ORIGIN="LAX", DEST="ORD", CRS_DEP_TIME=700, CRS_ARR_TIME=1300,
                   CRS_ELAPSED_TIME=240.0)
    return pd.DataFrame([base, inbound])


def test_flights_and_traffic_for_third_airport():
    fl, audit = build_flights(flight_rows(), [ORD], "2024-06-01", "2024-06-30")
    assert len(fl) == 2 and audit["excluded_unresolved_arrival_date"] == 0
    dep = fl[fl.origin == "ORD"].iloc[0]
    assert dep.scheduled_dep_utc == pd.Timestamp("2024-06-10 13:00", tz="UTC")  # 08:00 CDT
    arr = fl[fl.dest == "ORD"].iloc[0]
    assert arr.scheduled_arr_utc == pd.Timestamp("2024-06-10 18:00", tz="UTC")  # 13:00 CDT
    t, summary = build_traffic(flight_rows(), [ORD], ["2024-06"], "test", "synthetic")
    assert set(t.airport) == {"KORD"} and summary["by_airport"]["KORD"]["departure"]["scheduled_total"] == 1


TAF = ("station,valid,fx_valid,raw,is_tempo,fx_valid_end,sknt,drct,gust,visibility,presentwx,skyc,skyl,ws_level,"
       "ws_drct,ws_sknt,product_id,ftype,is_amendment\n"
       "KORD,2024-06-10 05:20,2024-06-10 05:20,18015KT P6SM BKN030,False,,15.0,180.0,0.0,6.01,[],['BKN'],[3000],,,,"
       "202406100520-KLOT-FTUS43-TAFORD,Observation,False\n")
METAR = ("station,valid,tmpf,drct,sknt,gust,vsby,skyc1,skyl1,skyc2,skyl2,skyc3,skyl3,skyc4,skyl4,wxcodes,metar\n"
         "ORD,2024-06-10 05:51,68,90,10,,10,BKN,3000,,,,,,,,KORD 100551Z 09010KT 10SM BKN030\n")


def test_features_use_the_third_airports_heading():
    w = pd.concat([decode_taf(TAF, ORD, "synthetic"), decode_metar(METAR, ORD, "synthetic")])
    f = build_features(w, ORD, "2024-06-10", "2024-06-10")
    assert validate_features(f) == []
    r = f[(f.asof_utc == pd.Timestamp("2024-06-10 07:00", tz="UTC")) & (f.horizon_hours == 3)].iloc[0]
    # wind 180 on runway 270: pure crosswind; METAR 090 on 270: pure tailwind
    assert r.crosswind_kt == pytest.approx(15) and r.tailwind_kt == pytest.approx(0, abs=1e-6)
    assert r.obs_tailwind_kt == pytest.approx(10) and r.obs_crosswind_kt == pytest.approx(0, abs=1e-6)
    assert set(f.airport) == {"KORD"}


def test_aar_plumbing_accepts_any_registry_airport():
    rng = np.random.default_rng(1)
    airports = [resolve_airports(["ATL"], TEST_REGISTRY)[0], ORD]
    rows = []
    for ap in airports:
        t = pd.date_range("2023-01-01 06:00", "2025-07-31 23:00", freq="11h", tz="UTC")
        for h in (3, 6, 12):
            rows.append(pd.DataFrame({"airport": ap.icao, "target_hour_utc": t, "horizon_hours": h}))
    f = pd.concat(rows, ignore_index=True)
    f["asof_utc"] = f.target_hour_utc - pd.to_timedelta(f.horizon_hours, unit="h")
    for c in FEATURE_COLUMNS + capacity.EXTRA_FEATURES:
        f[c] = rng.uniform(0, 10, len(f))
    f["status"], f["source_id"], f["taf_bulletin_id"] = "available", "synthetic", "synthetic"
    f["available_at_utc"] = f.asof_utc
    lab = f[["airport", "target_hour_utc"]].drop_duplicates()
    lab["aar"] = rng.normal(90, 5, len(lab))
    fc, rep = capacity.fit_evaluate(f, lab, airports, "test")
    assert {m["airport"] for m in rep["metrics"]} == {"KATL", "KORD"}


@pytest.mark.parametrize("name", ["weather_features.parquet", "weather.parquet", "forecast.parquet", "traffic_hourly.parquet"])
def test_no_third_airport_in_published_artifacts(name):
    p = CAPACITY_DIR / name
    if not p.exists():
        pytest.skip("not published")
    assert set(pd.read_parquet(p, columns=["airport"]).airport) <= {"KATL", "KDFW"}
