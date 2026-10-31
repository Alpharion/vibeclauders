import pandas as pd
import pytest

from src.dashboard.views import network_nodes, resolve_airport


@pytest.mark.parametrize("in_window", [False, True])
def test_arrow_routes_with_scored_flight_outside_planning_window(in_window):
    cutoff = pd.Timestamp("2025-07-31T11:00Z")
    flights = pd.DataFrame({
        "flight_id": ["future", "near"], "origin": ["DFW", "DFW"],
        "dest": ["ATL", "LAX"],
        "scheduled_dep_utc": [cutoff + pd.Timedelta(hours=12), cutoff + pd.Timedelta(hours=1 if in_window else 13)],
        "scheduled_arr_utc": [cutoff + pd.Timedelta(hours=14), cutoff + pd.Timedelta(hours=16)],
    }).convert_dtypes(dtype_backend="pyarrow")
    scored = pd.DataFrame({"flight_id": ["future"], "probability_severe_delay": [.8], "threshold": [.3]}).convert_dtypes(dtype_backend="pyarrow")
    nodes = network_nodes(flights, scored, resolve_airport("KDFW"), cutoff, 6)
    assert str(nodes.flagged.dtype) == "bool"
    assert not nodes.flagged.any()
    assert nodes.code.tolist() == (["LAX"] if in_window else [])


def test_arrow_matching_route_retains_true_risk_flag():
    cutoff = pd.Timestamp("2025-07-31T11:00Z")
    flights = pd.DataFrame({"flight_id": ["f"], "origin": ["DFW"], "dest": ["ATL"],
                            "scheduled_dep_utc": [cutoff], "scheduled_arr_utc": [cutoff + pd.Timedelta(hours=2)]}).convert_dtypes(dtype_backend="pyarrow")
    scored = pd.DataFrame({"flight_id": ["f"], "probability_severe_delay": [.3], "threshold": [.3]}).convert_dtypes(dtype_backend="pyarrow")
    nodes = network_nodes(flights, scored, resolve_airport("KDFW"), cutoff, 6)
    assert nodes.flagged.tolist() == [True]


def test_null_arrow_mapping_from_backend_is_normalized(monkeypatch):
    """Emulate the reported backend's all-unmatched null result at the map boundary."""
    import pyarrow as pa
    original_map = pd.Series.map
    seen = []

    def null_map(series, arg, *args, **kwargs):
        result = original_map(series, arg, *args, **kwargs)
        if isinstance(arg, pd.Series) and arg.name == "any_flag" and result.isna().all():
            seen.append(True)
            return pd.Series([None] * len(result), index=result.index, dtype=pd.ArrowDtype(pa.null()))
        return result

    monkeypatch.setattr(pd.Series, "map", null_map)
    test_arrow_routes_with_scored_flight_outside_planning_window(True)
    assert seen
