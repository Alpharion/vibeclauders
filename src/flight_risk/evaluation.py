"""Retrospective held-out evaluation added after prediction.

Everything here reads outcomes, storm logs or delay causes that were not known
at the cutoff. It runs only after predictions are fixed and never feeds a
model, so it cannot change a probability or threshold.
"""
import numpy as np
import pandas as pd

from .data import WEATHER_KEYS, aware_utc
from .metrics import classification_metrics

STORM_WINDOW_HOURS = 3
MIN_COHORT_N, MIN_COHORT_SEVERE = 30, 5
CAUSE_COLUMNS = {
    "cause_carrier_delay_min": "carrier", "cause_weather_delay_min": "weather", "cause_nas_delay_min": "national airspace system",
    "cause_security_delay_min": "security", "cause_late_aircraft_delay_min": "late-arriving aircraft",
}
COHORT_METRICS = ["pr_auc", "precision", "recall", "brier"]


def load_storm_events(path):
    """Validated NOAA events: retrospective annotation only, never predictors."""
    events = pd.read_parquet(path)
    required = {"airport", "event_type", "begin_utc", "end_utc"}
    if missing := required - set(events.columns):
        raise ValueError(f"Storm events missing columns: {sorted(missing)}")
    events = events.copy()
    for column in ["begin_utc", "end_utc"]:
        events[column] = aware_utc(events[column])
    valid = events.begin_utc.notna() & events.end_utc.notna() & events.end_utc.ge(events.begin_utc)
    return events[valid].reset_index(drop=True), int((~valid).sum())


def storm_flags(test, events, window_hours=STORM_WINDOW_HOURS):
    """True where an event overlaps [target - w, target + 1h + w) at the same airport."""
    flags = np.zeros(len(test), dtype=bool)
    nearest = [None] * len(test)
    window = pd.Timedelta(hours=window_hours)
    for airport, part in test.groupby("airport"):
        local = events[events.airport.eq(airport)]
        if local.empty:
            continue
        start = (part.target_hour_utc - window).to_numpy()[:, None]
        end = (part.target_hour_utc + pd.Timedelta(hours=1) + window).to_numpy()[:, None]
        overlap = (local.begin_utc.to_numpy()[None, :] < end) & (local.end_utc.to_numpy()[None, :] >= start)
        positions = test.index.get_indexer(part.index)
        flags[positions] = overlap.any(axis=1)
        for row, position in zip(np.flatnonzero(overlap.any(axis=1)), positions[overlap.any(axis=1)]):
            event = local.iloc[int(np.flatnonzero(overlap[row])[0])]
            nearest[position] = {"event_type": str(event.event_type), "begin_utc": event.begin_utc.isoformat(), "end_utc": event.end_utc.isoformat()}
    return flags, nearest


def storm_cohorts(test, probabilities, baseline_probs, baseline_threshold, flags):
    rows = []
    predicted = test["_alert"].to_numpy()
    for cohort, mask in [("storm_within_3h", flags), ("no_storm_within_3h", ~flags)]:
        for (airport, horizon), part in test[mask].groupby(["airport", "horizon_hours"]):
            index = part.index.to_numpy()
            labels = part.severe_delay.to_numpy()
            n, severe = int(len(part)), int(labels.sum())
            usable = n >= MIN_COHORT_N and MIN_COHORT_SEVERE <= severe < n
            model = _metrics_with_alerts(labels, probabilities[index], predicted[index]) if usable else {}
            base = classification_metrics(labels, baseline_probs[index], baseline_threshold) if usable else {}
            if usable:
                # Threshold metrics compare equal alert workload, as in impact().
                alerts = int(predicted[index].sum())
                base_tp = _top_share(labels, baseline_probs[index], alerts)
                base["precision"] = base_tp / alerts if alerts else 0.0
                base["recall"] = base_tp / severe
            for metric in COHORT_METRICS:
                rows.append({"cohort": cohort, "airport": airport, "horizon_hours": int(horizon), "metric": metric,
                             "value": model.get(metric), "baseline_value": base.get(metric), "n": n, "severe_n": severe,
                             "status": "available" if usable else "unavailable",
                             "reason": None if usable else f"Needs n >= {MIN_COHORT_N} with at least {MIN_COHORT_SEVERE} severe and one non-severe departure"})
    return rows


def _metrics_with_alerts(labels, probabilities, alerts):
    # Mixed weather/schedule rows use their own thresholds, so score the published alerts.
    summary = classification_metrics(labels, probabilities, 0.5)
    tp = int((alerts & (labels == 1)).sum())
    flagged, positives = int(alerts.sum()), int(labels.sum())
    summary["precision"] = tp / flagged if flagged else 0.0
    summary["recall"] = tp / positives if positives else 0.0
    return summary


def _top_share(labels, scores, k):
    """Expected true positives when flagging the k highest scores; ties are shared pro rata."""
    if k <= 0:
        return 0.0
    order = np.sort(np.unique(scores))[::-1]
    selected, positives = 0, 0.0
    for value in order:
        group = scores == value
        size = int(group.sum())
        if selected + size <= k:
            selected += size
            positives += labels[group].sum()
        else:
            positives += (k - selected) * labels[group].mean()
            break
    return float(positives)


def impact(test, baseline_probs):
    """Model alerts vs the status-quo historical rate flagging the same number of departures."""
    comparisons = []
    for (airport, horizon), part in test.groupby(["airport", "horizon_hours"]):
        labels = part.severe_delay.to_numpy()
        alerts = part["_alert"].to_numpy()
        n, k, positives = int(len(part)), int(alerts.sum()), int(labels.sum())
        model_tp = int((alerts & (labels == 1)).sum())
        base_tp = _top_share(labels, baseline_probs[part.index.to_numpy()], k)
        comparisons.append({
            "airport": airport, "horizon_hours": int(horizon), "n": n, "severe_n": positives, "alerts": k,
            "alert_share": k / n if n else None,
            "model_recall": model_tp / positives if positives else None, "baseline_recall": base_tp / positives if positives else None,
            "model_precision": model_tp / k if k else None, "baseline_precision": base_tp / k if k else None,
            "model_true_alerts": model_tp, "baseline_expected_true_alerts": base_tp,
        })
    return {
        "basis": "Held-out test departures. At each airport/lead the baseline flags the same number of departures as the model, choosing the highest historical rates; tied rates are shared pro rata (expected value).",
        "status_quo": "Training-only (2023) airport/local-hour severe-delay rate: the historical statistic a duty officer could consult without a model.",
        "comparisons": comparisons,
        "limitations": [
            "Measures alert quality only: recall and precision of severe-delay flags at equal alert workload.",
            "No delay-minute, fuel, cost or savings benefit is claimed; no intervention was simulated or tested.",
            "Sample coverage (about 0.8% of airport traffic); results describe this sample, not airport-wide operations.",
        ],
    }


def alert_rates(test):
    rows = []
    for (airport, horizon), part in test.groupby(["airport", "horizon_hours"]):
        alerts, scored, severe = int(part["_alert"].sum()), int(len(part)), int(part.severe_delay.sum())
        rows.append({"airport": airport, "horizon_hours": int(horizon), "alerts": alerts, "scored": scored,
                     "alert_rate": alerts / scored if scored else None, "observed_severe": severe,
                     "observed_severe_rate": severe / scored if scored else None})
    return rows


def _weather_evidence(row, features):
    present = {name: (None if pd.isna(row[name]) else float(row[name])) for name in features if name in row.index}
    return {key: value for key, value in present.items() if value is not None}


def _flag_summary(weather):
    flags = [label for name, label in [("thunderstorm_flag", "thunderstorms"), ("precip_flag", "precipitation")] if weather.get(name) == 1]
    return " and ".join(flags) if flags else "neither thunderstorms nor precipitation"


def _causes(row):
    causes = {label: float(row[column]) for column, label in CAUSE_COLUMNS.items() if column in row.index and pd.notna(row[column]) and row[column] > 0}
    return dict(sorted(causes.items(), key=lambda item: -item[1]))


def _case(kind, row, probability, threshold, evidence, explanation, remedy):
    return {
        "kind": kind, "flight_id": row.flight_id, "airport": row.airport, "horizon_hours": int(row.horizon_hours),
        "asof_utc": row.asof_utc.isoformat(), "target_hour_utc": row.target_hour_utc.isoformat(),
        "probability": None if probability is None else float(probability), "threshold": float(threshold),
        "observed": {"severe_delay": int(row.severe_delay), "dep_delay_min": float(row.dep_delay_min)},
        "evidence": evidence, "explanation": explanation, "remedy": remedy, "requires_outcome_reveal": True,
    }


def failure_cases(test, probabilities, thresholds, model_kind, storm_nearest, weather_features, weather_table=None):
    """One missed severe delay, one false alarm and one declined weather prediction, with evidence."""
    cases = []
    frame = test.assign(_p=probabilities, _t=thresholds, _kind=model_kind, _storm=storm_nearest)
    misses = frame[(frame.severe_delay.eq(1)) & ~frame._alert]
    if not misses.empty:
        # Prefer a miss with retrospective storm evidence, then the largest observed delay.
        misses = misses.assign(_has_storm=misses._storm.notna()).sort_values(["_has_storm", "dep_delay_min", "flight_id"], ascending=[False, False, True])
        row = misses.iloc[0]
        causes = _causes(row)
        evidence = {"model_kind": row._kind, "weather_at_cutoff": _weather_evidence(row, weather_features),
                    "retrospective_storm_event": row._storm, "bts_reported_delay_causes_min": causes or None}
        reasons = []
        if causes:
            top, minutes = next(iter(causes.items()))
            reasons.append(f"BTS attributes the largest share ({minutes:.0f} of {row.dep_delay_min:.0f} min) to {top} delay")
        if row._storm:
            reasons.append(f"NOAA logged a {row._storm['event_type']} near the airport overlapping the target hour, while the forecast at the cutoff indicated {_flag_summary(evidence['weather_at_cutoff'])}")
        explanation = (f"Probability {row._p:.3f} stayed below threshold {row._t:.3f}. " + "; ".join(reasons) + ". These are retrospective records consistent with the miss, not a proven cause.") if reasons else "Probability stayed below threshold and no cutoff-time feature indicated elevated risk; the data do not identify a cause."
        if causes and next(iter(causes)) in {"carrier", "late-arriving aircraft"}:
            remedy = "Carrier and upstream-aircraft delays are not observable from weather or schedule features; catching them needs a cutoff-safe inbound-aircraft or carrier-status source. Human review remains required."
        else:
            remedy = "Re-score as the lead shortens and newer forecasts arrive; storm onset after the cutoff cannot be in the features. Human review remains required."
        cases.append(_case("missed", row, row._p, row._t, evidence, explanation, remedy))
    alarms = frame[frame.severe_delay.eq(0) & frame._alert]
    if not alarms.empty:
        row = alarms.sort_values(["_p", "flight_id"], ascending=[False, True]).iloc[0]
        weather = _weather_evidence(row, weather_features)
        evidence = {"model_kind": row._kind, "weather_at_cutoff": weather, "retrospective_storm_event": row._storm}
        explanation = (f"Highest-probability false alarm ({row._p:.3f} against threshold {row._t:.3f}); observed delay {row.dep_delay_min:.0f} min. "
                       f"The forecast at the cutoff indicated {_flag_summary(weather)}"
                       + (", but no NOAA storm event was logged near the target hour" if not row._storm else "")
                       + ". Risk scores are probabilities, so some flagged departures will operate normally.")
        remedy = "Treat alerts as prompts for review, not actions; the validation-chosen threshold trades extra alerts for recall."
        cases.append(_case("false_alarm", row, row._p, row._t, evidence, explanation, remedy))
    declined = frame[frame._kind.eq("schedule_only")]
    if not declined.empty and "weather_available" in frame:
        row = declined.sort_values(["asof_utc", "flight_id"]).iloc[0]
        status = None
        if weather_table is not None:
            key = weather_table[WEATHER_KEYS].assign(_i=range(len(weather_table)))
            match = key[key.airport.eq(row.airport) & key.asof_utc.eq(row.asof_utc) & key.target_hour_utc.eq(row.target_hour_utc) & key.horizon_hours.eq(row.horizon_hours)]
            status = weather_table.iloc[int(match._i.iloc[0])].status if len(match) else "absent"
        evidence = {"model_kind": "schedule_only", "weather_snapshot_status": status}
        explanation = (f"The weather snapshot for this cutoff was not accepted (status: {status}), so the weather-enhanced prediction was withheld and the schedule-only model was used instead."
                       if status else "No accepted weather snapshot existed for this cutoff, so the weather-enhanced prediction was withheld.")
        remedy = "Label the row as schedule-only in the interface; it carries no lead-specific weather signal."
        cases.append(_case("declined", row, row._p, row._t, evidence, explanation, remedy))
    return cases


def retrospective_evaluation(test, probabilities, thresholds, model_kind, baseline_probs, baseline_threshold, weather_features, storm_events_path=None, weather_table=None):
    test = test.reset_index(drop=True).assign(_alert=probabilities >= thresholds)
    result = {"impact": impact(test, baseline_probs), "alert_rates": alert_rates(test), "storm_cohorts": [],
              "storm_annotation": {"status": "unavailable", "reason": "No storm events supplied"}}
    nearest = [None] * len(test)
    if storm_events_path is not None:
        events, invalid = load_storm_events(storm_events_path)
        flags, nearest = storm_flags(test, events)
        result["storm_cohorts"] = storm_cohorts(test, probabilities, baseline_probs, baseline_threshold, flags)
        result["storm_annotation"] = {
            "status": "available", "events": int(len(events)), "invalid_event_rows": invalid,
            "definition": f"Storm cohort: a NOAA Storm Events record for the airport's vicinity overlaps [target hour - {STORM_WINDOW_HOURS}h, target hour + 1h + {STORM_WINDOW_HOURS}h).",
            "use": "Retrospective evaluation only; never a model feature or replay input.",
            "baseline_comparison": "pr_auc and brier are threshold-free; baseline precision/recall flag the same number of departures as the model within each cohort.",
            "storm_rows": int(flags.sum()), "scored_rows": int(len(test)),
        }
    result["failure_cases"] = failure_cases(test, probabilities, thresholds, model_kind, nearest, weather_features, weather_table)
    return result
