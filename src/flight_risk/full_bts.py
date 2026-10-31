"""Build an isolated, hash-verified full-BTS canonical table, one month at a time.

Never downloads automatically and never overwrites production publications.
Canonical outcomes remain outcomes: model feature allowlists must not include them.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.data_capacity.config import resolve_airports
from src.data_capacity.flights import build_flights
from src.data_capacity.io import sha256_file

ROOT = Path(__file__).resolve().parents[2]
MONTHS = tuple(str(p) for p in pd.period_range("2023-01", "2025-07", freq="M"))


def verify_month(cache_dir, month):
    period = pd.Period(month, freq="M")
    path = Path(cache_dir) / f"ontime_ATL_DFW_{period.year}_{period.month:02d}.parquet"
    side = path.with_name(path.name + ".meta.json")
    if not path.is_file() or not side.is_file():
        raise ValueError(f"Missing local full-BTS cache or sidecar: {path}")
    meta = json.loads(side.read_text(encoding="utf-8-sig"))
    if meta.get("airports") != ["ATL", "DFW"]:
        raise ValueError("Cache airport scope must be ATL/DFW")
    if not isinstance(meta.get("zip_sha256"), str) or len(meta["zip_sha256"]) != 64:
        raise ValueError("Cache requires original archive SHA256 provenance")
    if meta.get("sha256") != sha256_file(path):
        raise ValueError(f"Filtered cache hash mismatch: {path}")
    return path, meta


def canonical_month(raw, month):
    period = pd.Period(month, freq="M")
    dates = pd.to_datetime(raw.FL_DATE, errors="coerce")
    if not dates.notna().all() or not dates.dt.to_period("M").eq(period).all():
        raise ValueError("Cache contains invalid dates or flights from another month")
    frame, audit = build_flights(raw, resolve_airports(["KATL", "KDFW"]),
                                 str(period.start_time.date()), str(period.end_time.date()))
    frame["coverage"] = "reporting_carriers"
    frame["source_id"] = "bts_ontime_prezip"
    audit["coverage_note"] = "Reporting carriers touching ATL/DFW; not all airport traffic or all eligible departures"
    return frame, audit


def build(cache_dir, output_dir, sample_path=ROOT / "data/processed/flights.parquet", months=MONTHS):
    months = tuple(months)
    if any(m not in MONTHS for m in months):
        raise ValueError("Months must lie in the fixed 2023-01 through 2025-07 experiment window")
    if len(set(months)) != len(months) or list(months) != sorted(months):
        raise ValueError("Months must be unique and chronological")
    # Validate every requested file before publishing any output.
    verified = [(month, *verify_month(cache_dir, month)) for month in months]
    if not verified:
        raise ValueError("No cache months supplied")
    output_dir = Path(output_dir).resolve()
    if output_dir.is_relative_to(ROOT / "data") or output_dir.is_relative_to(ROOT / "artifacts"):
        raise ValueError("Experiment output must not overwrite production data/artifacts")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "flights.parquet"
    pending = output_dir / "flights.parquet.pending"
    sample = pd.read_parquet(sample_path)
    schema = pq.read_schema(sample_path)
    sample_ids, matched = set(sample.flight_id), set()
    report = {"status": "built_experiment_only", "production_changed": False,
              "months": [], "forecast_population": "BTS reporting carriers touching ATL/DFW",
              "canonical_rows": 0, "label_counts": [], "sources": [],
              "limitations": ["Retrospectively reconstructed schedules; not verified live availability",
                "Canonical table contains outcomes for labels/evaluation, never all-column model inputs",
                "No training, adoption, accuracy improvement or full-airport claim is established by this build"]}
    writer = None
    try:
        for month, path, meta in verified:
            raw = pd.read_parquet(path)
            if len(raw) != meta.get("rows"):
                raise ValueError(f"Cache row count differs from sidecar: {path}")
            frame, audit = canonical_month(raw, month)
            table = pa.Table.from_pandas(frame, schema=schema, preserve_index=False, safe=True)
            if writer is None:
                writer = pq.ParquetWriter(pending, schema, compression="snappy")
            writer.write_table(table)
            matched.update(set(frame.flight_id) & sample_ids)
            departures = frame[frame.origin.isin(["ATL", "DFW"])]
            for origin, rows in departures.groupby("origin"):
                valid = rows.cancelled.eq(False).fillna(False) & rows.dep_delay_min.notna()
                split = "train" if month[:4] == "2023" else "validate" if month[:4] == "2024" else "test"
                report["label_counts"].append({"month": month, "split": split, "origin": origin,
                    "departures": len(rows), "eligible": int(valid.sum()),
                    "severe": int((valid & rows.dep_delay_min.gt(45)).sum())})
            report["canonical_rows"] += len(frame)
            report["months"].append({"month": month, "audit": audit})
            report["sources"].append({"month": month, "filtered_sha256": meta["sha256"],
                                      "archive_sha256": meta["zip_sha256"], "path": str(path)})
        writer.close()
        writer = None
        pending.replace(output)
    finally:
        if writer is not None:
            writer.close()
        if pending.exists():
            pending.unlink()
    report["sample_key_audit"] = {"sample_unique_keys": len(sample_ids), "matched_keys": len(matched),
                                 "missing_keys": len(sample_ids - matched)}
    report["output"] = str(output)
    report["sha256"] = sha256_file(output)
    (output_dir / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/full-bts-experiment")
    args = parser.parse_args()
    report = build(args.cache_dir, args.output)
    print(json.dumps({k: report[k] for k in ["status", "canonical_rows", "sample_key_audit", "output", "sha256"]}))


if __name__ == "__main__":
    main()
