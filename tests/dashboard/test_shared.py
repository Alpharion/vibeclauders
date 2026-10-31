from src.dashboard.views import resolve_airport
from src.shared import AIRPORTS, flight_key


def test_flight_key_reproduces_member_2_published_id():
    assert flight_key("2025-01-13", "AA", 2667, "DFW", "LAS", 2000) == "bfd0e37ba4944076cf85"
    assert flight_key("2025-01-13", "AA", "2667.0", "DFW", "LAS", "2000") == "bfd0e37ba4944076cf85"


def test_registry_configures_both_airports():
    assert (AIRPORTS["KATL"]["iata"], AIRPORTS["KATL"]["heading"]) == ("ATL", 80)
    assert (AIRPORTS["KDFW"]["iata"], AIRPORTS["KDFW"]["heading"]) == ("DFW", 180)


def test_resolve_airport_accepts_both_codes_and_refuses_unknown():
    assert resolve_airport("DFW") == resolve_airport("KDFW")
    assert resolve_airport("DFW").heading == 180
    assert resolve_airport("XXX") is None
