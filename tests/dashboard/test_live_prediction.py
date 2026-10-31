import json
import pandas as pd
import pytest
from src.dashboard.live_prediction import ARTIFACT, infer


def test_live_probabilities_and_stale_guard():
    document=json.loads(ARTIFACT.read_text())
    now=pd.Timestamp('2026-10-31T10:00Z')
    station={'status':'available','reports':[{'obsTime':int(now.timestamp()),'visib':'10+', 'wspd':8,'clouds':[], 'rawOb':'METAR KATL CAVOK','wxString':''}]}
    rows=infer(document,station,'KATL',now)
    assert len(rows)==12
    assert rows.Probability.between(0,1).all()
    with pytest.raises(ValueError,match='90 minutes'):
        infer(document,station,'KATL',now+pd.Timedelta(hours=2))
    with pytest.raises(ValueError,match='only'):
        infer(document,station,'KJFK',now)
    station['status']='cached'
    with pytest.raises(ValueError,match='Refresh'):
        infer(document,station,'KATL',now)
