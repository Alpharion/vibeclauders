"""End-to-end Member 1 run: acquire -> canonical flights -> weather -> features
-> (genuine AAR model if labels exist) -> reports -> manifest (published last)."""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

import pandas as pd

from . import PRODUCER, SCHEMA_VERSION, bts, capacity, features, flights, storms, weather
from .config import (
    CAPACITY_DIR, HORIZONS, METAR_LATENCY_MIN, PROCESSED_DIR, PUBLIC_DIR, REPO_ROOT, TAF_ASSUMED_VALID_H,
    TAF_LATENCY_MIN, TAF_MAX_AGE_H, find_flight_csv, new_run_id, registry_source, resolve_airports, utcnow,
)
from .identity import FLIGHT_KEY_IMPL
from .io import read_json, sha256_file, write_json, write_parquet

ASPM_REQUEST = {
    "source": "FAA ASPM (https://www.aspm.faa.gov/) - authenticated account required",
    "report": "Airport Analysis / Airport Quarter Hour (or hourly) export, CSV",
    "airports": ["ATL", "DFW"],
    "dates_local": "2023-01-01 through 2025-07-31 (minimum: 2023-01-01..2023-12-31 train, 2024 validate, 2025-01..07 test)",
    "fields": ["LOCID", "YYYYMMDD", "HR_LOCAL or HR_GMT (state which)", "quarter (if quarter-hour)",
               "AAR (facility-set Airport Arrival Rate, arrivals/hour)", "ADR (optional)",
               "scheduled/actual arrivals (optional, for demand)", "runway configuration (optional)",
               "MC: VMC/IMC (optional)"],
    "drop_location": "data/public/aspm/<anything>.csv",
    "label_definition_required": "Facility-set called AAR (not actual arrival throughput, not GDP program rate, not efficiency AAR)",
}


def _rel(p) -> str:
    try:
        return Path(p).resolve().relative_to(REPO_ROOT).as_posix()
    except Exception:
        return str(p)


def probe_access(timeout=(10, 30)) -> list[dict]:
    """Light, read-only reachability probes for each public source landing page."""
    import requests

    probes = {
        "faa_aspm": "https://www.aspm.faa.gov/",
        "iem_taf": "https://mesonet.agron.iastate.edu/request/taf.php",
        "iem_metar": "https://mesonet.agron.iastate.edu/request/download.phtml",
        "bts_ontime": "https://transtats.bts.gov/PREZIP/",
        "noaa_storm_events": "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/",
    }
    out = []
    for sid, url in probes.items():
        rec = {"source_id": sid, "url": url, "checked_at_utc": utcnow()}
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": "autonomous-sg-2026-member1/1.0"})
            rec["http_status"] = r.status_code
            if sid == "faa_aspm":
                rec["login_required_indicators"] = [s for s in ("Direct Login", "MyAccess Login") if s in r.text]
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"
        out.append(rec)
    return out


def run_all(airports_codes, start, end, *, cache_only=False, refresh=False, flights_csv=None, aar_files=None,
            aar_time_basis=None, with_storms=True, bts_months=None, log=print) -> dict:
    t0 = utcnow()
    run_id = new_run_id(t0)
    airports = resolve_airports(airports_codes)
    log(f"[{run_id}] airports={[a.icao for a in airports]} dates={start}..{end} cache_only={cache_only}")
    outputs, sources, limitations, missing = {}, [], [], []
    wx_start = pd.Timestamp(start) - pd.Timedelta(days=2)
    wx_end = pd.Timestamp(end) + pd.Timedelta(days=2)

    # ---- flights
    csv_path = find_flight_csv(flights_csv)
    raw = flights.load_raw(csv_path)
    fl, fl_audit = flights.build_flights(raw, airports, start, end)
    write_parquet(PROCESSED_DIR / "flights.parquet", fl)
    outputs["flights"] = PROCESSED_DIR / "flights.parquet"
    sources.append({"source_id": flights.SOURCE_ID, "name": "Challenge-supplied BTS-derived flight sample",
                    "url": _rel(csv_path), "retrieved_at_utc": None, "requested_coverage": f"{start}..{end}",
                    "coverage": "sample", "status": "available", "hash": sha256_file(csv_path),
                    "notes": "Supplied file; its embedded daily weather columns are undated w.r.t. availability and are NOT used."})
    log(f"flights: {len(fl)} rows")

    # ---- optional BTS automatic ingestion (reporting-carrier population)
    bts_recs = []
    for ym in bts_months or []:
        y, m = map(int, ym.split("-"))
        r = bts.acquire_month(y, m, airports, cache_only=cache_only, refresh=refresh)
        bts_recs.append(r)
        log(f"bts {ym}: {r['status']} {r.get('filtered_rows')}")
    for r in bts_recs:
        sources.append({"source_id": bts.SOURCE_ID, "name": "BTS On-Time Reporting (PREZIP)", "url": r["url"],
                        "retrieved_at_utc": r.get("retrieved_at_utc"), "requested_coverage": r["month"],
                        "coverage": "reporting_carriers" if r["status"] != "failed" else None, "status": r["status"],
                        "hash": r.get("sha256"), "notes": r.get("error") or f"filtered rows {r.get('filtered_rows')} -> {_rel(r.get('filtered_path', ''))}"})

    # ---- weather
    wx_recs = weather.acquire(airports, wx_start, wx_end, cache_only=cache_only, refresh=refresh)
    for r in wx_recs:
        sources.append({"source_id": r["source_id"], "name": f"IEM {r['source_id'].split('_')[1].upper()} {r['airport']}",
                        "url": r["url"], "retrieved_at_utc": r.get("retrieved_at_utc"),
                        "requested_coverage": f"{r['window'][0]:%Y-%m-%d}..{r['window'][1]:%Y-%m-%d} (end exclusive)",
                        "coverage": "complete_archive" if r["status"] != "failed" else None, "status": r["status"],
                        "hash": r.get("sha256"), "notes": r.get("error")})
    failed_wx = [r for r in wx_recs if r["status"] == "failed"]
    if failed_wx:
        limitations.append(f"{len(failed_wx)} weather chunks failed: " + "; ".join(f"{r['airport']} {r['source_id']}: {r.get('error')}" for r in failed_wx))
    wx, wx_audit = weather.build_weather(wx_recs, airports)
    wx["run_id"] = run_id
    write_parquet(CAPACITY_DIR / "weather.parquet", wx)
    outputs["weather"] = CAPACITY_DIR / "weather.parquet"
    log(f"weather: {len(wx)} rows")

    # ---- features
    feats = pd.concat([features.build_features(wx, ap, start, end) for ap in airports], ignore_index=True)
    errs = features.validate_features(feats)
    if errs:
        raise RuntimeError("weather_features failed validation: " + "; ".join(errs))
    feats["run_id"] = run_id
    write_parquet(CAPACITY_DIR / "weather_features.parquet", feats)
    outputs["weather_features"] = CAPACITY_DIR / "weather_features.parquet"
    feat_cov = {f"{a}/h{h}": {"rows": int(len(g)), "available": int((g["status"] == "available").sum()),
                              "partial": int((g["status"] == "partial").sum()),
                              "unavailable": int((g["status"] == "unavailable").sum()),
                              "first_target_utc": g["target_hour_utc"].min(), "last_target_utc": g["target_hour_utc"].max(),
                              "null_share": {c: round(float(g[c].isna().mean()), 4) for c in features.FEATURE_COLUMNS}}
                for (a, h), g in feats.groupby(["airport", "horizon_hours"])}
    log(f"features: {len(feats)} rows, validation passed")

    # ---- storms (retrospective)
    storm_recs, storm_df = [], None
    if with_storms:
        years = sorted({wx_start.year, *range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1)})
        storm_recs = storms.acquire(years, cache_only=cache_only, refresh=refresh)
        storm_df = storms.build_storms(storm_recs, airports)
        write_parquet(PROCESSED_DIR / "storm_events.parquet", storm_df)
        outputs["storm_events"] = PROCESSED_DIR / "storm_events.parquet"
        for r in storm_recs:
            sources.append({"source_id": "noaa_storm_events", "name": f"NOAA Storm Events details {r['year']}",
                            "url": r.get("url"), "retrieved_at_utc": r.get("retrieved_at_utc"),
                            "requested_coverage": str(r["year"]), "coverage": "vicinity counties, retrospective",
                            "status": r["status"], "hash": r.get("sha256"), "notes": r.get("error")})
        log(f"storms: {len(storm_df)} vicinity events")

    # ---- capacity (genuine AAR only)
    labels, lab_audit = capacity.load_aar_labels(airports, [Path(p) for p in aar_files] if aar_files else None, aar_time_basis)
    eval_report = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "generated_at_utc": utcnow(),
                   "producer": PRODUCER, "label_audit": lab_audit, "limitations": [], "missing_inputs": []}
    if lab_audit["status"] == "available":
        try:
            fc, rep = capacity.fit_evaluate(feats, labels, airports, run_id)
            if storm_df is not None and len(storm_df) and len(fc):
                sh = storms.storm_hours(storm_df)
                j = fc.merge(sh, on=["airport", "target_hour_utc"], how="inner").merge(
                    labels, on=["airport", "target_hour_utc"])
                if len(j):
                    rep["cohorts"].append({"cohort": "noaa_storm_event_hour (retrospective)", "n": int(len(j)),
                                           "rmse": float(((j["aar_pred"] - j["aar"]) ** 2).mean() ** 0.5),
                                           "baseline_rmse": float(((j["aar_baseline"] - j["aar"]) ** 2).mean() ** 0.5)})
            eval_report.update(rep)
        except capacity.LabelError as exc:
            fc = capacity.empty_forecast()
            eval_report.update({"status": "unavailable", "metrics": []})
            eval_report["missing_inputs"].append(str(exc))
    else:
        fc = capacity.empty_forecast()
        eval_report.update({"status": "unavailable", "metrics": [], "requested_extract": ASPM_REQUEST})
        eval_report["missing_inputs"].append(lab_audit["reason"])
        eval_report["limitations"].append("Unmet core Challenge 5 requirement: no genuine facility AAR labels, so no AAR model or RMSE. "
                                          "Sampled arrival counts are NOT relabelled as capacity.")
    write_parquet(CAPACITY_DIR / "forecast.parquet", fc)
    outputs["forecast"] = CAPACITY_DIR / "forecast.parquet"
    write_json(CAPACITY_DIR / "evaluation.json", eval_report)
    outputs["evaluation"] = CAPACITY_DIR / "evaluation.json"
    aar_status = eval_report["status"]
    if aar_status != "available":
        missing.append("genuine facility AAR labels (FAA ASPM export)")
    log(f"capacity: AAR {aar_status}")

    # ---- access report
    access = read_json(CAPACITY_DIR / "data_access.json") or {}
    probes = probe_access() if not cache_only else access.get("probes", [])
    data_access = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "generated_at_utc": utcnow(), "producer": PRODUCER,
        "status": "partial" if aar_status != "available" else "available",
        "decision": ("AAR UNAVAILABLE: FAA ASPM hourly/quarter-hour AAR requires an authenticated ASPM account "
                     "(Direct Login / MyAccess). No credentialed export is present. Weather (IEM METAR/TAF), BTS and "
                     "NOAA sources are automatically accessible.") if aar_status != "available" else
                    "Genuine AAR labels present; see label_audit.",
        "aar": {"label_kind": capacity.LABEL_KIND, "status": aar_status, "audit": lab_audit,
                "definition": "Facility-set Airport Arrival Rate (arrivals/hour) as recorded in ASPM; distinct from actual "
                              "arrival throughput, GDP program rate and efficiency AAR.",
                "access_evidence": [
                    "https://www.aspm.faa.gov/ landing page shows 'Direct Login' and 'MyAccess Login'; the public part is "
                    "APM (Airport Analysis / City Pair / Taxi Times) delay metrics.",
                    "An automated scripted query against the ASPM report server was not performed: it would bypass the "
                    "site's account requirement and was declined by the agent's permission policy.",
                    f"No files matching {_rel(capacity.ASPM_DIR)}/*.csv at run time."],
                "requested_extract": ASPM_REQUEST,
                "overlap_feasibility": "IEM TAF/METAR cover 2022-12-30..2025-08-01 for both airports, so any ASPM extract "
                                       "for 2023-01..2025-07 would overlap fully with cutoff-safe features."},
        "probes": probes,
        "acquisition": {"weather": wx_audit["chunks"], "bts": bts_recs, "storms": storm_recs},
        "limitations": limitations, "missing_inputs": missing,
    }
    write_json(CAPACITY_DIR / "data_access.json", data_access)
    outputs["data_access"] = CAPACITY_DIR / "data_access.json"

    # ---- provenance
    prov = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "generated_at_utc": utcnow(), "producer": PRODUCER,
        "status": "partial" if missing else "available", "sources": sources,
        "flights_audit": fl_audit, "weather_audit": wx_audit["rows_by_airport_kind"],
        "assumptions": [
            f"METAR available_at = observation time + {METAR_LATENCY_MIN} min (IEM archives no receipt time).",
            f"TAF available_at = issuance + {TAF_LATENCY_MIN} min (issuance-as-availability with latency margin).",
            f"TAF prevailing group valid until the next prevailing group; last group capped at issuance + {TAF_ASSUMED_VALID_H} h.",
            f"TAF older than {TAF_MAX_AGE_H} h at cutoff is treated as stale (not used).",
            "Runway headings fixed by the challenge: ATL 080, DFW 180 (true).",
            "No-gust wind: gust = sustained speed. No BKN/OVC/VV layer: ceiling_ft_agl = 30000.",
            "Flights: arrival-date resolution for non-registry origins uses the implied origin UTC offset (see flights.py).",
        ],
        "failures": [s for s in sources if s["status"] == "failed"],
        "flight_key_impl": FLIGHT_KEY_IMPL, "airport_registry": registry_source(),
        "limitations": limitations + ["Flights are a sample: not complete airport demand; no initial backlog evidence."],
        "missing_inputs": missing,
    }
    write_json(PROCESSED_DIR / "provenance.json", prov)
    outputs["provenance"] = PROCESSED_DIR / "provenance.json"

    # ---- manifest (last)
    import numpy, pyarrow, sklearn

    def rows(p):
        return int(len(pd.read_parquet(p))) if str(p).endswith(".parquet") else None

    manifest = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "generated_at_utc": utcnow(), "producer": PRODUCER,
        "status": "partial" if missing else "available",
        "started_at_utc": t0,
        "command": " ".join(["python", "-m", "src.data_capacity"] + sys.argv[1:]) if sys.argv and "data_capacity" in sys.argv[0] else None,
        "parameters": {"airports": [a.icao for a in airports], "start": start, "end": end, "horizons": list(HORIZONS),
                       "cache_only": cache_only},
        "environment": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": numpy.__version__,
                        "scikit_learn": sklearn.__version__, "pyarrow": pyarrow.__version__},
        "flight_key_impl": FLIGHT_KEY_IMPL, "airport_registry": registry_source(),
        "outputs": [{"name": k, "path": _rel(p), "rows": rows(p), "sha256": sha256_file(p), "schema_version": SCHEMA_VERSION}
                    for k, p in outputs.items()],
        # contract 2.0 section 2: manifest-directory-relative path -> SHA256
        "artifact_hashes": {os.path.relpath(p, CAPACITY_DIR).replace(os.sep, "/"): sha256_file(p) for p in outputs.values()},
        "split": {"basis": "airport-local date", "train": "2023", "validate": "2024", "test": "2025-01-01..2025-07-31"},
        "coverage": {"flights": fl_audit["coverage_by_airport"], "weather_features": feat_cov},
        "capabilities": {
            "canonical_flights": {"status": "available", "coverage": "sample"},
            "weather_decoded": {"status": "available" if not failed_wx else "partial"},
            "weather_features": {"status": "available", "feature_semantics": features.FEATURE_SEMANTICS},
            "aar_forecast": {"status": aar_status, "reason": None if aar_status == "available" else "; ".join(eval_report["missing_inputs"])},
            "arrival_demand": {"status": "unavailable", "reason": "Only sampled schedules exist; no complete as-of-cutoff demand for a named population."},
            "initial_backlog": {"status": "unavailable", "reason": "No observed queue state at cutoff and no validated reconstruction."},
            "eligible_flights": {"status": "unavailable", "reason": "No as-of flight state (airborne/ground) data."},
            "storm_annotation": {"status": "available" if storm_df is not None and len(storm_df) else "unavailable",
                                 "use": "retrospective evaluation cohorts only"},
        },
        "limitations": limitations + eval_report["limitations"], "missing_inputs": missing,
    }
    write_json(CAPACITY_DIR / "manifest.json", manifest)
    log(f"manifest published: {_rel(CAPACITY_DIR / 'manifest.json')} ({manifest['status']})")
    return manifest
