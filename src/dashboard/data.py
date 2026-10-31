"""Load published artifacts. A table is usable only after its manifest vouches for it."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

SCHEMA_VERSION = "2.0"
SCORED_HORIZONS = (3, 6, 12)
STATUSES = ("available", "partial", "unavailable")
SNAPSHOT_KEY = ["airport", "asof_utc", "target_hour_utc", "horizon_hours"]


class ArtifactError(ValueError):
    """An artifact exists but cannot be trusted."""


@dataclass(frozen=True)
class TableSpec:
    path: str
    required: tuple[str, ...]
    key: tuple[str, ...]
    utc: tuple[str, ...] = ()
    check: Callable[[pd.DataFrame], list[str]] | None = None


@dataclass
class Capability:
    name: str
    status: str
    reasons: list[str] = field(default_factory=list)
    run_id: str | None = None


@dataclass
class Group:
    """One producer publication: a manifest and the files it declares."""

    manifest: dict | None = None
    problems: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Bundle:
    root: str
    fingerprint: str
    tables: dict[str, pd.DataFrame]
    docs: dict[str, dict]
    groups: dict[str, Group]
    capabilities: list[Capability]

    def table(self, name: str) -> pd.DataFrame | None:
        return self.tables.get(name)

    def problem(self, name: str) -> str:
        for group in self.groups.values():
            if name in group.problems:
                return "; ".join(group.problems[name])
        return f"{name} is not part of any loaded publication"

    def capability(self, name: str) -> Capability:
        return next(c for c in self.capabilities if c.name == name)


def _check_snapshot(df: pd.DataFrame, horizons: tuple[int, ...] | None = None) -> list[str]:
    problems = []
    for column in ("asof_utc", "target_hour_utc"):
        if not (df[column] == df[column].dt.floor("h")).all():
            problems.append(f"{column} is off the hourly grid")
    lead = pd.to_timedelta(df["horizon_hours"], unit="h")
    if not (df["target_hour_utc"] == df["asof_utc"] + lead).all():
        problems.append("target_hour_utc != asof_utc + horizon_hours")
    if horizons and not df["horizon_hours"].isin(horizons).all():
        problems.append(f"horizon_hours outside scored leads {horizons}")
    return problems


def _check_predictions(df: pd.DataFrame) -> list[str]:
    problems = _check_snapshot(df, SCORED_HORIZONS)
    for column in ("probability_severe_delay", "threshold"):
        values = pd.to_numeric(df[column], errors="coerce")
        if not values.between(0, 1).all():
            problems.append(f"{column} has values outside [0, 1]")
    return problems


def _check_metrics(df: pd.DataFrame) -> list[str]:
    problems = []
    if (df["eligible_departures"] > df["scheduled_departures"]).any():
        problems.append("eligible_departures exceeds scheduled_departures")
    if (df["severe_departures"] > df["eligible_departures"]).any():
        problems.append("severe_departures exceeds eligible_departures")
    if (df["kind"] != "observed").any():
        problems.append("normalized metrics must be kind='observed'")
    return problems


def _check_forecast(df: pd.DataFrame) -> list[str]:
    problems = _check_snapshot(df)
    if (pd.to_numeric(df["aar_pred"], errors="coerce").dropna() < 0).any():
        problems.append("aar_pred is negative")
    return problems


def _check_traffic(df: pd.DataFrame) -> list[str]:
    problems = []
    if (df["coverage"] != "reporting_carriers").any():
        problems.append("traffic_hourly must be coverage='reporting_carriers'")
    if not df["direction"].isin(("arrival", "departure")).all():
        problems.append("direction must be arrival or departure")
    if (df[["scheduled_count", "actual_count"]] < 0).any().any():
        problems.append("traffic counts are negative")
    return problems


PREDICTION_COLUMNS = (
    "flight_id", *SNAPSHOT_KEY, "probability_severe_delay", "threshold", "model_kind",
    "model_version", "run_id", "source_id", "coverage", "status",
)
METRIC_COLUMNS = (
    "airport", "period_start_utc", "period_end_utc", "split", "scheduled_departures",
    "cancelled_departures", "unknown_cancellation_departures", "missing_delay_labels",
    "eligible_departures", "severe_departures", "severe_delay_rate",
    "total_positive_delay_minutes", "delay_minutes_per_flight", "coverage", "source_id",
    "kind", "requires_outcome_reveal",
)
QUEUE_COLUMNS = (
    "airport", "asof_utc", "target_hour_utc", "direction", "demand_count", "start_backlog",
    "served", "end_backlog", "capacity", "aar_pred", "status",
)
FORECAST_COLUMNS = (
    *SNAPSHOT_KEY, "aar_pred", "aar_lower", "aar_upper", "status", "source", "source_id",
    "label_kind", "features_available_at_utc", "model_train_end_utc",
    "model_selection_end_utc", "run_id", "model_version", "coverage",
)
FLIGHT_COLUMNS = (
    "flight_id", "origin", "dest", "carrier", "flight_number", "scheduled_dep_utc",
    "scheduled_arr_utc", "dep_delay_min", "arr_delay_min", "cancelled", "diverted",
    "coverage", "source_id",
)
WEATHER_COLUMNS = (
    "airport", "issued_at_utc", "available_at_utc", "valid_from_utc", "valid_to_utc", "kind",
    "condition", "probability", "bulletin_id", "source_id", "source", "wind_direction_deg",
    "wind_speed_kt", "wind_gust_kt", "visibility_sm", "ceiling_ft_agl", "temperature_c",
)
WEATHER_FEATURES = (
    "crosswind_kt", "tailwind_kt", "wind_speed_kt", "wind_gust_kt", "visibility_sm",
    "ceiling_ft_agl", "temperature_c", "precip_flag", "thunderstorm_flag",
)

RISK_TABLES = {
    "predictions": TableSpec(
        "artifacts/risk/predictions.parquet", PREDICTION_COLUMNS,
        ("flight_id", *SNAPSHOT_KEY), ("asof_utc", "target_hour_utc"), _check_predictions,
    ),
    "normalized_metrics": TableSpec(
        "artifacts/risk/normalized_metrics.parquet", METRIC_COLUMNS,
        ("airport", "period_start_utc", "split"), ("period_start_utc", "period_end_utc"), _check_metrics,
    ),
}
DECISION_TABLES = {
    "queue": TableSpec(
        "artifacts/risk/queue.parquet", QUEUE_COLUMNS,
        ("airport", "asof_utc", "target_hour_utc", "direction"), ("asof_utc", "target_hour_utc"),
    ),
}
CAPACITY_TABLES = {
    "traffic_hourly": TableSpec(
        "artifacts/capacity/traffic_hourly.parquet",
        (
            "airport", "hour_utc", "direction", "scheduled_count", "actual_count", "coverage",
            "population", "source_id", "run_id",
        ),
        ("airport", "hour_utc", "direction"), ("hour_utc",), _check_traffic,
    ),
    "flights": TableSpec(
        "data/processed/flights.parquet", FLIGHT_COLUMNS, ("flight_id",),
        ("scheduled_dep_utc", "scheduled_arr_utc"),
    ),
    "weather": TableSpec(
        "artifacts/capacity/weather.parquet", WEATHER_COLUMNS, (),
        ("issued_at_utc", "available_at_utc", "valid_from_utc", "valid_to_utc"),
    ),
    "weather_features": TableSpec(
        "artifacts/capacity/weather_features.parquet",
        (*SNAPSHOT_KEY, "available_at_utc", "source_id", "status", *WEATHER_FEATURES),
        tuple(SNAPSHOT_KEY), ("asof_utc", "target_hour_utc", "available_at_utc"), _check_snapshot,
    ),
    "forecast": TableSpec(
        "artifacts/capacity/forecast.parquet", FORECAST_COLUMNS, tuple(SNAPSHOT_KEY),
        (
            "asof_utc", "target_hour_utc", "features_available_at_utc",
            "model_train_end_utc", "model_selection_end_utc",
        ),
        _check_forecast,
    ),
    "eligible_flights": TableSpec(
        "data/processed/eligible_flights.parquet", ("flight_id", "airport", "asof_utc"),
        ("flight_id", "airport", "asof_utc"), ("asof_utc",),
    ),
}


ESTIMATE_LABEL = "model_estimated_capacity"
ESTIMATE_COLUMNS = (
    *FORECAST_COLUMNS, "aar_observed", "population", "estimation_method", "assumptions_id",
    "validation_target", "uncertainty_kind", "support_n",
)


def _check_estimate(df: pd.DataFrame) -> list[str]:
    """Optional capacity-proxy group: never facility AAR, never an observed label."""
    problems = _check_forecast(df)
    if (df["label_kind"] != ESTIMATE_LABEL).any():
        problems.append(f"label_kind must be {ESTIMATE_LABEL!r}")
    if df["aar_observed"].notna().any():
        problems.append("aar_observed must be null for a model estimate")
    if not df["status"].isin(STATUSES).all():
        problems.append("status is not a contract status")
    usable = df["status"].isin(("available", "partial"))
    for column in ("features_available_at_utc", "model_train_end_utc", "model_selection_end_utc"):
        if df.loc[usable, column].isna().any():
            problems.append(f"usable rows with null {column}")
        elif (df.loc[usable, column] > df.loc[usable, "asof_utc"]).any():
            problems.append(f"usable rows with {column} after the cutoff")
    # Usable proxy rates and support must survive numeric coercion, including infinities.
    for column in ("aar_pred", "support_n"):
        values = pd.to_numeric(df.loc[usable, column], errors="coerce")
        valid = np.isfinite(values) & (values >= 0)
        if column == "support_n":
            valid &= values == np.floor(values)
            valid &= ~df.loc[usable, column].map(lambda value: isinstance(value, (bool, np.bool_)))
        if not valid.all():
            problems.append(f"usable {column} must be finite nonnegative" + (" integers" if column == "support_n" else ""))
    for column in ("population", "estimation_method", "assumptions_id", "model_version", "validation_target", "uncertainty_kind"):
        valid = df[column].map(lambda value: isinstance(value, str) and bool(value.strip()))
        if not valid.all():
            problems.append(f"{column} must be nonempty text")
    for column in ("estimation_method", "assumptions_id", "model_version", "population", "validation_target"):
        if df[column].nunique(dropna=False) > 1:
            problems.append(f"{column} differs within forecast publication")
    if (df.loc[usable, "model_train_end_utc"] > df.loc[usable, "model_selection_end_utc"]).any():
        problems.append("model_train_end_utc after model_selection_end_utc")
    if not df["population"].str.contains("reporting carrier", case=False, na=False).all():
        problems.append("population must identify reporting carriers")
    if not (df["validation_target"] == "high_demand_observed_reporting_carrier_arrivals").all():
        problems.append("validation_target must identify the reporting-carrier throughput proxy")
    # Any supplied interval must be complete, finite, nonnegative and enclose its estimate.
    bounds_present = df[["aar_lower", "aar_upper"]].notna().any(axis=1)
    lower = pd.to_numeric(df.loc[bounds_present, "aar_lower"], errors="coerce")
    upper = pd.to_numeric(df.loc[bounds_present, "aar_upper"], errors="coerce")
    pred = pd.to_numeric(df.loc[bounds_present, "aar_pred"], errors="coerce")
    if not (np.isfinite(lower) & np.isfinite(upper) & np.isfinite(pred)
            & (lower >= 0) & (lower <= pred) & (pred <= upper)).all():
        problems.append("bounds must be finite nonnegative and enclose aar_pred")
    no_bounds = df["uncertainty_kind"] == "unavailable"
    if df.loc[no_bounds, ["aar_lower", "aar_upper"]].notna().any().any():
        problems.append("bounds present although uncertainty_kind is unavailable")
    return problems


ESTIMATE_TABLES = {
    "capacity_estimate": TableSpec(
        "artifacts/capacity_estimate/forecast.parquet", ESTIMATE_COLUMNS, tuple(SNAPSHOT_KEY),
        (
            "asof_utc", "target_hour_utc", "features_available_at_utc",
            "model_train_end_utc", "model_selection_end_utc",
        ),
        _check_estimate,
    ),
}
ESTIMATE_DOCUMENTS = {
    "capacity_estimate_evaluation": "artifacts/capacity_estimate/evaluation.json",
    "capacity_estimate_assumptions": "artifacts/capacity_estimate/assumptions.json",
    "capacity_estimate_model": "artifacts/capacity_estimate/model.json",
}


def read_json(path: Path) -> dict:
    def reject(token: str):
        raise ArtifactError(f"{token} is not valid contract JSON")

    try:
        document = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ArtifactError(f"malformed JSON: {error}") from error
    if not isinstance(document, dict):
        raise ArtifactError("expected a JSON object")
    return document


def envelope_problems(document: dict) -> list[str]:
    problems = []
    if document.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version {document.get('schema_version')!r}, need {SCHEMA_VERSION}")
    if not document.get("run_id"):
        problems.append("run_id missing")
    if document.get("status") not in STATUSES:
        problems.append(f"status {document.get('status')!r} is not a contract status")
    stamp = pd.to_datetime(document.get("generated_at_utc"), errors="coerce", utc=False)
    if pd.isna(stamp) or stamp.tzinfo is None:
        problems.append("generated_at_utc is not a timezone-aware timestamp")
    return problems


def declared_hashes(manifest: dict) -> dict[str, dict]:
    """Normalise a manifest's file declarations to {basename: {sha256, rows}}."""
    declared: dict[str, dict] = {}

    def add(path: str, value) -> None:
        entry = value if isinstance(value, dict) else {"sha256": value}
        declared[Path(str(path).replace("\\", "/")).name] = {
            "sha256": entry.get("sha256") or entry.get("hash"),
            "rows": entry.get("rows", entry.get("row_count")),
        }

    for section in ("artifact_hashes", "outputs", "artifacts", "files"):
        content = manifest.get(section)
        if isinstance(content, dict):
            for path, value in content.items():
                add(path, value)
        elif isinstance(content, list):
            for entry in content:
                if isinstance(entry, dict) and entry.get("path"):
                    add(entry["path"], entry)
    return declared


def _verify_file(path: Path, declared: dict[str, dict]) -> dict:
    entry = declared.get(path.name)
    if entry is None or not entry["sha256"]:
        raise ArtifactError("no hash declared in its manifest")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != str(entry["sha256"]).removeprefix("sha256:").lower():
        raise ArtifactError("SHA256 differs from manifest (partial write or mixed generation)")
    return entry


def validate_table(df: pd.DataFrame, spec: TableSpec) -> list[str]:
    missing = [c for c in spec.required if c not in df.columns]
    if missing:
        return [f"missing columns {missing}"]
    problems = []
    for column in spec.utc:
        dtype = df[column].dtype
        if not isinstance(dtype, pd.DatetimeTZDtype) or str(dtype.tz) != "UTC":
            problems.append(f"{column} is not timezone-aware UTC")
    if problems:
        return problems
    if spec.key:
        key = list(spec.key)
        if df[key].isna().any().any():
            problems.append(f"null values in key {key}")
        duplicates = int(df.duplicated(key).sum())
        if duplicates:
            problems.append(f"{duplicates} duplicate rows on key {key}")
    if spec.check and not df.empty and not problems:
        problems.extend(spec.check(df))
    return problems


def _load_group(root, manifest_path, specs, documents, tables, docs) -> Group:
    group = Group()
    names = [*specs, *documents]
    path = root / manifest_path
    if not path.exists():
        group.problems = {n: [f"{manifest_path} is not published"] for n in names}
        return group
    try:
        manifest = read_json(path)
        problems = envelope_problems(manifest)
    except (ArtifactError, OSError) as error:
        manifest, problems = None, [str(error)]
    if problems:
        message = f"{manifest_path} rejected: {'; '.join(problems)}"
        group.problems = {n: [message] for n in names}
        return group
    group.manifest = manifest
    declared = declared_hashes(manifest)

    for name, spec in specs.items():
        file = root / spec.path
        if not file.exists():
            group.problems[name] = [f"{spec.path} is not published"]
            continue
        try:
            entry = _verify_file(file, declared)
            df = pd.read_parquet(file)
            problems = validate_table(df, spec)
            if entry["rows"] is not None and int(entry["rows"]) != len(df):
                problems.append(f"{len(df)} rows, manifest declares {entry['rows']}")
            if "run_id" in df and not df.empty and set(df["run_id"]) != {manifest["run_id"]}:
                problems.append("run_id differs from manifest")
        except Exception as error:  # A damaged file must never stop the app.
            problems = [f"{type(error).__name__}: {error}"]
        if problems:
            group.problems[name] = [f"{spec.path} rejected: {p}" for p in problems]
        else:
            tables[name] = df

    for name, relative in documents.items():
        file = root / relative
        if not file.exists():
            group.problems[name] = [f"{relative} is not published"]
            continue
        try:
            _verify_file(file, declared)
            document = read_json(file)
            problems = envelope_problems(document)
            if document.get("run_id") != manifest["run_id"]:
                problems.append("run_id differs from manifest")
        except (ArtifactError, OSError) as error:
            problems = [str(error)]
        if problems:
            group.problems[name] = [f"{relative} rejected: {p}" for p in problems]
        else:
            docs[name] = document
    return group


def _validate_estimate_publication(tables: dict, docs: dict, group: Group) -> None:
    """Compare declared metadata when present; legacy envelope-only docs remain supported."""
    table = tables.get("capacity_estimate")
    if table is None:
        return
    problems = []
    for name in ESTIMATE_DOCUMENTS:
        if name not in docs:
            problems.append(f"{name} missing or rejected")
    mapping = {"model_version": "model_version", "assumptions_id": "assumptions_id",
               "population": "population", "label_kind": "label_kind",
               "validation_target": "validation_target", "method": "estimation_method"}
    for name in ESTIMATE_DOCUMENTS:
        document = docs.get(name, {})
        if document and document.get("status") not in ("available", "partial"):
            problems.append(f"{name} is unavailable")
        for field, column in mapping.items():
            if field not in document:
                continue
            value = document[field]
            if field == "method" and isinstance(value, dict):
                value = value.get("name")
            if not isinstance(value, str) or not value.strip() or not table[column].eq(value).all():
                problems.append(f"{name} {field} differs from forecast")
    if problems:
        group.problems.setdefault("capacity_estimate", []).extend(problems)
        tables.pop("capacity_estimate", None)


def is_schedule_only(model_kind: str) -> bool:
    kind = str(model_kind).lower()
    return "schedule" in kind and "weather" not in kind


def _capability(name, loaded, reasons, group, published=None) -> Capability:
    """Loaded evidence is required; the producer's own status can only lower it."""
    run_id = group.manifest["run_id"] if group.manifest else None
    if not loaded:
        return Capability(name, "unavailable", list(reasons), run_id)
    entry = ((group.manifest or {}).get("capabilities") or {}).get(published) or {}
    status = entry.get("status") if entry.get("status") in STATUSES else "available"
    return Capability(name, status, [str(entry["reason"])] if entry.get("reason") else [], run_id)


def _published(group: Group, name: str) -> bool:
    entry = ((group.manifest or {}).get("capabilities") or {}).get(name) or {}
    return "predictions" not in group.problems and entry.get("status") in ("available", "partial")


def _capabilities(tables, docs, groups) -> list[Capability]:
    risk, decision, capacity = groups["risk"], groups["decision"], groups["capacity"]
    predictions = tables.get("predictions")
    kinds = set(predictions["model_kind"]) if predictions is not None else set()
    schedule_kinds = {k for k in kinds if is_schedule_only(k)}
    weather_loaded = "weather_features" in tables
    forecast = tables.get("forecast")
    aar_ready = (
        forecast is not None
        and not forecast.empty
        and (docs.get("capacity_evaluation") or {}).get("status") in ("available", "partial")
    )

    capabilities = [
        _capability(
            "Schedule risk", bool(schedule_kinds) or _published(risk, "schedule_risk"),
            risk.problems.get("predictions", ["no schedule-only predictions published"]), risk,
            "schedule_risk",
        ),
        _capability(
            "Weather risk", bool(kinds - schedule_kinds) and weather_loaded,
            ["no weather-enhanced predictions with verified weather features published"], risk,
            "weather_risk",
        ),
        _capability(
            "Normalised history", "normalized_metrics" in tables,
            risk.problems.get("normalized_metrics", []), risk, "normalized_observed_delays",
        ),
        _capability(
            "Weather features", weather_loaded,
            capacity.problems.get("weather_features", []), capacity,
        ),
        _capability(
            "AAR forecast", aar_ready,
            capacity.problems.get("forecast", [])
            + capacity.problems.get("capacity_evaluation", [])
            + (docs.get("capacity_evaluation") or {}).get("missing_inputs", [])
            or ["no AAR forecast rows are published"],
            capacity,
        ),
        _capability(
            "Flight traffic", "flights" in tables, capacity.problems.get("flights", []), capacity
        ),
        _capability(
            "Reporting-carrier traffic", "traffic_hourly" in tables,
            capacity.problems.get("traffic_hourly", []), capacity,
        ),
    ]
    estimate = groups.get("capacity_estimate", Group())
    capabilities.append(
        _capability(
            "Capacity estimate (proxy)",
            "capacity_estimate" in tables and "capacity_estimate_evaluation" in docs,
            estimate.problems.get("capacity_estimate", [])
            + estimate.problems.get("capacity_estimate_evaluation", [])
            or ["artifacts/capacity_estimate/manifest.json is not published"],
            estimate, "capacity_estimate",
        )
    )
    recommendations = docs.get("recommendations") or {}
    queue = tables.get("queue")
    missing = [str(m) for m in recommendations.get("missing_inputs", [])]
    gate = missing or decision.problems.get("recommendations", [])
    capabilities.append(
        _capability(
            "Arrival queue", queue is not None and not queue.empty,
            gate or decision.problems.get("queue", ["queue is empty"]), decision,
        )
    )
    capabilities.append(
        _capability(
            "Review advisory", bool(recommendations.get("recommendations")),
            gate or ["no deficit at the published snapshot, so no action is advised"], decision,
        )
    )
    rescheduled = any(r.get("revised_times") for r in recommendations.get("recommendations", []))
    capabilities.append(
        _capability(
            "Flight rescheduling", rescheduled and "eligible_flights" in tables,
            ["no verified flight state/eligibility; revised times are withheld"], decision,
        )
    )
    return capabilities


def _watched_paths() -> list[str]:
    paths = [
        "artifacts/risk/manifest.json", "artifacts/risk/decision_manifest.json",
        "artifacts/capacity/manifest.json", "artifacts/risk/evaluation.json",
        "artifacts/risk/recommendations.json", "artifacts/capacity/evaluation.json",
        "artifacts/capacity/data_access.json", "data/processed/provenance.json",
    ]
    for specs in (RISK_TABLES, DECISION_TABLES, CAPACITY_TABLES, ESTIMATE_TABLES):
        paths.extend(spec.path for spec in specs.values())
    paths.extend(ESTIMATE_DOCUMENTS.values())
    paths.append("artifacts/capacity_estimate/manifest.json")
    return paths


def fingerprint(root: Path) -> str:
    """Change detector for caching: any published file changing starts a new load."""
    parts = []
    for relative in _watched_paths():
        path = root / relative
        if path.exists():
            stat = path.stat()
            parts.append(f"{relative}:{stat.st_mtime_ns}:{stat.st_size}")
    for relative in [*_watched_paths()[:3], "artifacts/capacity_estimate/manifest.json"]:
        path = root / relative
        if path.exists():
            parts.append(hashlib.sha256(path.read_bytes()).hexdigest())
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def load_bundle(root: Path) -> Bundle:
    root = Path(root)
    tables: dict[str, pd.DataFrame] = {}
    docs: dict[str, dict] = {}
    groups = {
        "risk": _load_group(
            root, "artifacts/risk/manifest.json", RISK_TABLES,
            {"risk_evaluation": "artifacts/risk/evaluation.json"}, tables, docs,
        ),
        "decision": _load_group(
            root, "artifacts/risk/decision_manifest.json", DECISION_TABLES,
            {"recommendations": "artifacts/risk/recommendations.json"}, tables, docs,
        ),
        "capacity": _load_group(
            root, "artifacts/capacity/manifest.json", CAPACITY_TABLES,
            {"capacity_evaluation": "artifacts/capacity/evaluation.json"}, tables, docs,
        ),
        # optional, independently hashed; absence leaves the baseline app unchanged
        "capacity_estimate": _load_group(
            root, "artifacts/capacity_estimate/manifest.json", ESTIMATE_TABLES, ESTIMATE_DOCUMENTS, tables, docs,
        ),
    }
    _validate_estimate_publication(tables, docs, groups["capacity_estimate"])
    for name, relative in (
        ("provenance", "data/processed/provenance.json"),
        ("data_access", "artifacts/capacity/data_access.json"),
    ):
        path = root / relative
        if path.exists():
            try:
                docs[name] = read_json(path)
            except (ArtifactError, OSError) as error:
                groups["capacity"].problems[name] = [f"{relative} rejected: {error}"]
    return Bundle(
        str(root), fingerprint(root), tables, docs, groups, _capabilities(tables, docs, groups)
    )
