"""Held-out classification metrics and volume-normalised observed delays."""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, confusion_matrix, precision_score, recall_score, f1_score


def classification_metrics(labels, probabilities, threshold):
    labels, probabilities = np.asarray(labels, dtype=int), np.asarray(probabilities, dtype=float)
    if not len(labels):
        return {"n": 0, "severe_n": 0, "precision": None, "recall": None, "f1": None, "pr_auc": None, "brier": None, "confusion": {}}
    prediction = probabilities >= threshold
    tn, fp, fn, tp = confusion_matrix(labels, prediction, labels=[0, 1]).ravel()
    return {
        "n": int(len(labels)), "severe_n": int(labels.sum()),
        "precision": float(precision_score(labels, prediction, zero_division=0)),
        "recall": float(recall_score(labels, prediction, zero_division=0)),
        "f1": float(f1_score(labels, prediction, zero_division=0)),
        "pr_auc": float(average_precision_score(labels, probabilities)) if labels.sum() else None,
        "brier": float(brier_score_loss(labels, probabilities)),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def reliability_bins(labels, probabilities):
    labels, probabilities = np.asarray(labels, dtype=int), np.asarray(probabilities, dtype=float)
    bins = np.minimum((probabilities * 10).astype(int), 9)
    result = []
    for i in range(10):
        mask = bins == i
        if mask.any():
            result.append({"lower": i / 10, "upper": (i + 1) / 10, "n": int(mask.sum()), "mean_probability": float(probabilities[mask].mean()), "observed_severe_rate": float(labels[mask].mean())})
    return result


def normalized_delay_metrics(flights):
    """Daily UTC buckets; all delay denominators exclude cancelled/unknown labels."""
    frame = flights.copy()
    frame["period_start_utc"] = frame.scheduled_dep_utc.dt.floor("D")
    records = []
    for (airport, period, split), part in frame.groupby(["airport", "period_start_utc", "split"], dropna=False):
        eligible = part[part.cancelled.eq(0) & part.dep_delay_min.notna()]
        n, severe = len(eligible), int(eligible.dep_delay_min.gt(45).sum())
        delay = float(eligible.dep_delay_min.clip(lower=0).sum())
        records.append({
            "airport": airport, "period_start_utc": period, "period_end_utc": period + pd.Timedelta(days=1), "split": split,
            "scheduled_departures": int(len(part)), "cancelled_departures": int(part.cancelled.eq(1).sum()),
            "unknown_cancellation_departures": int((~part.cancelled.isin([0, 1])).sum()),
            "missing_delay_labels": int((part.cancelled.eq(0) & part.dep_delay_min.isna()).sum()),
            "eligible_departures": n, "severe_departures": severe,
            "severe_delay_rate": severe / n if n else None,
            "total_positive_delay_minutes": delay if n else None,
            "delay_minutes_per_flight": delay / n if n else None,
            "coverage": part.coverage.iloc[0] if part.coverage.nunique(dropna=False) == 1 else "mixed",
            "source_id": ";".join(sorted(part.source_id.dropna().astype(str).unique())),
            "kind": "observed", "requires_outcome_reveal": True,
        })
    return pd.DataFrame.from_records(records)
