"""Airport-generic behaviour: a third airport needs registry configuration only."""
from argparse import Namespace
import json

import pandas as pd
import pytest

import src.flight_risk.__main__ as cli
from src.flight_risk.pipeline import build_artifacts
from src.shared import AIRPORTS

# Test-only registry entry; KORD is not part of the scored demonstration.
REGISTRY = AIRPORTS | {"KORD": {"iata": "ORD", "name": "Chicago O'Hare (test fixture)", "timezone": "America/Chicago", "heading": 270}}


@pytest.fixture(scope="module")
def three_airport_sample(tmp_path_factory):
    records = []
    for year in [2023, 2024, 2025]:
        for i in range(90):
            records.append({"FL_DATE": f"{year}-03-{i % 20 + 1:02}", "ORIGIN": ["ATL", "DFW", "ORD"][i % 3], "DEST": "LAX",
                            "OP_UNIQUE_CARRIER": "UA", "OP_CARRIER_FL_NUM": i + 1, "CRS_DEP_TIME": 700 + i % 9 * 100,
                            "DEP_DELAY": 70 if i % 4 == 0 else 2, "CANCELLED": 0, "CRS_ELAPSED_TIME": 150, "DISTANCE": 900})
    path = tmp_path_factory.mktemp("airports") / "sample.csv"
    pd.DataFrame(records).to_csv(path, index=False)
    return path


def test_third_airport_is_scored_through_registry_only(three_airport_sample):
    default = build_artifacts(three_airport_sample)
    assert set(default.predictions.airport) == {"KATL", "KDFW"}
    extended = build_artifacts(three_airport_sample, airport_registry=REGISTRY)
    assert set(extended.predictions.airport) == {"KATL", "KDFW", "KORD"}
    assert extended.manifest["airports"] == ["KATL", "KDFW", "KORD"]
    assert {row["airport"] for row in extended.evaluation["metrics"]} == {"KATL", "KDFW", "KORD"}
    assert {row["airport"] for row in extended.evaluation["alert_rates"]} == {"KATL", "KDFW", "KORD"}


def test_registry_entry_without_timezone_is_refused(three_airport_sample):
    broken = AIRPORTS | {"KORD": {"iata": "ORD", "heading": 270}}
    with pytest.raises(ValueError, match="KORD requires iata and timezone"):
        build_artifacts(three_airport_sample, airport_registry=broken)


def test_cli_registry_argument_reaches_the_pipeline(three_airport_sample, tmp_path, monkeypatch):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps(REGISTRY), encoding="utf-8")
    missing = tmp_path / "absent"
    args = Namespace(sample=str(three_airport_sample), output=str(tmp_path / "out"), airport_registry=str(registry),
                     canonical=None, weather_features=None, storm_events=None, input_manifest=str(missing / "manifest.json"))
    # Point default upstream paths at an empty directory so only the fixture sample is used.
    monkeypatch.setattr(cli, "ROOT", missing)
    result = cli.train(args)
    assert result["prediction_rows"] > 0
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["airports"] == ["KATL", "KDFW", "KORD"]
