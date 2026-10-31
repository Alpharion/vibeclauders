"""Publication integration: reject stale/mixed inputs and expose missing evidence."""
from argparse import Namespace
from hashlib import sha256
import json

import pandas as pd
import pytest

from src.flight_risk.__main__ import decide, verified_bytes, verify, verify_manifest


def publish(directory, filenames, run_id="test-run", **metadata):
    report = {"schema_version": "2.0", "run_id": run_id,
              "artifact_hashes": {name: sha256((directory / name).read_bytes()).hexdigest() for name in filenames}, **metadata}
    path = directory / "manifest.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def decision_args(tmp_path):
    return Namespace(airport="KATL", asof="2025-07-15T12:00:00Z", window_hours=3,
                     demand=tmp_path / "demand.parquet", capacity=tmp_path / "capacity.parquet",
                     initial_backlog=tmp_path / "backlog.parquet", input_manifest=tmp_path / "manifest.json",
                     output=tmp_path / "out")


def decision_inputs(tmp_path, run_id="test-run"):
    args = decision_args(tmp_path)
    cutoff = pd.Timestamp(args.asof)
    hours = pd.date_range(cutoff, periods=3, freq="h")
    pd.DataFrame({"airport": "KATL", "asof_utc": cutoff, "target_hour_utc": hours,
                  "direction": "arrival", "demand_count": [4, 2, 0], "population": "all_arrivals",
                  "coverage": "complete", "available_at_utc": cutoff, "source_id": "test-demand"}).to_parquet(args.demand)
    pd.DataFrame({"airport": "KATL", "asof_utc": cutoff, "target_hour_utc": hours,
                  "horizon_hours": [0, 1, 2], "aar_pred": [2., 3., 3.], "status": "available",
                  "label_kind": "facility_aar", "source": "test capacity", "source_id": "test-capacity",
                  "features_available_at_utc": cutoff, "model_train_end_utc": cutoff-pd.Timedelta(days=2),
                  "model_selection_end_utc": cutoff-pd.Timedelta(days=1), "run_id": run_id}).to_parquet(args.capacity)
    pd.DataFrame([{"airport": "KATL", "asof_utc": cutoff, "direction": "arrival", "backlog_count": 0,
                   "coverage": "complete", "population": "all_arrivals", "source_id": "test-backlog",
                   "observed_at_utc": cutoff, "available_at_utc": cutoff}]).to_parquet(args.initial_backlog)
    publish(tmp_path, ["demand.parquet", "capacity.parquet", "backlog.parquet"])
    return args


def test_missing_inputs_replace_stale_advice_with_typed_empty_queue(tmp_path):
    args = decision_inputs(tmp_path)
    assert decide(args)["status"] == "available"
    args.demand = tmp_path / "missing.parquet"
    result = decide(args)
    assert result["status"] == "unavailable"
    report = json.loads((args.output / "recommendations.json").read_text())
    assert report["recommendations"] == []
    queue = pd.read_parquet(args.output / "queue.parquet")
    assert queue.empty and str(queue.asof_utc.dtype) == "datetime64[ns, UTC]"
    verify_manifest(args.output / "decision_manifest.json", [args.output / "queue.parquet", args.output / "recommendations.json"])


def test_decision_json_is_lf_only_so_hashes_survive_any_checkout(tmp_path):
    args = decision_inputs(tmp_path)
    decide(args)
    for name in ["recommendations.json", "decision_manifest.json"]:
        assert b"\r" not in (args.output / name).read_bytes(), name


def test_decision_rejects_corrupted_source_even_if_parquet_readable(tmp_path):
    args = decision_inputs(tmp_path)
    table = pd.read_parquet(args.capacity)
    table["aar_pred"] = 999.
    table.to_parquet(args.capacity)
    result = decide(args)
    assert result["status"] == "unavailable"
    assert any("hash mismatch" in reason for reason in result["missing_inputs"])


def test_decision_rejects_hashed_but_mismatched_run(tmp_path):
    args = decision_inputs(tmp_path, run_id="stale-run")
    result = decide(args)
    assert result["status"] == "unavailable"
    assert any("another publication run" in reason for reason in result["missing_inputs"])


def test_verified_bytes_are_immutable_after_upstream_replacement(tmp_path):
    path = tmp_path / "input.txt"
    path.write_text("original")
    manifest = publish(tmp_path, [path.name])
    _, snapshots = verified_bytes(manifest, [path])
    path.write_text("changed")
    assert snapshots[path.resolve()] == b"original"
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_manifest(manifest, [path])


def test_required_input_must_be_declared(tmp_path):
    (tmp_path / "declared.txt").write_text("okay")
    (tmp_path / "not-declared.txt").write_text("not okay")
    path = publish(tmp_path, ["declared.txt"])
    with pytest.raises(ValueError, match="not declared"):
        verify_manifest(path, [tmp_path / "not-declared.txt"])


@pytest.mark.parametrize("asof,window", [("2025-07-15T12:00:00", 3), ("2025-07-15T12:37:00Z", 3), ("2025-07-15T12:00:00Z", 0)])
def test_invalid_cli_context_rejected_even_when_data_absent(tmp_path, asof, window):
    args = decision_args(tmp_path)
    args.asof, args.window_hours = asof, window
    with pytest.raises(ValueError):
        decide(args)


def model_fixture(tmp_path, asof="2025-07-15T12:00:00Z"):
    cutoff = pd.Timestamp(asof)
    pd.DataFrame([{"flight_id": "test-flight", "airport": "KATL", "asof_utc": cutoff,
                   "target_hour_utc": cutoff+pd.Timedelta(hours=3), "horizon_hours": 3,
                   "run_id": "test-run", "probability_severe_delay": .2, "threshold": .3,
                   "selection_end_utc": cutoff-pd.Timedelta(days=1)}]).to_parquet(tmp_path / "predictions.parquet")
    pd.DataFrame({"eligible_departures": [1]}).to_parquet(tmp_path / "normalized_metrics.parquet")
    (tmp_path / "evaluation.json").write_text(json.dumps({"run_id": "test-run"}))
    (tmp_path / "model.joblib").write_bytes(b"not loaded by verifier")
    publish(tmp_path, ["predictions.parquet", "normalized_metrics.parquet", "evaluation.json", "model.joblib"], status="partial")
    return Namespace(output=tmp_path)


@pytest.mark.parametrize("asof", ["2025-07-15T12:37:00Z", "2025-07-15T12:00:00"])
def test_prediction_verifier_rejects_non_hourly_or_naive_snapshot(tmp_path, asof):
    args = model_fixture(tmp_path, asof)
    with pytest.raises(ValueError):
        verify(args)


def test_verification_requires_all_model_files_in_manifest(tmp_path):
    args = model_fixture(tmp_path)
    publish(tmp_path, ["model.joblib"], status="partial")
    with pytest.raises(ValueError, match="not declared"):
        verify(args)


def test_valid_published_model_passes_without_deserializing_model(tmp_path):
    args = model_fixture(tmp_path)
    assert verify(args)["status"] == "passed"
