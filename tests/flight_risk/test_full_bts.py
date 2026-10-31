import json
from pathlib import Path
import pandas as pd
import pytest

from src.flight_risk.full_bts import build, canonical_month, verify_month
from src.data_capacity.flights import USECOLS
from src.data_capacity.io import sha256_file


def raw(**values):
    row = dict.fromkeys(USECOLS)
    row.update(FL_DATE="2024-06-01", OP_UNIQUE_CARRIER="DL", OP_CARRIER_FL_NUM=100., TAIL_NUM="N1",
               ORIGIN="ATL", DEST="DFW", CRS_DEP_TIME=900, CRS_ARR_TIME=1015, CRS_ELAPSED_TIME=135.,
               DISTANCE=731., DEP_DELAY=60., ARR_DELAY=45., CANCELLED=0., DIVERTED=0.)
    row.update(values)
    return pd.DataFrame([row])


def cache(tmp_path, frame=None):
    directory=tmp_path / "filtered"; directory.mkdir()
    p=directory / "ontime_ATL_DFW_2024_06.parquet"
    (raw() if frame is None else frame).to_parquet(p,index=False)
    p.with_name(p.name+".meta.json").write_text(json.dumps({"sha256":sha256_file(p),
        "zip_sha256":"a"*64,"airports":["ATL","DFW"],"rows":len(raw() if frame is None else frame)}))
    return directory,p


def test_missing_month_fails_before_any_output(tmp_path):
    directory,_=cache(tmp_path)
    with pytest.raises(ValueError,match="Missing"):
        build(directory,tmp_path/"result",months=["2024-06","2024-07"])
    assert not (tmp_path/"result").exists()


def test_hash_tamper_refused(tmp_path):
    directory,p=cache(tmp_path)
    p.write_bytes(p.read_bytes()+b"tamper")
    with pytest.raises(ValueError,match="hash mismatch"):
        verify_month(directory,"2024-06")


def test_month_boundary_and_duplicate_identity():
    with pytest.raises(ValueError,match="another month"):
        canonical_month(raw(FL_DATE="2024-07-01"),"2024-06")
    frame,audit=canonical_month(pd.concat([raw(),raw(DEP_DELAY=90.)],ignore_index=True),"2024-06")
    assert frame.empty and audit["excluded_conflicting_duplicate_keys"]==2


def test_carrier_is_part_of_key_and_outcomes_do_not_change_identity():
    a,_=canonical_month(raw(),"2024-06")
    b,_=canonical_month(raw(DEP_DELAY=150.),"2024-06")
    c,_=canonical_month(raw(OP_UNIQUE_CARRIER="AA"),"2024-06")
    assert a.flight_id.iloc[0]==b.flight_id.iloc[0]!=c.flight_id.iloc[0]
    assert a.coverage.eq("reporting_carriers").all()
    assert a.source_id.eq("bts_ontime_prezip").all()


def test_streamed_canonical_schema_and_sample_audit(tmp_path):
    directory,_=cache(tmp_path)
    sample=Path(__file__).resolve().parents[2]/"data/processed/flights.parquet"
    result=build(directory,tmp_path/"result",sample,months=["2024-06"])
    out=pd.read_parquet(result["output"])
    assert list(out.columns)==list(pd.read_parquet(sample).columns)
    assert len(out)==1 and result["canonical_rows"]==1
    assert result["label_counts"][0]["split"]=="validate"
    assert result["label_counts"][0]["severe"]==1
    assert result["sha256"]==sha256_file(Path(result["output"]))
    assert not result["production_changed"]


def test_unique_months_required(tmp_path):
    with pytest.raises(ValueError,match="unique"):
        build(tmp_path,tmp_path/"output",months=["2024-06","2024-06"])


def test_outside_experiment_window_refused(tmp_path):
    with pytest.raises(ValueError,match="fixed"):
        build(tmp_path,tmp_path/"output",months=["2026-01"])
