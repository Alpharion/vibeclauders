"""AAR label handling and model plumbing. All label data here is SYNTHETIC and
exists only to test code paths; no synthetic number is ever published."""
import numpy as np
import pandas as pd
import pytest

from src.data_capacity import capacity
from src.data_capacity.config import CAPACITY_DIR, resolve_airports
from src.data_capacity.features import FEATURE_COLUMNS

AIRPORTS = resolve_airports(["KATL", "KDFW"])


def test_no_labels_is_unavailable(tmp_path):
    lab, audit = capacity.load_aar_labels(AIRPORTS, files=[])
    assert audit["status"] == "unavailable" and lab.empty


def test_quarter_hour_rates_are_averaged_not_summed(tmp_path):
    p = tmp_path / "aspm.csv"
    pd.DataFrame({"LOCID": ["ATL"] * 8, "YYYYMMDD": ["20240601"] * 8, "HR_LOCAL": [10] * 4 + [11] * 4,
                  "QTR": [1, 2, 3, 4, 1, 2, 3, 4], "AAR": [120, 120, 100, 100, 90, 90, 90, None]}).to_csv(p, index=False)
    lab, audit = capacity.load_aar_labels(AIRPORTS, files=[p])
    assert len(lab) == 1  # 11:00 has a missing quarter -> null, dropped
    assert lab.iloc[0].aar == 110
    assert lab.iloc[0].target_hour_utc == pd.Timestamp("2024-06-01 14:00", tz="UTC")  # 10:00 EDT
    assert audit["incomplete_quarter_hours"] == 1


def test_unknown_hour_basis_rejected(tmp_path):
    p = tmp_path / "x.csv"
    pd.DataFrame({"airport": ["ATL"], "date": ["2024-06-01"], "hour": [3], "aar": [100]}).to_csv(p, index=False)
    with pytest.raises(capacity.LabelError):
        capacity.load_aar_labels(AIRPORTS, files=[p])


def test_negative_aar_rejected(tmp_path):
    p = tmp_path / "x.csv"
    pd.DataFrame({"airport": ["KATL"], "hour_start_utc": ["2024-06-01T03:00Z"], "aar": [-5]}).to_csv(p, index=False)
    with pytest.raises(capacity.LabelError):
        capacity.load_aar_labels(AIRPORTS, files=[p])


def synthetic(seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for ap in AIRPORTS:
        t = pd.date_range("2023-01-01 06:00", "2025-07-31 23:00", freq="7h", tz="UTC")
        for h in (3, 6, 12):
            d = pd.DataFrame({"airport": ap.icao, "target_hour_utc": t, "horizon_hours": h})
            d["asof_utc"] = d.target_hour_utc - pd.to_timedelta(h, unit="h")
            rows.append(d)
    f = pd.concat(rows, ignore_index=True)
    for c in FEATURE_COLUMNS + capacity.EXTRA_FEATURES:
        f[c] = rng.uniform(0, 10, len(f))
    # same target hour -> same forecast storm flag across horizons
    targets = f[["airport", "target_hour_utc"]].drop_duplicates()
    targets["thunderstorm_flag"] = rng.integers(0, 2, len(targets))
    f = f.drop(columns="thunderstorm_flag").merge(targets, on=["airport", "target_hour_utc"])
    f["status"], f["source_id"], f["taf_bulletin_id"] = "available", "synthetic", "synthetic"
    f["available_at_utc"] = f["asof_utc"]
    lab = f[["airport", "target_hour_utc", "thunderstorm_flag"]].drop_duplicates(["airport", "target_hour_utc"])
    lab["aar"] = 100 - 30 * lab.thunderstorm_flag + rng.normal(0, 3, len(lab))
    return f, lab[["airport", "target_hour_utc", "aar"]]


def test_fit_evaluate_split_and_no_test_leakage():
    f, lab = synthetic()
    fc, rep = capacity.fit_evaluate(f, lab, AIRPORTS, "test-run")
    assert set(fc.split) == {"test"} and (fc.aar_pred >= 0).all()
    assert (fc.asof_utc >= fc.model_selection_end_utc).all()  # no replay cutoff before selection end
    assert (fc.features_available_at_utc <= fc.asof_utc).all()
    assert {(m["airport"], m["horizon_hours"]) for m in rep["metrics"]} == {(a.icao, h) for a in AIRPORTS for h in (3, 6, 12)}
    assert all(m["value"] < m["baseline_value"] for m in rep["metrics"])  # weather signal beats hour baseline here
    # perturbing TEST labels must not change predictions or baselines
    lab2 = lab.copy()
    test_mask = lab2.target_hour_utc >= pd.Timestamp("2025-01-01 06:00", tz="UTC")
    lab2.loc[test_mask, "aar"] += 1000
    fc2, _ = capacity.fit_evaluate(f, lab2, AIRPORTS, "test-run")
    pd.testing.assert_series_equal(fc.aar_pred.reset_index(drop=True), fc2.aar_pred.reset_index(drop=True))
    pd.testing.assert_series_equal(fc.aar_baseline.reset_index(drop=True), fc2.aar_baseline.reset_index(drop=True))


def test_labels_not_covering_split_refuse_metrics():
    f, lab = synthetic()
    with pytest.raises(capacity.LabelError):
        capacity.fit_evaluate(f, lab[lab.target_hour_utc < pd.Timestamp("2024-01-01", tz="UTC")], AIRPORTS, "r")


@pytest.mark.skipif(not (CAPACITY_DIR / "forecast.parquet").exists(), reason="no published forecast")
def test_published_forecast_schema_and_honest_status():
    import json

    fc = pd.read_parquet(CAPACITY_DIR / "forecast.parquet")
    assert list(fc.columns) == list(capacity.FORECAST_COLUMNS)
    ev = json.loads((CAPACITY_DIR / "evaluation.json").read_text(encoding="utf-8"))
    if ev["status"] != "available":
        assert fc.empty and ev["metrics"] == [] and ev["missing_inputs"]
    else:
        assert (fc.label_kind == "facility_aar").all()


def test_aar_attempt_log_loads_and_rejects_malformed(tmp_path):
    import json

    from src.data_capacity.pipeline import load_aar_attempts

    good = {"attempts": [{"at_utc": "2026-10-31T06:00:00Z", "channel": "email", "requested_by": "supervisor",
                          "request": "ASPM extract", "response": "pending", "status": "pending"},
                         {"at_utc": "2026-10-31T04:00:00Z", "channel": "web", "requested_by": "agent",
                          "request": "access check", "response": "login required", "status": "refused_no_credentials"}]}
    p = tmp_path / "attempts.json"
    p.write_text(json.dumps(good))
    assert [a["channel"] for a in load_aar_attempts(p)] == ["web", "email"]  # chronological
    assert load_aar_attempts(tmp_path / "absent.json") == []
    p.write_text(json.dumps({"attempts": [{"at_utc": "2026-10-31T06:00:00", "channel": "x"}]}))
    with pytest.raises(ValueError):
        load_aar_attempts(p)


def test_repository_attempt_log_is_valid():
    from src.data_capacity.pipeline import load_aar_attempts

    assert all(a["status"] for a in load_aar_attempts())


def test_aar_observed_is_the_held_out_label_only():
    f, lab = synthetic(seed=3)
    fc, _ = capacity.fit_evaluate(f, lab, AIRPORTS, "r")
    j = fc.merge(lab, on=["airport", "target_hour_utc"])
    assert len(j) == len(fc) and np.allclose(j.aar_observed, j.aar)
    assert set(fc.split) == {"test"}
    assert "aar_observed" in capacity.empty_forecast().columns
