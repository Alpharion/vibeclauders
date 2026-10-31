import numpy as np
import pandas as pd
import pytest
from src.dashboard.live_flights import fetch_departures, prepare, score

NOW=pd.Timestamp('2026-10-31T10:00:00Z')

def feed():
    return dict(airport='KATL',retrieved_at_utc=NOW.isoformat(),partial=False,flights=[dict(
        fa_flight_id='one',ident_iata='DL123',origin={'code_iata':'ATL'},destination={'code_iata':'DFW'},
        scheduled_out='2026-10-31T13:00:00Z',scheduled_in='2026-10-31T15:00:00Z',estimated_out='2026-10-31T14:00:00Z')])

class Model:
    threshold=.2
    def predict(self, rows):
        assert rows.local_hour.iloc[0]==9
        assert rows.scheduled_duration_min.iloc[0]==120
        assert rows.distance_miles.isna().all()
        return np.full(len(rows),.1)

def test_provider_delay_is_separate_review_trigger():
    rows=score(prepare(feed(),'KATL',NOW),{'schedule_model':Model()})
    assert rows.Review.iloc[0]
    assert rows.probability_severe_delay.iloc[0]==.1
    assert rows.provider_delay_min.iloc[0]==60

def test_stale_and_wrong_airport_refused():
    with pytest.raises(ValueError): prepare(feed(),'KATL',NOW+pd.Timedelta(minutes=16))
    with pytest.raises(ValueError): prepare(feed(),'KDFW',NOW)

def test_missing_features_not_scored_and_duplicates_removed():
    data=feed();data['flights'][0]['scheduled_in']=None
    data['flights']*=2
    rows=score(prepare(data,'KATL',NOW),{'schedule_model':Model()})
    assert len(rows)==1
    assert rows.probability_severe_delay.isna().all()
    assert rows.unscored_reason.iloc[0]

def test_cancelled_departed_and_naive_times_excluded():
    for field,value in [('cancelled',True),('actual_out','2026-10-31T10:00:00Z'),('scheduled_out','2026-10-31T13:00:00')]:
        data=feed();data['flights'][0][field]=value
        assert prepare(data,'KATL',NOW).empty

def test_bounded_request_and_partial_coverage():
    def get(url,headers,params,timeout):
        assert url.endswith('/KATL/flights/scheduled_departures')
        assert headers['x-apikey']=='test-only'
        assert params['max_pages']==3
        class Response:
            def raise_for_status(self): pass
            def json(self): return {'scheduled_departures':[], 'links':{'next':'next-page'}}
        return Response()
    assert fetch_departures('KATL',NOW,'test-only',get)['partial']
