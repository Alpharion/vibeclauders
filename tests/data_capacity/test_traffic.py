"""Hourly traffic counts from SYNTHETIC BTS-format rows."""
import pandas as pd
import pytest

from src.data_capacity.config import CAPACITY_DIR, resolve_airports
from src.data_capacity.flights import USECOLS
from src.data_capacity.traffic import build_traffic, validate_traffic

AIRPORTS = resolve_airports(["KATL", "KDFW"])


def row(**kw):
    base = {c: None for c in USECOLS}
    base.update(FL_DATE="2024-06-10", OP_UNIQUE_CARRIER="DL", OP_CARRIER_FL_NUM=1.0, TAIL_NUM="N1", ORIGIN="ATL",
                DEST="DFW", CRS_DEP_TIME=900, CRS_ARR_TIME=1015, CRS_ELAPSED_TIME=135.0, DISTANCE=731.0,
                DEP_DELAY=0.0, ARR_DELAY=0.0, TAXI_OUT=10.0, TAXI_IN=5.0, CANCELLED=0.0, DIVERTED=0.0)
    base.update(kw)
    return base


@pytest.fixture(scope="module")
def traffic():
    rows = [
        row(OP_CARRIER_FL_NUM=1.0),                                   # dep ATL 13:00Z, wheels-off 13:10Z
        row(OP_CARRIER_FL_NUM=2.0, DEP_DELAY=55.0, ARR_DELAY=50.0),   # wheels-off 14:05Z: actual in the next hour
        row(OP_CARRIER_FL_NUM=3.0, CANCELLED=1.0, DEP_DELAY=None, ARR_DELAY=None, TAXI_OUT=None, TAXI_IN=None),
        row(OP_CARRIER_FL_NUM=4.0, DIVERTED=1.0, ARR_DELAY=None, TAXI_IN=None),  # departs, never arrives at DFW
    ]
    t, summary = build_traffic(pd.DataFrame(rows), AIRPORTS, ["2024-06"], "test-run", "synthetic")
    return t.set_index(["airport", "hour_utc", "direction"]), summary


def at(t, ap, hour, direction):
    return t.loc[(ap, pd.Timestamp(hour, tz="UTC"), direction)]


def test_scheduled_includes_cancelled_actual_excludes_it(traffic):
    t, _ = traffic
    r = at(t, "KATL", "2024-06-10 13:00", "departure")
    assert r.scheduled_count == 4
    assert r.actual_count == 2  # flights 1 and 4 took off in 13Z; flight 2 in 14Z; 3 cancelled
    assert at(t, "KATL", "2024-06-10 14:00", "departure").actual_count == 1


def test_diversions_do_not_count_as_arrivals(traffic):
    t, _ = traffic
    sched = at(t, "KDFW", "2024-06-10 15:00", "arrival")  # 10:15 CDT
    assert sched.scheduled_count == 4
    assert sched.actual_count == 1  # 15:10Z wheels-on for flight 1 only
    assert at(t, "KDFW", "2024-06-10 16:00", "arrival").actual_count == 1  # delayed flight 2


def test_zero_hours_are_present_and_failed_months_absent(traffic):
    t, _ = traffic
    assert at(t, "KATL", "2024-06-10 03:00", "departure").scheduled_count == 0
    hours = t.reset_index().query("airport == 'KATL'").hour_utc
    assert hours.min() == pd.Timestamp("2024-06-01 04:00", tz="UTC")  # local midnight EDT
    assert hours.max() == pd.Timestamp("2024-07-01 03:00", tz="UTC")
    assert len(hours) == 2 * 30 * 24


def test_hours_before_coverage_end_mask_actuals(traffic):
    t, _ = traffic
    assert pd.isna(at(t, "KATL", "2024-07-01 03:00", "departure").actual_count)
    assert at(t, "KATL", "2024-07-01 03:00", "departure").scheduled_count == 0


def test_contract_fields_and_validation(traffic):
    t, summary = traffic
    flat = t.reset_index()
    assert validate_traffic(flat) == []
    assert set(flat.coverage) == {"reporting_carriers"} and flat.population.str.contains("reporting carriers").all()
    assert summary["status"] == "available"
    assert "demand" not in " ".join(flat.columns)  # never presented as queue demand


def test_no_months_is_unavailable():
    t, summary = build_traffic(pd.DataFrame([row()]), AIRPORTS, [], "r", "s")
    assert t.empty and summary["status"] == "unavailable"


def test_validator_catches_duplicates(traffic):
    flat = traffic[0].reset_index()
    assert validate_traffic(pd.concat([flat, flat.head(1)])) != []


@pytest.mark.skipif(not (CAPACITY_DIR / "traffic_hourly.parquet").exists(), reason="no published traffic")
def test_published_traffic_covers_both_airports():
    t = pd.read_parquet(CAPACITY_DIR / "traffic_hourly.parquet")
    assert validate_traffic(t) == []
    assert set(t.airport) == {"KATL", "KDFW"} and set(t.direction) == {"arrival", "departure"}
