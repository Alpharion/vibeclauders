"""Automatic IEM METAR/TAF acquisition and decoding into weather.parquet.

Sources (no manual browser steps):
* METAR/SPECI: https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py
* TAF groups:  https://mesonet.agron.iastate.edu/cgi-bin/request/taf.py

Timing semantics
* METAR ``issued_at_utc`` = observation time; ``available_at_utc`` = issued +
  METAR_LATENCY_MIN (assumption: IEM does not archive receipt time).
* TAF ``issued_at_utc`` = product issuance (from the product id);
  ``available_at_utc`` = issued + TAF_LATENCY_MIN (same assumption).
* TAF prevailing groups (initial + FM) are valid from their start until the next
  prevailing group of the same bulletin, the last one until the end of the TAF
  period (TAF_VALIDITY_H after its 6-hourly cycle). TEMPO/PROB groups take their
  half-open interval from the raw DDHH/DDHH text and
  never replace prevailing weather. A later amendment supersedes a bulletin only
  from the amendment's availability onward (selection happens in features.py).
"""
from __future__ import annotations

import ast
import re
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

from .config import (
    METAR_LATENCY_MIN, PUBLIC_DIR, TAF_LATENCY_MIN, TAF_VALIDITY_H, Airport,
)
from .io import fetch_cached, validate_csv_header

IEM_ASOS = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
IEM_TAF = "https://mesonet.agron.iastate.edu/cgi-bin/request/taf.py"
METAR_FIELDS = ["tmpf", "drct", "sknt", "gust", "vsby", "skyc1", "skyl1", "skyc2", "skyl2",
                "skyc3", "skyl3", "skyc4", "skyl4", "wxcodes", "metar"]
TAF_REQUIRED = ["station", "valid", "fx_valid", "raw", "is_tempo", "fx_valid_end", "sknt", "drct",
                "gust", "visibility", "presentwx", "skyc", "skyl", "product_id", "ftype", "is_amendment"]

# Precipitation at the station (VCSH = showers in vicinity, no precip type -> 0).
PRECIP_RE = re.compile(r"RA|SN|DZ|PL|GR|GS|IC|UP|SG")
# Thunderstorm includes vicinity thunderstorm (VCTS); documented semantics.
TS_RE = re.compile(r"TS")
VRB_RE = re.compile(r"\bVRB(\d{2,3})(?:G(\d{2,3}))?KT\b")
NO_CEILING_FT = 30000.0  # documented sentinel: no BKN/OVC/VV layer reported


def metar_url(station: str, year: int, start: pd.Timestamp, end: pd.Timestamp) -> str:
    q = [f"station={station}"] + [f"data={f}" for f in METAR_FIELDS] + [
        f"year1={start.year}", f"month1={start.month}", f"day1={start.day}",
        f"year2={end.year}", f"month2={end.month}", f"day2={end.day}",
        "tz=Etc/UTC", "format=onlycomma", "latlon=no", "missing=empty", "trace=T",
        "direct=no", "report_type=3", "report_type=4",
    ]
    return IEM_ASOS + "?" + "&".join(q)


def taf_url(station: str, start: pd.Timestamp, end: pd.Timestamp) -> str:
    return f"{IEM_TAF}?station={station}&sts={start:%Y-%m-%dT%H:%MZ}&ets={end:%Y-%m-%dT%H:%MZ}&fmt=csv"


def _year_windows(start: pd.Timestamp, end: pd.Timestamp):
    """Yield (year, window_start, window_end_exclusive) chunks."""
    cur = start
    while cur < end:
        nxt = min(pd.Timestamp(year=cur.year + 1, month=1, day=1), end)
        yield cur.year, cur, nxt
        cur = nxt


def acquire(airports: list[Airport], start: pd.Timestamp, end: pd.Timestamp, *, cache_only=False, refresh=False) -> list[dict]:
    """Download (or reuse) yearly METAR and TAF chunks. Returns one record per chunk."""
    records = []
    for ap in airports:
        for year, ws, we in _year_windows(start, end):
            days = max(1.0, (we - ws).total_seconds() / 86400)
            tag = f"{ws:%Y%m%d}_{we:%Y%m%d}"
            dest = PUBLIC_DIR / "iem_metar" / f"{ap.metar_station}_{tag}.csv"
            rec = fetch_cached(metar_url(ap.metar_station, year, ws, we), dest,
                               validate=validate_csv_header(["station", "valid", "metar"], int(days * 8)),
                               cache_only=cache_only, refresh=refresh)
            records.append({**rec, "source_id": "iem_metar", "airport": ap.icao, "window": [ws, we]})
            dest = PUBLIC_DIR / "iem_taf" / f"{ap.taf_station}_{tag}.csv"
            rec = fetch_cached(taf_url(ap.taf_station, ws, we), dest,
                               validate=validate_csv_header(TAF_REQUIRED, int(days * 4)),
                               cache_only=cache_only, refresh=refresh)
            records.append({**rec, "source_id": "iem_taf", "airport": ap.icao, "window": [ws, we]})
    return records


# ---------------------------------------------------------------- decoding

def _wx_flags(codes: pd.Series) -> tuple[pd.Series, pd.Series]:
    s = codes.fillna("").astype(str)
    precip = s.str.contains(PRECIP_RE).astype("Int8")
    ts = s.str.contains(TS_RE).astype("Int8")
    return precip, ts


def _ceiling(covers: list, levels: list) -> float:
    lows = [float(l) for c, l in zip(covers, levels) if c in ("BKN", "OVC", "VV") and l is not None and not pd.isna(l)]
    return min(lows) if lows else NO_CEILING_FT


def _parse_list(v):
    if v is None or (isinstance(v, float) and np.isnan(v)) or v == "":
        return []
    try:
        out = ast.literal_eval(v) if isinstance(v, str) else v
        return list(out) if isinstance(out, (list, tuple)) else [out]
    except Exception:
        return []


def decode_metar(text: str, ap: Airport, source_ref: str) -> pd.DataFrame:
    df = pd.read_csv(StringIO(text), comment="#")
    if df.empty:
        return pd.DataFrame()
    obs = pd.to_datetime(df["valid"], utc=True)
    speed = pd.to_numeric(df["sknt"], errors="coerce")
    direction = pd.to_numeric(df["drct"], errors="coerce")
    gust = pd.to_numeric(df["gust"], errors="coerce")
    raw = df["metar"].fillna("").astype(str)
    vrb = raw.str.extract(VRB_RE)
    is_vrb = vrb[0].notna()
    speed = speed.where(~(is_vrb & speed.isna()), pd.to_numeric(vrb[0], errors="coerce"))
    direction = direction.where(~is_vrb, np.nan)  # variable direction is unknown, not 0
    gust = gust.where(gust.notna(), speed)  # no gust group: peak = sustained (documented)
    covers = df[["skyc1", "skyc2", "skyc3", "skyc4"]].values.tolist()
    levels = df[["skyl1", "skyl2", "skyl3", "skyl4"]].values.tolist()
    precip, ts = _wx_flags(df["wxcodes"])
    tmpf = pd.to_numeric(df["tmpf"], errors="coerce")
    out = pd.DataFrame({
        "airport": ap.icao,
        "issued_at_utc": obs,
        "available_at_utc": obs + pd.Timedelta(minutes=METAR_LATENCY_MIN),
        "valid_from_utc": obs,
        "valid_to_utc": pd.NaT,
        "kind": "observation",
        "condition": np.where(raw.str.startswith("SPECI"), "speci", "routine"),
        "probability": np.nan,
        "bulletin_id": ap.icao + "-" + obs.dt.strftime("%Y%m%dT%H%MZ"),
        "source_id": "iem_metar",
        "source": "IEM ASOS/METAR archive",
        "wind_direction_deg": direction,
        "wind_speed_kt": speed,
        "wind_gust_kt": gust,
        "wind_variable": is_vrb,
        "visibility_sm": pd.to_numeric(df["vsby"], errors="coerce"),
        "ceiling_ft_agl": [_ceiling(c, l) for c, l in zip(covers, levels)],
        "temperature_c": (tmpf - 32) * 5 / 9,
        "weather_codes": df["wxcodes"].astype("string"),
        "precip_flag": precip,
        "thunderstorm_flag": ts,
        "is_amendment": False,
        "raw_text": raw,
        "raw_ref": source_ref,
    })
    out = out.sort_values("issued_at_utc").drop_duplicates(["airport", "issued_at_utc", "raw_text"])
    out["valid_to_utc"] = metar_valid_to(out["issued_at_utc"])
    return out


def metar_valid_to(observed: pd.Series) -> pd.Series:
    """Each observation is valid until the next STRICTLY later observation
    (two reports in the same minute must not create a zero-length interval)."""
    uniq = observed.dropna().drop_duplicates().sort_values()
    nxt = dict(zip(uniq, uniq.shift(-1)))
    return pd.to_datetime(observed.map(nxt), utc=True)


GROUP_PERIOD_RE = re.compile(r"\b(\d{2})(\d{2})/(\d{2})(\d{2})\b")


def group_end_from_raw(raw: str, start: pd.Timestamp) -> pd.Timestamp:
    """End of a TEMPO/PROB group from its DDHH/DDHH period, anchored on the
    group start. IEM's fx_valid_end is wrong across month ends (3119/3124 in
    May came back as May 18), so the raw text is authoritative."""
    m = GROUP_PERIOD_RE.search(raw or "")
    if m is None or pd.isna(start):
        return pd.NaT
    day, hour = int(m.group(3)), int(m.group(4))
    month_start = start.normalize().replace(day=1)
    for months_ahead in (0, 1):
        anchor = month_start + pd.DateOffset(months=months_ahead)
        try:
            end = anchor.replace(day=day) + pd.Timedelta(hours=hour)
        except ValueError:  # day does not exist in that month
            continue
        if end > start:
            return end
    return pd.NaT


def taf_validity_end(issued: pd.Series) -> pd.Series:
    """End of the TAF period: TAF_VALIDITY_H after the 6-hourly cycle the
    bulletin belongs to. Routine TAFs are issued up to ~40 min before their
    cycle hour and amendments keep the parent's end, so the cycle is the latest
    00/06/12/18Z hour <= issued + 1 h."""
    shifted = issued + pd.Timedelta(hours=1)
    cycle = shifted.dt.floor("6h")
    return cycle + pd.Timedelta(hours=TAF_VALIDITY_H)


def _condition(ftype: str) -> tuple[str, float]:
    f = (ftype or "").strip()
    if f == "Observation":
        return "initial", np.nan
    if f == "Forecast":
        return "FM", np.nan
    if f == "Temporary":
        return "TEMPO", np.nan
    if f.startswith("Probability"):
        m = re.search(r"(\d+)", f)
        return "PROB", float(m.group(1)) / 100 if m else np.nan
    if f.startswith("Becoming"):
        return "BECMG", np.nan
    return f or "unknown", np.nan


def decode_taf(text: str, ap: Airport, source_ref: str) -> pd.DataFrame:
    df = pd.read_csv(StringIO(text))
    if df.empty:
        return pd.DataFrame()
    issued = pd.to_datetime(df["valid"], utc=True)
    start = pd.to_datetime(df["fx_valid"], utc=True)
    end = pd.to_datetime(df["fx_valid_end"], utc=True, errors="coerce")
    cond = [_condition(f) for f in df["ftype"].fillna("")]
    condition = pd.Series([c for c, _ in cond], index=df.index)
    prob = pd.Series([p for _, p in cond], index=df.index, dtype="float64")
    raw = df["raw"].fillna("").astype(str)
    speed = pd.to_numeric(df["sknt"], errors="coerce")
    direction = pd.to_numeric(df["drct"], errors="coerce")
    gust = pd.to_numeric(df["gust"], errors="coerce")
    vrb = raw.str.extract(VRB_RE)
    is_vrb = vrb[0].notna()
    speed = speed.where(~(is_vrb & speed.isna()), pd.to_numeric(vrb[0], errors="coerce"))
    gust = gust.where(~(is_vrb & gust.isna()), pd.to_numeric(vrb[1], errors="coerce"))
    direction = direction.where(~is_vrb, np.nan)
    has_wind = speed.notna()
    # IEM writes gust 0 when no gust group; peak = sustained in that case
    gust = gust.where(~(has_wind & ((gust == 0) | gust.isna())), speed)
    wx = df["presentwx"].map(_parse_list)
    wx_str = wx.map(lambda l: " ".join(l)).astype("string")
    precip, ts = _wx_flags(wx_str)
    covers = df["skyc"].map(_parse_list)
    levels = df["skyl"].map(_parse_list)
    has_sky = covers.map(len) > 0
    ceiling = pd.Series([_ceiling(c, l) for c, l in zip(covers, levels)], index=df.index).where(has_sky)
    out = pd.DataFrame({
        "airport": ap.icao,
        "issued_at_utc": issued,
        "available_at_utc": issued + pd.Timedelta(minutes=TAF_LATENCY_MIN),
        "valid_from_utc": start,
        "valid_to_utc": end,
        "kind": "forecast",
        "condition": condition,
        "probability": prob,
        "bulletin_id": df["product_id"].astype("string"),
        "source_id": "iem_taf",
        "source": "IEM TAF archive",
        "wind_direction_deg": direction,
        "wind_speed_kt": speed,
        "wind_gust_kt": gust,
        "wind_variable": is_vrb,
        "visibility_sm": pd.to_numeric(df["visibility"], errors="coerce"),
        "ceiling_ft_agl": ceiling,
        "temperature_c": np.nan,  # TAFs here carry no temperature groups
        "weather_codes": wx_str,
        "precip_flag": precip.where(wx.map(len) > 0, 0).astype("Int8"),
        "thunderstorm_flag": ts.where(wx.map(len) > 0, 0).astype("Int8"),
        "is_amendment": df["is_amendment"].astype(str).str.lower() == "true",
        "raw_text": raw,
        "raw_ref": source_ref,
    })
    out = out.drop_duplicates(["bulletin_id", "condition", "valid_from_utc", "raw_text"])
    period_end = taf_validity_end(out["issued_at_utc"])
    # conditional groups: period from the raw DDHH/DDHH text
    cond_mask = out["condition"].isin(["TEMPO", "PROB"])
    out.loc[cond_mask, "valid_to_utc"] = [group_end_from_raw(r, s)
                                         for r, s in zip(out.loc[cond_mask, "raw_text"], out.loc[cond_mask, "valid_from_utc"])]
    # prevailing groups: valid until the next prevailing group of the same
    # bulletin; the last one until the end of the TAF period
    prev = out["condition"].isin(["initial", "FM", "BECMG"])
    p = out[prev].sort_values(["bulletin_id", "valid_from_utc"])
    nxt = p.groupby("bulletin_id")["valid_from_utc"].shift(-1)
    end = period_end[p.index]
    out.loc[p.index, "valid_to_utc"] = nxt.fillna(end).where(nxt.fillna(end) <= end, end)
    # groups that never cover any time (an initial group superseded by an FM
    # group at the same minute, or a group starting after the period end) are
    # dropped; the count is reported by build_weather
    empty = out["valid_to_utc"].notna() & (out["valid_to_utc"] <= out["valid_from_utc"])
    out = out[~empty]
    out.attrs["dropped_empty_groups"] = int(empty.sum())
    # a prevailing group that omits wind/vis/sky inherits nothing: values stay null
    return out.sort_values(["issued_at_utc", "valid_from_utc"]).reset_index(drop=True)


WEATHER_COLUMNS = [
    "airport", "issued_at_utc", "available_at_utc", "valid_from_utc", "valid_to_utc", "kind",
    "condition", "probability", "bulletin_id", "source_id", "source", "wind_direction_deg",
    "wind_speed_kt", "wind_gust_kt", "wind_variable", "visibility_sm", "ceiling_ft_agl",
    "temperature_c", "weather_codes", "precip_flag", "thunderstorm_flag", "is_amendment",
    "raw_text", "raw_ref",
]


def build_weather(records: list[dict], airports: list[Airport]) -> tuple[pd.DataFrame, dict]:
    by_icao = {a.icao: a for a in airports}
    frames, audit = [], {"chunks": [], "rows_by_airport_kind": {}}
    for rec in records:
        if rec["status"] == "failed":
            audit["chunks"].append({"path": rec["path"], "status": "failed", "error": rec.get("error")})
            continue
        path = Path(rec["path"])
        text = path.read_text(encoding="utf-8", errors="replace")
        ref = path.relative_to(path.parents[2]).as_posix() if len(path.parents) > 2 else path.name
        ap = by_icao[rec["airport"]]
        df = decode_metar(text, ap, ref) if rec["source_id"] == "iem_metar" else decode_taf(text, ap, ref)
        dropped = df.attrs.get("dropped_empty_groups", 0)
        audit["dropped_empty_taf_groups"] = audit.get("dropped_empty_taf_groups", 0) + dropped
        frames.append(df)
        audit["chunks"].append({"path": rec["path"], "status": rec["status"], "rows": int(len(df)),
                                "dropped_empty_groups": dropped})
    if not frames:
        return pd.DataFrame(columns=WEATHER_COLUMNS), audit
    w = pd.concat(frames, ignore_index=True)[WEATHER_COLUMNS]
    w = w.drop_duplicates(["airport", "kind", "bulletin_id", "condition", "valid_from_utc", "raw_text"])
    w = w.sort_values(["airport", "kind", "issued_at_utc", "valid_from_utc"]).reset_index(drop=True)
    # METAR validity across yearly chunk boundaries
    for a in w["airport"].unique():
        m = (w["airport"] == a) & (w["kind"] == "observation")
        w.loc[m, "valid_to_utc"] = metar_valid_to(w.loc[m, "issued_at_utc"])
    audit["inverted_validity_rows"] = int((w["valid_to_utc"].notna() & (w["valid_to_utc"] <= w["valid_from_utc"])).sum())
    for (a, k), g in w.groupby(["airport", "kind"]):
        audit["rows_by_airport_kind"][f"{a}/{k}"] = {
            "rows": int(len(g)),
            "bulletins": int(g["bulletin_id"].nunique()),
            "first_issued_utc": g["issued_at_utc"].min(),
            "last_issued_utc": g["issued_at_utc"].max(),
            "missing_wind_direction": int(g["wind_direction_deg"].isna().sum()),
            "variable_wind": int(g["wind_variable"].sum()),
        }
    return w, audit
