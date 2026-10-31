"""SYNTHETIC fixtures. These numbers are invented and exist only under test temp dirs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

RUN = "synthetic-run"
DECISION_RUN = "synthetic-decision"
ASOF = pd.Timestamp("2025-07-15T12:00:00Z")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def envelope(run=RUN, **extra) -> dict:
    return {
        "schema_version": "2.0", "run_id": run, "status": "available",
        "generated_at_utc": "2026-10-31T00:00:00+00:00", "limitations": [], "missing_inputs": [],
        **extra,
    }


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def predictions(rows=None) -> pd.DataFrame:
    rows = rows or [
        ("f1", "KATL", ASOF, 6, 0.4), ("f2", "KATL", ASOF, 6, 0.1), ("f1", "KATL", ASOF, 3, 0.4),
        ("f3", "KDFW", ASOF + pd.Timedelta(hours=1), 6, 0.2),
    ]
    frame = pd.DataFrame(rows, columns=["flight_id", "airport", "asof_utc", "horizon_hours", "probability_severe_delay"])
    frame["target_hour_utc"] = frame["asof_utc"] + pd.to_timedelta(frame["horizon_hours"], unit="h")
    return frame.assign(
        threshold=0.15, model_kind="schedule_only", model_version="m1", run_id=RUN,
        source_id="synthetic", coverage="sample", status="available",
    )


def metrics() -> pd.DataFrame:
    days = pd.date_range("2025-01-06", periods=8, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "airport": "KATL", "period_start_utc": days, "period_end_utc": days + pd.Timedelta(days=1),
            "split": "test", "scheduled_departures": 10, "cancelled_departures": 1,
            "unknown_cancellation_departures": 1, "missing_delay_labels": 1,
            "eligible_departures": [8, 8, 8, 8, 8, 8, 8, 0], "severe_departures": [2, 2, 2, 2, 2, 2, 2, 0],
            "severe_delay_rate": [0.25] * 7 + [None],
            "total_positive_delay_minutes": [80.0] * 7 + [0.0],
            "delay_minutes_per_flight": [10.0] * 7 + [None],
            "coverage": "sample", "source_id": "synthetic", "kind": "observed",
            "requires_outcome_reveal": True,
        }
    )


def queue(hours=6) -> pd.DataFrame:
    target = pd.date_range(ASOF, periods=hours, freq="h")
    rows, backlog = [], 2
    for hour in target:
        demand, capacity = 10, 8
        served = min(backlog + demand, capacity)
        rows.append(
            {
                "airport": "KATL", "asof_utc": ASOF, "target_hour_utc": hour, "direction": "arrival",
                "demand_count": demand, "start_backlog": backlog, "served": served,
                "end_backlog": backlog + demand - served, "capacity": capacity, "aar_pred": 8.7,
                "status": "simulated",
            }
        )
        backlog = rows[-1]["end_backlog"]
    return pd.DataFrame(rows)


def recommendations(**overrides) -> dict:
    return envelope(
        DECISION_RUN, asof_utc="2025-07-15T12:00:00Z", airport="KATL", horizon_hours=6,
        recommendations=[
            {
                "id": "r1", "action": "Review arrival metering", "rationale": "Simulated deficit",
                "affected_flight_ids": [], "revised_times": [], "baseline": {}, "proposed": {},
                "prerequisites": [], "source": "synthetic", "human_review_required": True,
            }
        ],
        **overrides,
    )


def flights() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "flight_id": ["f1", "f2", "f4", "f5"], "origin": ["ATL", "ATL", "ATL", "LAS"],
            "dest": ["LAS", "ORD", "ORD", "ATL"], "carrier": "AA", "flight_number": [1, 2, 4, 5],
            "scheduled_dep_utc": pd.to_datetime(
                ["2025-07-15T18:37Z", "2025-07-15T18:05Z", "2025-07-15T13:00Z", "2025-07-15T10:00Z"], utc=True
            ),
            "scheduled_arr_utc": pd.to_datetime(
                ["2025-07-15T22:00Z", "2025-07-15T20:00Z", "2025-07-15T15:00Z", "2025-07-15T14:00Z"], utc=True
            ),
            "dep_delay_min": [50.0, 1.0, 0.0, 2.0], "arr_delay_min": [55.0, 0.0, 0.0, 1.0],
            "cancelled": False, "diverted": False, "coverage": "sample", "source_id": "synthetic",
        }
    )


def forecast() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "airport": "KATL", "asof_utc": ASOF, "target_hour_utc": ASOF + pd.Timedelta(hours=6),
                "horizon_hours": 6, "aar_pred": 88.0, "aar_lower": None, "aar_upper": None,
                "status": "available", "source": "synthetic", "source_id": "synthetic",
                "label_kind": "facility_aar", "features_available_at_utc": ASOF - pd.Timedelta(hours=1),
                "model_train_end_utc": ASOF - pd.Timedelta(days=30),
                "model_selection_end_utc": ASOF - pd.Timedelta(days=30), "run_id": "synthetic-capacity",
                "model_version": "c1", "coverage": "sample",
            }
        ]
    ).astype({"aar_lower": "float64", "aar_upper": "float64"})


def publish(root: Path, tables: dict, documents: dict, manifest_path: str, run: str) -> None:
    hashes = {}
    for relative, frame in tables.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path)
        hashes[relative] = {"sha256": sha(path), "rows": len(frame)}
    for relative, document in documents.items():
        write_json(root / relative, document)
        hashes[relative] = {"sha256": sha(root / relative)}
    write_json(root / manifest_path, envelope(run, outputs=hashes))


def publish_risk(root: Path, table=None, evaluation=None) -> None:
    publish(
        root,
        {
            "artifacts/risk/predictions.parquet": predictions() if table is None else table,
            "artifacts/risk/normalized_metrics.parquet": metrics(),
        },
        {
            "artifacts/risk/evaluation.json": evaluation or envelope(
                model="synthetic", split={"test": "2025"},
                metrics=[{"airport": "KATL", "horizon_hours": 3, "metric": "average_precision", "value": 0.2, "baseline_value": 0.1, "n": 9}],
                failure_example={"flight_id": "f1", "dep_delay_min": 41},
            )
        },
        "artifacts/risk/manifest.json", RUN,
    )


def publish_decision(root: Path, table=None, document=None) -> None:
    publish(
        root, {"artifacts/risk/queue.parquet": queue() if table is None else table},
        {"artifacts/risk/recommendations.json": document or recommendations()},
        "artifacts/risk/decision_manifest.json", DECISION_RUN,
    )


def publish_capacity(root: Path) -> None:
    publish(
        root,
        {"data/processed/flights.parquet": flights(), "artifacts/capacity/forecast.parquet": forecast()},
        {"artifacts/capacity/evaluation.json": envelope("synthetic-capacity", model="c", split={}, metrics=[])},
        "artifacts/capacity/manifest.json", "synthetic-capacity",
    )


@pytest.fixture
def root(tmp_path) -> Path:
    publish_risk(tmp_path)
    publish_decision(tmp_path)
    publish_capacity(tmp_path)
    return tmp_path
