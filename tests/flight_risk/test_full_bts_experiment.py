import copy
import json
from hashlib import sha256

import numpy as np
import pandas as pd
import pytest

from src.flight_risk.full_bts_experiment import decision, estimator, knowledge_end, matched_alert_recall, run_full


def cells():
    return [{"airport": a, "lead": h, "incumbent": {"pr_auc": .2, "brier": .1},
             "candidate": {"pr_auc": .204, "brier": .101}}
            for a in ("KATL", "KDFW") for h in (3, 6, 12)]


def test_adoption_requires_all_cells_and_each_guardrail():
    assert decision(cells())["adopt"]
    assert not decision(cells()[:-1])["adopt"]
    rows = cells(); rows[0] = copy.deepcopy(rows[1])
    assert not decision(rows)["adopt"]
    rows = cells(); rows[0]["candidate"]["pr_auc"] = .189
    assert not decision(rows)["adopt"]
    rows = cells()
    for row in rows: row["candidate"]["brier"] = .103
    assert not decision(rows)["adopt"]
    rows = cells(); rows[0]["incumbent"]["pr_auc"] = 0
    assert not decision(rows)["adopt"]
    rows = cells(); rows[0]["candidate"]["brier"] = np.nan
    assert not decision(rows)["adopt"]


def test_equal_workload_handles_boundary_ties_fractionally():
    assert matched_alert_recall([1, 0, 1], [.8, .5, .5], 2) == .75
    assert matched_alert_recall([1, 0, 1], [.8, .5, .5], 0) == 0
    assert matched_alert_recall([1, 0, 1], [.8, .5, .5], 9) == 1
    assert matched_alert_recall([0, 0], [.1, .2], 1) is None


def test_selection_waits_for_late_year_labels_not_only_calendar():
    rows = pd.DataFrame({"scheduled_dep_utc": pd.to_datetime(["2024-12-31T23:00Z"], utc=True),
                         "dep_delay_min": [60*30]})
    assert knowledge_end(rows, "2025-01-01") == pd.Timestamp("2025-01-02T05:00Z")
    rows["dep_delay_min"] = -15
    assert knowledge_end(rows, "2025-01-01") == pd.Timestamp("2025-01-01T06:00Z")


def test_feature_allowlist_excludes_outcomes_and_keeps_new_columns_explicit():
    _, allowed = estimator(["recent_departure_count_2h", "scheduled_arrivals_target_hour"])
    assert "recent_departure_count_2h" in allowed
    assert "scheduled_arrivals_target_hour" in allowed
    assert not {"dep_delay_min", "severe_delay", "cancelled", "actual_dep_gate_utc", "flight_date"} & set(allowed)


def test_full_bts_rejects_corrupt_canonical_before_loading(tmp_path):
    canonical = tmp_path / "canonical.parquet"
    canonical.write_bytes(b"not a parquet")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"output": str(canonical), "sha256": "0"*64, "status": "built_experiment_only"}))
    with pytest.raises(ValueError, match="not verified"):
        run_full(manifest, tmp_path / "result.json")
    assert not (tmp_path / "result.json").exists()


def test_full_bts_rejects_incomplete_months_before_loading(tmp_path):
    canonical = tmp_path / "canonical.parquet"
    canonical.write_bytes(b"not a parquet")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"output": str(canonical), "sha256": sha256(canonical.read_bytes()).hexdigest(),
                                    "status": "built_experiment_only", "months": [{"month": "2023-01"}]}))
    with pytest.raises(ValueError, match="All 31"):
        run_full(manifest, tmp_path / "result.json")
