"""Export the same illustrative scenario shown by the dashboard from verified files."""
import argparse
from io import BytesIO
import json
from pathlib import Path

import pandas as pd

from src.flight_risk.arrival_scenario import build_scenario
from tools.delivery.package import collect, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--airport", required=True, choices=("KATL", "KDFW"))
    parser.add_argument("--asof", required=True)
    parser.add_argument("--lead", type=int, required=True, choices=(3, 6, 12))
    parser.add_argument("--window", type=int, default=6)
    args = parser.parse_args()
    files, _ = collect(args.root)
    paths = {"traffic": "artifacts/capacity/traffic_hourly.parquet",
             "forecast": "artifacts/capacity_estimate/forecast.parquet"}
    result = build_scenario(**{k: pd.read_parquet(BytesIO(files[p])) for k, p in paths.items()},
        airport=args.airport, asof_utc=args.asof, window_hours=args.window, anchor_lead=args.lead)
    result["queue"] = result["queue"].to_dict(orient="records")
    result["evidence"] = {p: digest(files[p]) for p in paths.values()}
    result["airport"], result["asof_utc"] = args.airport, args.asof
    output = args.root / "output/delivery/arrival-scenario.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": result["status"], "metrics": result["metrics"],
                      "missing_inputs": result["missing_inputs"], "output": str(output)}))


if __name__ == "__main__":
    main()
