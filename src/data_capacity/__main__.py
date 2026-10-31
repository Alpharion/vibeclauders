"""CLI: python -m src.data_capacity --help"""
from __future__ import annotations

import argparse
import json
import sys

from .config import DEFAULT_END, DEFAULT_START, UnsupportedAirport


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m src.data_capacity",
                                description="Member 1: public data, canonical flights, cutoff-safe weather features, genuine AAR model.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--airports", nargs="+", default=["KATL", "KDFW"], help="ICAO or IATA codes present in the airport registry")
        sp.add_argument("--start", default=DEFAULT_START, help="first local flight date (YYYY-MM-DD)")
        sp.add_argument("--end", default=DEFAULT_END, help="last local flight date (YYYY-MM-DD)")
        sp.add_argument("--cache-only", action="store_true", help="never touch the network; use cached downloads")
        sp.add_argument("--refresh", action="store_true", help="re-download even if a valid cache exists")

    run = sub.add_parser("run", help="full pipeline; publishes all artifacts and the manifest last")
    common(run)
    run.add_argument("--flights-csv", help="path to Flight_Data_With_Weather_Final.csv (auto-detected by default)")
    run.add_argument("--aar-file", nargs="*", help="genuine ASPM AAR export(s); default data/public/aspm/*.csv")
    run.add_argument("--aar-time-basis", choices=["local", "utc"], help="hour basis when the export has date+hour columns")
    run.add_argument("--no-storms", action="store_true", help="skip NOAA storm-event annotation")
    run.add_argument("--bts-months", nargs="*", default=None,
                     help="BTS PREZIP months to ingest for traffic_hourly (default: every month in --start..--end)")
    run.add_argument("--no-bts", action="store_true", help="skip BTS ingestion; traffic_hourly is then unavailable")
    run.add_argument("--no-throughput", action="store_true",
                     help="skip the observed-arrivals forecast (plan section 7 stretch; never AAR)")

    acc = sub.add_parser("access", help="probe public source reachability and print JSON (no artifacts written)")

    bt = sub.add_parser("bts", help="download + filter BTS monthly on-time archives only")
    common(bt)
    bt.add_argument("--months", nargs="+", required=True, help="YYYY-MM ...")
    bt.add_argument("--workers", type=int, default=4, help="parallel downloads (BTS throttles per connection)")

    args = p.parse_args(argv)
    try:
        if args.cmd == "run":
            from .pipeline import run_all

            m = run_all(args.airports, args.start, args.end, cache_only=args.cache_only, refresh=args.refresh,
                        flights_csv=args.flights_csv, aar_files=args.aar_file, aar_time_basis=args.aar_time_basis,
                        with_storms=not args.no_storms, bts_months=[] if args.no_bts else args.bts_months,
                        with_throughput=not args.no_throughput)
            print(json.dumps({"run_id": m["run_id"], "status": m["status"],
                              "capabilities": {k: v["status"] for k, v in m["capabilities"].items()}}, indent=2))
        elif args.cmd == "access":
            from .io import _jsonable
            from .pipeline import probe_access

            print(json.dumps(_jsonable(probe_access()), indent=2))
        elif args.cmd == "bts":
            from . import bts
            from .config import resolve_airports

            aps = resolve_airports(args.airports)
            recs = bts.acquire_months(args.months, aps, cache_only=args.cache_only, refresh=args.refresh,
                                      workers=args.workers, log=lambda m: print(m, flush=True))
            failed = [r["month"] for r in recs if r["status"] == "failed"]
            print(f"done: {len(recs) - len(failed)} ok, failed months: {failed or 'none'}")
    except UnsupportedAirport as exc:
        print(f"unsupported airport: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
