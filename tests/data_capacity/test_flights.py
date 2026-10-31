"""Synthetic flight rows (test fixtures only) for identity/time edge cases."""
import pandas as pd
import pytest

from src.data_capacity.config import PROCESSED_DIR, resolve_airports
from src.data_capacity.flights import USECOLS, build_flights

AIRPORTS = resolve_airports(["KATL", "KDFW"])


def row(**kw):
    base = {c: None for c in USECOLS}
    base.update(FL_DATE="2024-06-01", OP_UNIQUE_CARRIER="DL", OP_CARRIER_FL_NUM=100.0, TAIL_NUM="N1", ORIGIN="ATL",
                DEST="DFW", CRS_DEP_TIME=900, CRS_ARR_TIME=1015, CRS_ELAPSED_TIME=135.0, DISTANCE=731.0,
                DEP_DELAY=0.0, ARR_DELAY=0.0, CANCELLED=0.0, DIVERTED=0.0)
    base.update(kw)
    return base


def build(rows):
    return build_flights(pd.DataFrame(rows), AIRPORTS, "2023-01-01", "2025-07-31")


def test_utc_and_arrival_from_elapsed():
    out, _ = build([row()])
    r = out.iloc[0]
    assert r.scheduled_dep_utc == pd.Timestamp("2024-06-01 13:00", tz="UTC")  # EDT = UTC-4
    assert r.scheduled_arr_utc == pd.Timestamp("2024-06-01 15:15", tz="UTC")  # 10:15 CDT


def test_inbound_overnight_from_unregistered_origin():
    # LAX 23:30 PDT (UTC-7) -> ATL 06:55 EDT next day, elapsed 265 min
    out, audit = build([row(ORIGIN="LAX", DEST="ATL", CRS_DEP_TIME=2330, CRS_ARR_TIME=655, CRS_ELAPSED_TIME=265.0)])
    r = out.iloc[0]
    assert r.scheduled_arr_utc == pd.Timestamp("2024-06-02 10:55", tz="UTC")
    assert r.scheduled_dep_utc == pd.Timestamp("2024-06-02 06:30", tz="UTC")
    assert audit["excluded_unresolved_arrival_date"] == 0


def test_dst_nonexistent_excluded_and_ambiguous_flagged():
    rows = [row(FL_DATE="2024-03-10", CRS_DEP_TIME=230, OP_CARRIER_FL_NUM=1.0),   # 02:30 does not exist
            row(FL_DATE="2024-11-03", CRS_DEP_TIME=130, OP_CARRIER_FL_NUM=2.0)]   # 01:30 happens twice
    out, audit = build(rows)
    assert audit["excluded_nonexistent_local_time"] == 1
    assert audit["flagged_dst_ambiguous"] == 1
    r = out.iloc[0]
    assert r.local_time_flag == "dst_ambiguous_first_occurrence"
    assert r.scheduled_dep_utc == pd.Timestamp("2024-11-03 05:30", tz="UTC")  # first (EDT) occurrence


def test_2400_is_end_of_day_and_flagged():
    out, audit = build([row(CRS_DEP_TIME=2400, CRS_ARR_TIME=115)])
    assert out.iloc[0].scheduled_dep_utc == pd.Timestamp("2024-06-02 04:00", tz="UTC")
    assert audit["flagged_crs_2400"] == 1


def test_identity_ignores_outcomes_and_conflicts_excluded():
    a, _ = build([row(DEP_DELAY=5.0)])
    b, _ = build([row(DEP_DELAY=90.0, CANCELLED=0.0)])
    assert a.flight_id.iloc[0] == b.flight_id.iloc[0]
    out, audit = build([row(DEP_DELAY=5.0), row(DEP_DELAY=50.0), row(OP_CARRIER_FL_NUM=7.0)])
    assert audit["excluded_conflicting_duplicate_keys"] == 2 and len(out) == 1
    out, audit = build([row(), row()])
    assert audit["collapsed_exact_duplicates"] == 1 and len(out) == 1


def test_unknown_cancellation_is_not_false_and_unselected_airports_counted():
    out, audit = build([row(CANCELLED=None), row(ORIGIN="ORD", DEST="LAX", OP_CARRIER_FL_NUM=9.0)])
    assert len(out) == 1 and pd.isna(out.iloc[0].cancelled)
    assert audit["excluded_no_selected_airport"] == 1 and audit["unknown_cancellation_status"] == 1


def test_gate_and_runway_times_separate():
    out, _ = build([row(DEP_DELAY=10.0, TAXI_OUT=20.0, ARR_DELAY=5.0, TAXI_IN=8.0)])
    r = out.iloc[0]
    assert r.actual_dep_gate_utc == pd.Timestamp("2024-06-01 13:10", tz="UTC")
    assert r.actual_wheels_off_utc == pd.Timestamp("2024-06-01 13:30", tz="UTC")
    assert r.actual_wheels_on_utc == r.actual_arr_gate_utc - pd.Timedelta(minutes=8)


@pytest.mark.skipif(not (PROCESSED_DIR / "flights.parquet").exists(), reason="no published flights")
def test_published_flights_keys_unique_and_utc():
    f = pd.read_parquet(PROCESSED_DIR / "flights.parquet")
    assert f.flight_id.is_unique
    assert str(f.scheduled_dep_utc.dt.tz) == "UTC"
    for c in ["flight_id", "origin", "dest", "carrier", "flight_number", "scheduled_dep_utc", "scheduled_arr_utc",
              "dep_delay_min", "arr_delay_min", "cancelled", "diverted", "coverage", "source_id"]:
        assert c in f.columns


def test_icao_columns_from_registry_and_unknown_stay_null():
    out, _ = build([row(), row(ORIGIN="LAX", DEST="ATL", CRS_DEP_TIME=700, CRS_ARR_TIME=1430, CRS_ELAPSED_TIME=270.0,
                            OP_CARRIER_FL_NUM=5.0)])
    atl_dfw = out[out.origin == "ATL"].iloc[0]
    assert (atl_dfw.origin_icao, atl_dfw.dest_icao) == ("KATL", "KDFW")
    lax = out[out.origin == "LAX"].iloc[0]
    assert pd.isna(lax.origin_icao) and lax.dest_icao == "KATL"
    # identity is unchanged: still the IATA-based shared flight_key
    assert out.flight_id.str.len().eq(20).all()
