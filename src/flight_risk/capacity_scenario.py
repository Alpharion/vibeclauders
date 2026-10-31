"""Explicit proxy-capacity scenario inputs; never verified facility AAR.

Sparse scored horizons cannot fill a contiguous queue. The optional constant
scenario holds one published anchor rate across a window as a named assumption.
It does not interpolate forecasts or claim weather was forecast for those hours.
Callers must first load forecasts through the hash-verifying publication loader.
"""
from numbers import Integral

import numpy as np
import pandas as pd


LIMITATIONS = [
    "Model-estimated capacity for reporting carriers, not independently validated facility AAR.",
    "Scenario inputs are not eligible for the verified operational arrival queue.",
    "No delay savings, metering rate, rescheduling or intervention benefit is established.",
    "The caller must verify publication hashes before supplying this dataframe.",
]


def _scope(forecast, airport, asof_utc, window_hours):
    cutoff = pd.Timestamp(asof_utc)
    if pd.isna(cutoff) or cutoff.tzinfo is None or cutoff != cutoff.floor("h"):
        raise ValueError("asof_utc must be a timezone-aware hour boundary")
    cutoff = cutoff.tz_convert("UTC")
    if airport not in ("KATL", "KDFW"):
        raise ValueError("airport must be KATL or KDFW")
    if isinstance(window_hours, bool) or not isinstance(window_hours, Integral) or not 1 <= window_hours <= 168:
        raise ValueError("window_hours must be an integer from 1 to 168")
    required = {"airport", "asof_utc", "target_hour_utc", "horizon_hours", "aar_pred", "status",
                "label_kind", "population", "features_available_at_utc", "model_train_end_utc",
                "model_selection_end_utc", "run_id", "model_version", "source_id"}
    if not isinstance(forecast, pd.DataFrame) or not forecast.columns.is_unique or not required <= set(forecast):
        raise ValueError("forecast schema missing required columns or contains duplicate columns")
    # Never match a neighbouring cutoff or airport as a substitute.
    rows = forecast.loc[(forecast.airport == airport) & (forecast.asof_utc == cutoff)].copy()
    return rows, cutoff


def _validate(rows, cutoff):
    rows = rows.copy()
    if rows.empty:
        raise ValueError("No exact-cutoff model capacity estimates")
    for column in ("target_hour_utc", "features_available_at_utc", "model_train_end_utc", "model_selection_end_utc"):
        values = rows[column].map(pd.Timestamp)
        if not values.map(lambda v: not pd.isna(v) and v.tzinfo is not None).all():
            raise ValueError(f"{column} requires timezone-aware nonmissing values")
        if column != "target_hour_utc" and (values > cutoff).any():
            raise ValueError(f"{column} is after the cutoff")
        rows[column] = pd.to_datetime(values, utc=True)
    if rows.target_hour_utc.duplicated().any():
        raise ValueError("Duplicate capacity target hours")
    if (rows.model_train_end_utc > rows.model_selection_end_utc).any():
        raise ValueError("Training ends after model selection")
    lead = pd.to_numeric(rows.horizon_hours, errors="coerce")
    if rows.horizon_hours.map(lambda v: isinstance(v, (bool, np.bool_))).any() or not (np.isfinite(lead) & (lead >= 0) & (lead == np.floor(lead))).all():
        raise ValueError("Invalid horizon")
    if not (rows.target_hour_utc == cutoff + pd.to_timedelta(lead, unit="h")).all():
        raise ValueError("Target hour does not match the declared lead")
    rate = pd.to_numeric(rows.aar_pred, errors="coerce")
    if rows.aar_pred.map(lambda v: isinstance(v, (bool, np.bool_))).any() or not (np.isfinite(rate) & (rate >= 0)).all():
        raise ValueError("Capacity rate must be finite and nonnegative")
    if not rows.status.isin(["available", "partial"]).all():
        raise ValueError("Unusable capacity estimates")
    if not rows.label_kind.eq("model_estimated_capacity").all():
        raise ValueError("Expected model_estimated_capacity proxy label")
    if not rows.population.str.contains("reporting carrier", case=False, na=False).all():
        raise ValueError("Expected reporting-carrier population")
    for column in ("run_id", "model_version", "source_id"):
        if not rows[column].map(lambda v: isinstance(v, str) and bool(v.strip())).all():
            raise ValueError(f"Missing {column}")
    if rows.run_id.nunique() != 1 or rows.model_version.nunique() != 1:
        raise ValueError("Mixed model publications")
    return rows.assign(aar_pred=rate)


def _result():
    return {"status": "unavailable", "capacity": pd.DataFrame(), "missing_inputs": [],
            "limitations": list(LIMITATIONS), "operationally_eligible": False,
            "population": "reporting_carriers", "label_kind": "model_estimated_capacity"}


def build_capacity_inputs(forecast: pd.DataFrame, *, airport: str, asof_utc, window_hours: int) -> dict:
    """Return only exact-cutoff rates; missing hours remain missing, never zero."""
    result = _result()
    try:
        rows, cutoff = _scope(forecast, airport, asof_utc, window_hours)
        hours = pd.date_range(cutoff, periods=window_hours, freq="h")
        rows = _validate(rows.loc[rows.target_hour_utc.isin(hours)], cutoff)
        missing = hours.difference(pd.DatetimeIndex(rows.target_hour_utc))
        result["capacity"] = rows.sort_values("target_hour_utc").reset_index(drop=True)
        result["missing_inputs"] = [f"No capacity forecast for {h.isoformat()}" for h in missing]
        result["status"] = "partial" if len(missing) else "available"
        result["input_kind"] = "published_capacity_proxy"
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        result["missing_inputs"] = [str(exc)]
    return result


def build_constant_capacity_scenario(forecast: pd.DataFrame, *, airport: str, asof_utc,
                                     window_hours: int, anchor_lead: int) -> dict:
    """Explicit sensitivity assumption: one forecast rate held over every hour.

    ``anchor_target_hour_utc`` preserves the true forecast target. Repeated rows
    are assumed scenario rates, not new weather-conditioned predictions.
    """
    result = _result()
    try:
        rows, cutoff = _scope(forecast, airport, asof_utc, window_hours)
        if isinstance(anchor_lead, bool) or not isinstance(anchor_lead, Integral) or anchor_lead not in (3, 6, 12):
            raise ValueError("anchor_lead must be 3, 6 or 12")
        rows = _validate(rows.loc[rows.horizon_hours == anchor_lead], cutoff)
        if len(rows) != 1:
            raise ValueError("Exactly one capacity anchor is required")
        anchor = rows.iloc[0]
        scenario = pd.DataFrame([anchor.to_dict() for _ in range(window_hours)])
        scenario["anchor_target_hour_utc"] = anchor.target_hour_utc
        scenario["anchor_horizon_hours"] = anchor_lead
        scenario["target_hour_utc"] = pd.date_range(cutoff, periods=window_hours, freq="h")
        scenario["horizon_hours"] = range(window_hours)
        scenario["status"] = "scenario_assumption"
        scenario["input_kind"] = "constant_capacity_proxy_assumption"
        scenario["direction"] = "arrival"
        result.update(status="partial", capacity=scenario, input_kind="constant_capacity_proxy_assumption",
                      anchor_target_hour_utc=anchor.target_hour_utc.isoformat(), anchor_lead=int(anchor_lead),
                      constant_rate=float(anchor.aar_pred))
        result["limitations"].append(
            f"The +{anchor_lead}h forecast rate is assumed constant across all {window_hours} hours; "
            "these are scenario rates, not forecasts at unscored horizons. No rate interpolation is performed."
        )
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        result["missing_inputs"] = [str(exc)]
    return result
