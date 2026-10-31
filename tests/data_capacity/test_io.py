"""Download cache behaviour without network access (fake sessions)."""
import json

import pandas as pd
import pytest

from src.data_capacity.io import fetch_cached, validate_csv_header, write_parquet

GOOD = b"station,valid,metar\nATL,2024-01-01 00:52,KATL ...\nATL,2024-01-01 01:52,KATL ...\n"


class Resp:
    def __init__(self, body, status=200):
        self.content, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Session:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), 0

    def get(self, url, timeout=None, headers=None):
        self.calls += 1
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


V = validate_csv_header(["station", "valid", "metar"], 2)


def test_download_then_cache_reuse(tmp_path):
    dest = tmp_path / "a.csv"
    s = Session(Resp(GOOD))
    assert fetch_cached("u", dest, validate=V, session=s)["status"] == "downloaded"
    s2 = Session()  # any network call would raise IndexError
    assert fetch_cached("u", dest, validate=V, session=s2)["status"] == "cached" and s2.calls == 0


def test_timeout_and_malformed_never_replace_good_cache(tmp_path):
    dest = tmp_path / "a.csv"
    fetch_cached("u", dest, validate=V, session=Session(Resp(GOOD)))
    bad = Session(TimeoutError("read timed out"), Resp(b"<html>error</html>"), Resp(b"", 503))
    rec = fetch_cached("u", dest, validate=V, session=bad, refresh=True, backoff_s=0)
    assert rec["status"] == "failed" and bad.calls == 3
    assert dest.read_bytes() == GOOD
    assert json.loads((tmp_path / "a.csv.failed.json").read_text())["status"] == "failed"


def test_partial_download_rejected(tmp_path):
    rec = fetch_cached("u", tmp_path / "p.csv", validate=V, session=Session(Resp(b"station,valid,metar\n")), retries=1)
    assert rec["status"] == "failed" and not (tmp_path / "p.csv").exists()


def test_tampered_cache_is_not_trusted_in_cache_only_mode(tmp_path):
    dest = tmp_path / "a.csv"
    fetch_cached("u", dest, validate=V, session=Session(Resp(GOOD)))
    dest.write_bytes(GOOD + b"tampered\n")
    assert fetch_cached("u", dest, validate=V, cache_only=True)["status"] == "failed"


def test_atomic_parquet_write_leaves_no_temp_files(tmp_path):
    write_parquet(tmp_path / "x.parquet", pd.DataFrame({"a": [1]}))
    assert [p.name for p in tmp_path.iterdir()] == ["x.parquet"]


def test_failed_writer_keeps_previous_file(tmp_path):
    p = tmp_path / "x.parquet"
    write_parquet(p, pd.DataFrame({"a": [1]}))

    class Boom(pd.DataFrame):
        def to_parquet(self, *a, **k):
            raise OSError("disk full")

    with pytest.raises(OSError):
        write_parquet(p, Boom({"a": [2]}))
    assert pd.read_parquet(p)["a"].tolist() == [1]
    assert [q.name for q in tmp_path.iterdir()] == ["x.parquet"]
