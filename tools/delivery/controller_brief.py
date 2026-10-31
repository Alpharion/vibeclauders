"""Read-only review priorities from an exact published risk snapshot; no flight instructions."""
import argparse
from io import BytesIO
import json
from pathlib import Path

import pandas as pd

from tools.delivery.package import collect, digest, json_bytes


def summarize(rows, airport, asof, lead, run_id):
    required = {"flight_id", "airport", "asof_utc", "horizon_hours", "run_id", "status",
                "model_train_end_utc", "selection_end_utc", "weather_available_at_utc",
                "model_kind", "target_hour_utc", "probability_severe_delay", "threshold"}
    if not rows.columns.is_unique or not required.issubset(rows.columns):
        raise ValueError("Prediction schema is missing required or has duplicate columns")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("Missing producer run ID")
    cutoff = pd.Timestamp(asof)
    if cutoff.tzinfo is None:
        raise ValueError("Cutoff must include a timezone")
    cutoff = cutoff.tz_convert("UTC")
    if lead not in (3, 6, 12) or airport not in ("KATL", "KDFW"):
        raise ValueError("Choose KATL/KDFW and a 3/6/12-hour lead")
    selected = rows[(rows.airport == airport) & (rows.asof_utc == cutoff)
                    & (rows.horizon_hours == lead)].copy()
    if selected.flight_id.map(lambda value: not isinstance(value, str) or not value.strip()).any():
        raise ValueError("Missing flight identity at the requested snapshot")
    if selected.flight_id.duplicated().any():
        raise ValueError("Duplicate flights at the requested snapshot")
    for _, row in selected.iterrows():
        if row.run_id != run_id or row.status not in ("available", "partial"):
            raise ValueError("Unusable prediction status or mismatched run")
        for key in ("model_train_end_utc", "selection_end_utc"):
            value = pd.Timestamp(row[key])
            if pd.isna(value) or value.tzinfo is None or value > cutoff:
                raise ValueError(f"Invalid or future {key}")
        if row.model_kind == "weather_enhanced":
            value = pd.Timestamp(row.weather_available_at_utc)
            if pd.isna(value) or value.tzinfo is None or value > cutoff:
                raise ValueError("Invalid or future weather availability")
        elif row.model_kind != "schedule_only":
            raise ValueError("Unknown model kind")
        if row.target_hour_utc != cutoff + pd.Timedelta(hours=lead):
            raise ValueError("Target does not match the requested lead")
        if not (0 <= row.probability_severe_delay <= 1 and 0 <= row.threshold <= 1):
            raise ValueError("Invalid probability or threshold")
    flagged = selected[selected.probability_severe_delay >= selected.threshold].sort_values(
        ["probability_severe_delay", "flight_id"], ascending=[False, True])
    priorities = [{"flight_id": r.flight_id, "probability": float(r.probability_severe_delay),
                   "threshold": float(r.threshold), "model_kind": r.model_kind,
                   "reason": "Published probability meets or exceeds its validation-selected alert threshold",
                   "recommended_review": "Review current weather and airline/inbound-aircraft status before deciding whether intervention is warranted"}
                  for _, r in flagged.iterrows()]
    return {"schema_version": "1.0", "status": "available" if len(selected) else "unavailable",
            "airport": airport, "asof_utc": cutoff.isoformat(), "horizon_hours": lead,
            "target_hour_utc": (cutoff + pd.Timedelta(hours=lead)).isoformat(), "risk_run_id": run_id,
            "sampled_flights_scored": len(selected), "flagged_flights": len(flagged),
            "review_priorities": priorities,
            "summary": ("Review the flagged departures in descending risk order" if len(flagged) else
                        "No sampled departure crosses its threshold; this is not an airport all-clear" if len(selected) else
                        "No exact-key predictions available; do not substitute another cutoff or lead"),
            "limitations": ["Historical replay; these are not current operational alerts.",
                "This is a separate review briefing, not an action published to the dashboard or queue.",
                "Coverage is sampled departures, not complete airport traffic; probabilities are not calibrated guarantees.",
                "No capacity reduction, metering rate, flight time, routing or rescheduling is recommended.",
                "Qualified human review is required; no delay-minute or fuel benefit is established."]}


def create_brief(root, airport, asof, lead):
    files, _ = collect(root)
    path = "artifacts/risk/predictions.parquet"
    manifest = json.loads(files["artifacts/risk/manifest.json"])
    if manifest.get("status") not in ("available", "partial"):
        raise ValueError("Risk publication is not usable")
    if path.split("/")[-1] not in manifest["artifact_hashes"]:
        raise ValueError("Risk predictions are not declared by their producer")
    if digest(files[path]) != manifest["artifact_hashes"]["predictions.parquet"]:
        raise ValueError("Risk prediction hash does not match its producer")
    result = summarize(pd.read_parquet(BytesIO(files[path])), airport, asof, lead, manifest["run_id"])
    result["evidence"] = {"predictions": path, "predictions_sha256": digest(files[path]),
                          "manifest_sha256": digest(files["artifacts/risk/manifest.json"])}
    return result


def markdown(brief):
    lines = ["# Controller review brief", "", f"Status: **{brief['status']}**. Historical replay only.",
             f"{brief['airport']} | cutoff {brief['asof_utc']} | +{brief['horizon_hours']}h.",
             f"Risk run: `{brief['risk_run_id']}`.", "",
             f"{brief['sampled_flights_scored']} sampled departures scored; {brief['flagged_flights']} flagged.",
             brief["summary"], "", "| Flight ID | Probability | Threshold | Model |", "|---|---:|---:|---|"]
    for row in brief["review_priorities"]:
        lines.append(f"| {row['flight_id']} | {row['probability']:.1%} | {row['threshold']:.1%} | {row['model_kind']} |")
    if brief["review_priorities"]:
        lines += ["", brief["review_priorities"][0]["recommended_review"] + "."]
    lines += ["", "## Boundaries", ""] + ["- " + x for x in brief["limitations"]]
    lines += ["", "## Evidence", "", "```json", json.dumps(brief.get("evidence", {}), indent=2), "```", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--airport", required=True, choices=("KATL", "KDFW"))
    parser.add_argument("--asof", required=True)
    parser.add_argument("--lead", type=int, required=True, choices=(3, 6, 12))
    args = parser.parse_args()
    brief = create_brief(args.root, args.airport, args.asof, args.lead)
    output = args.root / "output/delivery"
    output.mkdir(parents=True, exist_ok=True)
    (output / "controller-brief.json").write_bytes(json_bytes(brief))
    (output / "CONTROLLER_BRIEF.md").write_text(markdown(brief), encoding="utf-8")
    print(json.dumps(brief, indent=2))


if __name__ == "__main__":
    main()
