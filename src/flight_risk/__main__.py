"""Member 2 command line: train, decide, and verify published artifacts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from uuid import uuid4

import pandas as pd

from .pipeline import run_pipeline
from .recommendations import build_recommendations
from .simulation import simulate_arrival_queue

ROOT = Path(__file__).resolve().parents[2]


def _digest(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_bytes(path, required_paths=None):
    """Check declared file hashes without loading any serialized model code.

    Paths are relative to the manifest directory. An input consumer verifies only
    the explicitly requested files, and requires every one to be declared.
    """
    path = Path(path).resolve()
    report = json.loads(path.read_text(encoding="utf-8-sig"))
    if report.get("schema_version") != "2.0" or not report.get("run_id"):
        raise ValueError(f"Invalid v2 manifest: {path}")
    hashes = report.get("artifact_hashes")
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError(f"Manifest has no artifact_hashes: {path}")
    declared = {(path.parent / name).resolve(): expected for name, expected in hashes.items()}
    selected = {Path(item).resolve() for item in required_paths} if required_paths is not None else set(declared)
    if missing := selected - set(declared):
        raise ValueError(f"Inputs not declared by manifest: {sorted(map(str, missing))}")
    snapshots = {}
    for item in selected:
        content = item.read_bytes()
        if sha256(content).hexdigest() != declared[item]:
            raise ValueError(f"Artifact hash mismatch: {item}")
        snapshots[item] = content
    return report, snapshots


def verify_manifest(path, required_paths=None):
    return verified_bytes(path, required_paths)[0]


def _optional_input(value, default):
    if value is not None:
        path = Path(value)
        if not path.is_file():
            raise ValueError(f"Explicit input does not exist: {path}")
        return path
    return default if default.is_file() else None


def _atomic_json(path, report):
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def train(args):
    canonical = _optional_input(args.canonical, ROOT / "data/processed/flights.parquet")
    weather = _optional_input(args.weather_features, ROOT / "artifacts/capacity/weather_features.parquet")
    external = [path for path in [canonical, weather] if path is not None]
    if external:
        upstream, snapshots = verified_bytes(args.input_manifest, external)
        # Train from immutable byte snapshots, even if Member 1 publishes again.
        cache = Path(args.output) / "input_snapshots" / uuid4().hex
        cache.mkdir(parents=True, exist_ok=False)
        cached = {}
        provenance = {"upstream_manifest": str(Path(args.input_manifest).resolve()),
                      "upstream_run_id": upstream["run_id"], "inputs": []}
        for index, (original, content) in enumerate(snapshots.items()):
            target = cache / f"{index}-{original.name}"
            target.write_bytes(content)
            cached[original] = target
            provenance["inputs"].append({"original": str(original), "snapshot": str(target.resolve()),
                                         "sha256": sha256(content).hexdigest()})
        _atomic_json(cache / "provenance.json", provenance)
        canonical = cached[canonical.resolve()] if canonical else None
        weather = cached[weather.resolve()] if weather else None
    registry = None
    if args.airport_registry:
        registry = json.loads(Path(args.airport_registry).read_text(encoding="utf-8-sig"))
    result = run_pipeline(args.sample, args.output, canonical, weather, registry)
    evaluation = result["evaluation"]
    return {"status": evaluation["status"], "output_dir": result["output_dir"],
            "model": evaluation["model"], "prediction_rows": evaluation["prediction_rows"],
            "weather_model": evaluation["weather_model"]["status"],
            "note": "Run verify before dashboard integration; partial status is not full Challenge 5 completion."}


def decide(args):
    cutoff = pd.Timestamp(args.asof)
    if pd.isna(cutoff) or cutoff.tzinfo is None or cutoff != cutoff.floor("h"):
        raise ValueError("--asof must be an explicit timezone-aware hour boundary")
    if args.window_hours <= 0 or args.window_hours > 168:
        raise ValueError("--window-hours must be between 1 and 168")
    args.airport = args.airport.strip().upper()
    if len(args.airport) != 4 or not args.airport.isalnum():
        raise ValueError("--airport must be a four-character ICAO code")
    paths = {"demand": Path(args.demand), "capacity": Path(args.capacity),
             "initial_backlog": Path(args.initial_backlog)}
    present = [path for path in paths.values() if path.is_file()]
    inputs, errors, snapshots, upstream = {}, [], {}, None
    if present:
        try:
            upstream, snapshots = verified_bytes(args.input_manifest, present)
        except (ValueError, OSError, TypeError) as exc:
            errors.append(f"Input publication rejected: {exc}")
            present = []
    for name, path in paths.items():
        inputs[name] = None
        if path in present:
            try:
                inputs[name] = pd.read_parquet(BytesIO(snapshots[path.resolve()]))
                if name == "capacity" and ("run_id" not in inputs[name]
                        or not inputs[name].run_id.eq(upstream["run_id"]).all()):
                    raise ValueError("Capacity rows belong to another publication run")
            except (ValueError, OSError) as exc:
                inputs[name] = None
                errors.append(f"Cannot read {name}: {exc}")
    simulation = simulate_arrival_queue(**inputs, airport=args.airport, asof_utc=args.asof,
                                        window_hours=args.window_hours)
    report = build_recommendations(**inputs, airport=args.airport, asof_utc=args.asof,
                                   horizon_hours=args.window_hours)
    run_id, generated = uuid4().hex, datetime.now(timezone.utc).isoformat()
    report.update(run_id=run_id, generated_at_utc=generated)
    report["missing_inputs"].extend(errors)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    queue_path = output / "queue.parquet"
    temp = queue_path.with_name(queue_path.name + ".tmp")
    simulation["queue"].to_parquet(temp, index=False)
    temp.replace(queue_path)
    _atomic_json(output / "recommendations.json", report)
    manifest = {
        "schema_version": "2.0", "producer": "member-2-decision-support", "run_id": run_id,
        "generated_at_utc": generated, "status": report["status"], "airport": report["airport"],
        "asof_utc": report["asof_utc"], "window_hours": args.window_hours,
        "row_counts": {"queue.parquet": len(simulation["queue"])},
        "artifact_hashes": {name: _digest(output / name) for name in ["queue.parquet", "recommendations.json"]},
        "upstream_run_id": upstream["run_id"] if upstream else None,
        "input_hashes": {str(path): sha256(content).hexdigest() for path, content in snapshots.items()},
        "missing_inputs": report["missing_inputs"], "limitations": report["limitations"],
    }
    _atomic_json(output / "decision_manifest.json", manifest)
    return {"status": report["status"], "output_dir": str(output.resolve()),
            "queue_rows": len(simulation["queue"]), "missing_inputs": report["missing_inputs"]}


def verify(args):
    output = Path(args.output)
    required_files = [output / name for name in ["model.joblib", "predictions.parquet", "normalized_metrics.parquet", "evaluation.json"]]
    manifest, snapshots = verified_bytes(output / "manifest.json", required_files)
    predictions = pd.read_parquet(BytesIO(snapshots[(output / "predictions.parquet").resolve()]))
    keys = ["flight_id", "airport", "asof_utc", "target_hour_utc", "horizon_hours"]
    required = keys + ["run_id", "probability_severe_delay", "threshold", "selection_end_utc"]
    if missing := set(required) - set(predictions):
        raise ValueError(f"Predictions missing {sorted(missing)}")
    if predictions.empty or predictions[keys].isna().any().any() or predictions.duplicated(keys).any():
        raise ValueError("Empty, missing-key or duplicate predictions")
    if not predictions.run_id.eq(manifest["run_id"]).all():
        raise ValueError("Predictions and manifest belong to different runs")
    for column in ["probability_severe_delay", "threshold"]:
        if not predictions[column].between(0, 1).all():
            raise ValueError(f"Invalid {column}")
    if not predictions.horizon_hours.isin([3, 6, 12]).all():
        raise ValueError("Unsupported prediction lead")
    for column in ["asof_utc", "target_hour_utc", "selection_end_utc"]:
        if not isinstance(predictions[column].dtype, pd.DatetimeTZDtype) or str(predictions[column].dt.tz) != "UTC":
            raise ValueError(f"{column} must use timezone-aware UTC")
        if predictions[column].isna().any():
            raise ValueError(f"{column} has missing timestamps")
    for column in ["asof_utc", "target_hour_utc"]:
        if not predictions[column].eq(predictions[column].dt.floor("h")).all():
            raise ValueError(f"{column} must use hour boundaries")
    if not (predictions.target_hour_utc - predictions.asof_utc).eq(pd.to_timedelta(predictions.horizon_hours, unit="h")).all():
        raise ValueError("Prediction lead does not match target hour")
    if not predictions.asof_utc.ge(predictions.selection_end_utc).all():
        raise ValueError("Prediction uses selection information from after cutoff")
    evaluation = json.loads(snapshots[(output / "evaluation.json").resolve()].decode("utf-8-sig"))
    if evaluation["run_id"] != manifest["run_id"]:
        raise ValueError("Evaluation belongs to another run")
    decisions = None
    if (output / "decision_manifest.json").is_file():
        decision_manifest, decision_bytes = verified_bytes(output / "decision_manifest.json",
            [output / "recommendations.json", output / "queue.parquet"])
        report = json.loads(decision_bytes[(output / "recommendations.json").resolve()].decode("utf-8-sig"))
        for key in ["run_id", "airport", "asof_utc", "status"]:
            if report.get(key) != decision_manifest.get(key):
                raise ValueError(f"Decision {key} differs from manifest")
        if report.get("horizon_hours") != decision_manifest.get("window_hours"):
            raise ValueError("Decision planning window differs from manifest")
        decisions = decision_manifest["status"]
    return {"status": "passed", "model_status": manifest["status"], "decision_status": decisions,
            "prediction_rows": len(predictions), "unique_flights": int(predictions.flight_id.nunique()),
            "airports": sorted(predictions.airport.unique()), "horizons": sorted(predictions.horizon_hours.unique().tolist()),
            "run_id": manifest["run_id"]}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    training = commands.add_parser("train", help="Train/evaluate the risk model; auto-detect verified Member 1 inputs")
    training.add_argument("--sample", default=str(ROOT / "data/weather/Flight_Data_With_Weather_Final.csv"))
    training.add_argument("--canonical")
    training.add_argument("--weather-features")
    training.add_argument("--airport-registry", help="JSON mapping ICAO to iata/timezone/heading config")
    decision = commands.add_parser("decide", help="Publish a supported queue/advisory or explicit unavailable result")
    decision.add_argument("--airport", required=True)
    decision.add_argument("--asof", required=True, help="Hourly UTC cutoff, e.g. 2025-07-15T12:00:00Z")
    decision.add_argument("--window-hours", type=int, default=6)
    decision.add_argument("--demand", default=str(ROOT / "data/processed/arrival_demand.parquet"))
    decision.add_argument("--capacity", default=str(ROOT / "artifacts/capacity/forecast.parquet"))
    decision.add_argument("--initial-backlog", default=str(ROOT / "data/processed/initial_backlog.parquet"))
    verification = commands.add_parser("verify", help="Verify artifact hashes, snapshot keys and probability bounds")
    for command in [training, decision, verification]:
        command.add_argument("--output", default=str(ROOT / "artifacts/risk"))
    for command in [training, decision]:
        command.add_argument("--input-manifest", default=str(ROOT / "artifacts/capacity/manifest.json"))
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        report = {"train": train, "decide": decide, "verify": verify}[args.command](args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "error", "reason": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
