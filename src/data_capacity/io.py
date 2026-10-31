"""Atomic publication, hashing, null-safe JSON and cached HTTP downloads."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from .config import utcnow


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (pd.Timestamp, datetime)):
        if obj.tzinfo is None:
            raise ValueError(f"naive timestamp in JSON output: {obj!r}")
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Path):
        return obj.as_posix()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, np.bool_):
        return bool(obj)
    if obj is pd.NaT or obj is pd.NA:
        return None
    return obj


def _atomic_write(path: Path, writer: Callable[[Path], None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        writer(tmp_path)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def write_json(path: Path, payload: dict) -> None:
    text = json.dumps(_jsonable(payload), indent=2, allow_nan=False, ensure_ascii=False)
    # LF on every OS so published hashes are platform-independent
    _atomic_write(path, lambda p: p.write_text(text + "\n", encoding="utf-8", newline="\n"))


def write_parquet(path: Path, df: pd.DataFrame) -> None:
    _atomic_write(path, lambda p: df.to_parquet(p, index=False))


def write_bytes(path: Path, data: bytes) -> None:
    _atomic_write(path, lambda p: p.write_bytes(data))


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


class DownloadError(RuntimeError):
    pass


def fetch_cached(
    url: str,
    dest: Path,
    *,
    validate: Callable[[bytes], None],
    cache_only: bool = False,
    refresh: bool = False,
    timeout: tuple[float, float] = (15, 180),
    retries: int = 3,
    backoff_s: float = 3.0,
    session=None,
) -> dict:
    """Download ``url`` to ``dest`` unless a validated cache exists.

    A sidecar ``<dest>.meta.json`` records URL, retrieval time, hash and status.
    A failed or invalid download never replaces a good cached file. Returns
    the metadata record (``status`` is ``cached``, ``downloaded`` or ``failed``).
    """
    meta_path = dest.with_name(dest.name + ".meta.json")
    meta = read_json(meta_path)
    if dest.exists() and not refresh and meta and meta.get("status") in ("downloaded", "cached"):
        if meta.get("sha256") == sha256_file(dest):
            return {**meta, "status": "cached"}
    if cache_only:
        rec = {"url": url, "path": dest, "status": "failed", "error": "cache-only mode and no valid cached file"}
        return rec

    import requests

    sess = session or requests.Session()
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = sess.get(url, timeout=timeout, headers={"User-Agent": "autonomous-sg-2026-member1/1.0"})
            resp.raise_for_status()
            body = resp.content
            validate(body)
            write_bytes(dest, body)
            rec = {
                "url": url,
                "path": dest,
                "retrieved_at_utc": utcnow(),
                "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body),
                "status": "downloaded",
                "attempts": attempt,
            }
            write_json(meta_path, rec)
            return rec
        except Exception as exc:  # network, HTTP or validation failure
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(backoff_s * attempt)
    rec = {"url": url, "path": dest, "status": "failed", "error": last_err, "attempted_at_utc": utcnow()}
    # keep any previous good cache untouched; record the failure separately
    write_json(dest.with_name(dest.name + ".failed.json"), rec)
    return rec


def validate_csv_header(required: list[str], min_rows: int = 1) -> Callable[[bytes], None]:
    def _v(body: bytes) -> None:
        text = body.decode("utf-8", errors="replace")
        lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        if not lines:
            raise DownloadError("empty response")
        header = lines[0].split(",")
        missing = [c for c in required if c not in header]
        if missing:
            raise DownloadError(f"unexpected header, missing {missing}: {lines[0][:200]!r}")
        if len(lines) - 1 < min_rows:
            raise DownloadError(f"only {len(lines) - 1} data rows")

    return _v
