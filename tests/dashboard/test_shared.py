import json

import pytest

from src.shared import AIRPORTS, flight_key, load_airports, resolve_airport


def test_flight_key_reproduces_member_2_published_id():
    assert flight_key("2025-01-13", "AA", 2667, "DFW", "LAS", 2000) == "bfd0e37ba4944076cf85"
    assert flight_key("2025-01-13", "AA", "2667.0", "DFW", "LAS", "2000") == "bfd0e37ba4944076cf85"


def test_registry_configures_both_airports():
    assert (AIRPORTS["KATL"].iata, AIRPORTS["KATL"].runway_heading_deg) == ("ATL", 80)
    assert (AIRPORTS["KDFW"].iata, AIRPORTS["KDFW"].runway_heading_deg) == ("DFW", 180)
    assert resolve_airport("DFW") is AIRPORTS["KDFW"]
    assert resolve_airport("XXX") is None


def test_unknown_metadata_is_refused(tmp_path):
    path = tmp_path / "airports.json"
    path.write_text(json.dumps({"airports": [{"icao": "KXXX", "iata": "XXX", "station": "KXXX"}]}))
    with pytest.raises(ValueError, match="timezone"):
        load_airports(path)
