import json

import pytest

from src.dashboard.data import Group, _capabilities, fingerprint, is_schedule_only, load_bundle
from tests.dashboard import conftest as c


def status(bundle, name):
    return bundle.capability(name).status


def test_absent_artifacts_are_unavailable_with_reasons(tmp_path):
    bundle = load_bundle(tmp_path)
    assert bundle.tables == {}
    assert status(bundle, "Schedule risk") == "unavailable"
    assert "manifest.json is not published" in bundle.capability("Schedule risk").reasons[0]


def test_valid_publication_loads(root):
    bundle = load_bundle(root)
    assert len(bundle.table("predictions")) == 4
    assert status(bundle, "Schedule risk") == "available"
    assert status(bundle, "Weather risk") == "unavailable"
    assert status(bundle, "AAR forecast") == "available"
    assert status(bundle, "Flight rescheduling") == "unavailable"


def test_file_without_manifest_is_not_ready(root):
    (root / "artifacts/risk/manifest.json").unlink()
    assert load_bundle(root).table("predictions") is None


def test_partial_write_fails_hash_check(root):
    path = root / "artifacts/risk/predictions.parquet"
    path.write_bytes(path.read_bytes()[:200])
    bundle = load_bundle(root)
    assert bundle.table("predictions") is None
    assert "SHA256" in bundle.problem("predictions")


def test_undeclared_file_is_rejected(root):
    path = root / "artifacts/risk/manifest.json"
    manifest = json.loads(path.read_text())
    del manifest["outputs"]["artifacts/risk/predictions.parquet"]
    path.write_text(json.dumps(manifest))
    assert "no hash declared" in load_bundle(root).problem("predictions")


@pytest.mark.parametrize("content", ["{not json", '{"schema_version": NaN}', "[]"])
def test_malformed_manifest_is_rejected(root, content):
    (root / "artifacts/risk/manifest.json").write_text(content)
    bundle = load_bundle(root)
    assert bundle.table("predictions") is None
    assert "rejected" in bundle.problem("predictions")


def test_incompatible_schema_version_is_rejected(root):
    path = root / "artifacts/risk/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["schema_version"] = "1.0"
    path.write_text(json.dumps(manifest))
    assert "schema_version" in load_bundle(root).problem("predictions")


def test_duplicate_prediction_keys_are_rejected(tmp_path):
    table = c.predictions()
    c.publish_risk(tmp_path, table=c.pd.concat([table, table.iloc[[0]]]))
    assert "duplicate" in load_bundle(tmp_path).problem("predictions")


def test_invalid_probability_is_rejected(tmp_path):
    table = c.predictions().assign(probability_severe_delay=1.5)
    c.publish_risk(tmp_path, table=table)
    assert "outside [0, 1]" in load_bundle(tmp_path).problem("predictions")


def test_null_probability_is_rejected(tmp_path):
    table = c.predictions()
    table.loc[0, "probability_severe_delay"] = None
    c.publish_risk(tmp_path, table=table)
    assert "outside [0, 1]" in load_bundle(tmp_path).problem("predictions")


def test_inconsistent_target_hour_is_rejected(tmp_path):
    table = c.predictions()
    table["target_hour_utc"] = table["asof_utc"]
    c.publish_risk(tmp_path, table=table)
    assert "target_hour_utc" in load_bundle(tmp_path).problem("predictions")


def test_naive_timestamps_are_rejected(tmp_path):
    table = c.predictions()
    table["asof_utc"] = table["asof_utc"].dt.tz_localize(None)
    c.publish_risk(tmp_path, table=table)
    assert "not timezone-aware UTC" in load_bundle(tmp_path).problem("predictions")


def test_mixed_run_is_rejected(tmp_path):
    c.publish_risk(tmp_path, table=c.predictions().assign(run_id="older"))
    assert "run_id differs" in load_bundle(tmp_path).problem("predictions")


def test_evaluation_from_other_run_is_rejected(tmp_path):
    c.publish_risk(tmp_path, evaluation=c.envelope("older", metrics=[]))
    assert "run_id differs" in load_bundle(tmp_path).problem("risk_evaluation")


def test_fingerprint_changes_with_new_run(root):
    before = fingerprint(root)
    table = c.predictions().assign(probability_severe_delay=0.9)
    c.publish_risk(root, table=table)
    assert fingerprint(root) != before


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("schedule_only", True), ("schedule-hgb", True), ("weather_enhanced", False), ("schedule+weather", False)],
)
def test_schedule_only_identification(kind, expected):
    assert is_schedule_only(kind) is expected


def test_utc_day_spanning_two_splits_is_valid(tmp_path):
    # Splits use local dates, so one UTC day can hold rows from two splits.
    frame = c.metrics()
    frame.loc[1, ["period_start_utc", "period_end_utc", "split"]] = [
        frame.loc[0, "period_start_utc"], frame.loc[0, "period_end_utc"], "validation",
    ]
    c.publish(
        tmp_path, {"artifacts/risk/normalized_metrics.parquet": frame}, {},
        "artifacts/risk/manifest.json", c.RUN,
    )
    assert len(load_bundle(tmp_path).table("normalized_metrics")) == len(frame)


def set_capabilities(root, capabilities):
    path = root / "artifacts/risk/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["capabilities"] = capabilities
    path.write_text(json.dumps(manifest))


def test_schedule_risk_stays_available_when_every_row_has_weather(tmp_path):
    table = c.predictions().assign(model_kind="weather_enhanced")
    c.publish_risk(tmp_path, table=table)
    set_capabilities(tmp_path, {"schedule_risk": {"status": "available"}, "weather_risk": {"status": "partial", "reason": "coverage gap"}})
    bundle = load_bundle(tmp_path)
    assert status(bundle, "Schedule risk") == "available"  # All rows carry weather.


def test_partial_weather_risk_keeps_its_reason(root):
    c.publish_risk(root, table=c.predictions().assign(model_kind="weather_enhanced"))
    set_capabilities(root, {"weather_risk": {"status": "partial", "reason": "coverage gap"}})
    tables = {"weather_features": c.pd.DataFrame(), "predictions": c.predictions().assign(model_kind="weather_enhanced")}
    group = Group(manifest=json.loads((root / "artifacts/risk/manifest.json").read_text()))
    groups = {"risk": group, "decision": Group(), "capacity": Group(), "forecast": Group()}
    capability = next(x for x in _capabilities(tables, {}, groups) if x.name == "Weather risk")
    assert (capability.status, capability.reasons) == ("partial", ["coverage gap"])


def test_producer_status_cannot_raise_missing_evidence(tmp_path):
    set_capabilities_on_empty = c.envelope(capabilities={"weather_risk": {"status": "available"}})
    c.write_json(tmp_path / "artifacts/risk/manifest.json", set_capabilities_on_empty)
    assert status(load_bundle(tmp_path), "Weather risk") == "unavailable"


def test_empty_forecast_is_not_available_aar(tmp_path):
    c.publish_capacity(tmp_path, forecast_table=c.forecast().iloc[0:0])
    bundle = load_bundle(tmp_path)
    assert bundle.table("forecast") is not None
    assert status(bundle, "AAR forecast") == "unavailable"


def test_unavailable_capacity_evaluation_is_not_available_aar(tmp_path):
    document = c.envelope("synthetic-capacity", metrics=[], missing_inputs=["no AAR labels"])
    document["status"] = "unavailable"
    c.publish(
        tmp_path, {"artifacts/capacity/forecast.parquet": c.forecast()},
        {"artifacts/capacity/evaluation.json": document}, "artifacts/capacity/manifest.json", "synthetic-capacity",
    )
    capability = load_bundle(tmp_path).capability("AAR forecast")
    assert capability.status == "unavailable" and capability.reasons == ["no AAR labels"]
