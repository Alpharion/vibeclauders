"""Optional capacity-estimate group (SYNTHETIC fixtures only)."""
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard import views
from src.dashboard.app import cached_bundle
from src.dashboard.data import load_bundle
from tests.dashboard import conftest as c

ROOT = Path(__file__).resolve().parents[2]
EST_RUN = "synthetic-estimate"


def estimate_table(**overrides) -> pd.DataFrame:
    rows = []
    for icao in ("KATL", "KDFW"):
        for lead in (3, 6, 12):
            asof = c.ASOF
            rows.append({
                "airport": icao, "asof_utc": asof, "target_hour_utc": asof + pd.Timedelta(hours=lead),
                "horizon_hours": lead, "aar_pred": 71.0 + lead, "aar_lower": None, "aar_upper": None,
                "status": "available", "source": "synthetic frontier", "source_id": "synthetic",
                "label_kind": "model_estimated_capacity", "features_available_at_utc": asof - pd.Timedelta(hours=1),
                "model_train_end_utc": asof - pd.Timedelta(days=200), "model_selection_end_utc": asof - pd.Timedelta(days=30),
                "run_id": EST_RUN, "model_version": "v1", "coverage": "held_out", "aar_observed": None,
                "population": "reporting carriers", "estimation_method": "high_demand_weather_frontier_v1",
                "assumptions_id": "a1", "validation_target": "high_demand_observed_reporting_carrier_arrivals",
                "uncertainty_kind": "unavailable", "support_n": 120, "frontier_cell": f"{icao}/h{lead}/vfr",
                "backoff_level": "regime",
            })
    df = pd.DataFrame(rows).astype({"aar_lower": "float64", "aar_upper": "float64", "aar_observed": "float64"})
    for k, v in overrides.items():
        df[k] = v
    return df


def publish_estimate(root: Path, table=None) -> None:
    metrics = [{"split": "test", "airport": "KATL", "horizon_hours": 6, "metric": "high_demand_throughput_rmse",
                "value": 20.0, "baseline_value": 21.0, "n": 50, "units": "arrivals/hour"}]
    cohorts = [{"split": "test", "airport": "KATL", "weather_regime": "vfr", "n_snapshots": 50, "n_unique_hours": 50,
                "mean_estimate": 81.0, "mean_observed": 61.0, "high_demand_throughput_rmse": 20.0}]
    docs = {
        "artifacts/capacity_estimate/evaluation.json": c.envelope(
            EST_RUN, status="partial", method="high_demand_weather_frontier_v1",
            validation_target="high_demand_observed_reporting_carrier_arrivals", metrics=metrics, cohorts=cohorts),
        "artifacts/capacity_estimate/assumptions.json": c.envelope(EST_RUN, status="partial"),
        "artifacts/capacity_estimate/model.json": c.envelope(EST_RUN, status="partial"),
    }
    c.publish(root, {"artifacts/capacity_estimate/forecast.parquet": estimate_table() if table is None else table},
              docs, "artifacts/capacity_estimate/manifest.json", EST_RUN)


def snap(icao="KATL", lead=6):
    return views.Snapshot(views.resolve_airport(icao), c.ASOF, lead)


def no_genuine_aar(root: Path) -> None:
    c.publish_capacity(root, forecast_table=c.forecast().iloc[0:0])


def test_genuine_aar_is_preferred_over_estimate(root):
    publish_estimate(root)
    row, kind, _ = views.capacity_row(load_bundle(root), snap())
    assert kind == "facility_aar" and row["aar_pred"] == 88.0


@pytest.mark.parametrize("icao", ["KATL", "KDFW"])
@pytest.mark.parametrize("lead", [3, 6, 12])
def test_estimate_used_at_exact_key_when_no_genuine_aar(root, icao, lead):
    no_genuine_aar(root)
    publish_estimate(root)
    row, kind, reason = views.capacity_row(load_bundle(root), snap(icao, lead))
    assert kind == "estimate" and row["aar_pred"] == 71.0 + lead and reason
    assert "Model proxy, not facility AAR" in views.estimate_note(row)


def test_no_estimate_at_other_keys(root):
    no_genuine_aar(root)
    publish_estimate(root)
    other = views.Snapshot(views.resolve_airport("KATL"), c.ASOF + pd.Timedelta(hours=1), 6)
    row, kind, reason = views.capacity_row(load_bundle(root), other)
    assert row is None and kind == "none" and "exact cutoff" in reason


@pytest.mark.parametrize("override,message", [
    ({"label_kind": "facility_aar"}, "label_kind"),
    ({"aar_observed": 50.0}, "aar_observed"),
    ({"features_available_at_utc": c.ASOF + pd.Timedelta(hours=1)}, "after the cutoff"),
    ({"model_selection_end_utc": pd.to_datetime([pd.NaT] * 6, utc=True)}, "null model_selection_end_utc"),
    ({"aar_lower": 10.0}, "bounds present"),
])
def test_invalid_estimate_publication_is_rejected(root, override, message):
    no_genuine_aar(root)
    publish_estimate(root, estimate_table(**override))
    bundle = load_bundle(root)
    assert bundle.table("capacity_estimate") is None
    assert message in bundle.problem("capacity_estimate")
    assert views.capacity_row(bundle, snap())[0] is None


def test_hash_mismatch_rejects_estimate(root):
    publish_estimate(root)
    path = root / "artifacts/capacity_estimate/forecast.parquet"
    estimate_table(aar_pred=1.0).to_parquet(path)
    bundle = load_bundle(root)
    assert bundle.table("capacity_estimate") is None and "SHA256" in bundle.problem("capacity_estimate")


def test_absent_estimate_leaves_baseline_unchanged(root):
    bundle = load_bundle(root)
    assert bundle.capability("Capacity estimate (proxy)").status == "unavailable"
    assert views.capacity_row(bundle, snap())[1] == "facility_aar"
    assert bundle.capability("AAR forecast").status == load_bundle(root).capability("AAR forecast").status


def test_estimate_never_enters_aar_trend_or_queue(root):
    no_genuine_aar(root)
    publish_estimate(root)
    bundle = load_bundle(root)
    assert views.aar_trend(bundle.table("forecast"), views.resolve_airport("KATL"), 6).empty
    assert bundle.capability("AAR forecast").status == "unavailable"
    queue = bundle.table("queue")
    assert queue is None or "model_estimated_capacity" not in set(queue.get("label_kind", []))
    assert "capacity_estimate" not in {"forecast", "queue"}  # separate table name in the bundle


@pytest.fixture
def run(monkeypatch):
    def start(root) -> AppTest:
        monkeypatch.setenv("DASHBOARD_DATA_ROOT", str(root))
        cached_bundle.clear()
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
        assert not app.exception
        return app

    return start


def text(app) -> str:
    parts = [e.value for kind in ("markdown", "warning", "error", "info", "caption", "title", "success")
             for e in getattr(app, kind)]
    return "\n".join(map(str, parts))


def test_app_all_airports_leads_and_reveal_with_estimate(run, root):
    no_genuine_aar(root)
    publish_estimate(root)
    app = run(root)
    for icao in ("KATL", "KDFW"):
        app.selectbox(key="airport").set_value(icao).run()
        for lead in (3, 6, 12):
            next(w for w in app.get("button_group") if w.key == "horizon").set_value(lead).run()
            for reveal in (False, True):
                app.session_state["reveal"] = reveal
                app.session_state["tab"] = "Evaluation"
                app.run()
                assert not app.exception, (icao, lead, reveal)
                body = text(app)
                assert "high_demand_weather_frontier_v1" in body  # Evaluation panel proxy section
                assert ("mean_observed" in str([f.value.columns.tolist() for f in app.dataframe])) == reveal
    app.selectbox(key="airport").set_value("KATL").run()
    next(w for w in app.get("button_group") if w.key == "horizon").set_value(6).run()
    app.session_state["tab"] = "Overview"
    app.run()
    assert any(views.ESTIMATE_TITLE in m.label for m in app.metric)
    assert "Model proxy, not facility AAR" in text(app)


def test_app_without_estimate_still_launches(run, root):
    app = run(root)
    app.session_state["tab"] = "Evaluation"
    app.run()
    assert "Capacity estimate (proxy) not loaded" in text(app)
