from pathlib import Path
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from src.dashboard.data import Bundle, Group
from src.dashboard import views
from tests.dashboard import conftest as c

ROOT = Path(__file__).resolve().parents[2]

def bundle():
    rows = c.predictions().assign(
        model_train_end_utc=c.ASOF-pd.Timedelta(days=365),
        selection_end_utc=c.ASOF-pd.Timedelta(days=30),
        weather_available_at_utc=c.ASOF-pd.Timedelta(hours=1),
    )
    return Bundle('', '', {'predictions': rows}, {}, {'risk': Group(c.envelope())}, [])

def snap(airport='KATL', lead=6, asof=c.ASOF):
    return views.Snapshot(views.resolve_airport(airport), asof, lead)

def test_exact_key_priorities_no_outcomes_and_rank():
    b=bundle()
    b.tables['predictions']['dep_delay_min']=9999
    b.tables['predictions']['cancelled']=True
    brief, error=views.review_priorities(b,snap())
    assert error is None
    assert [x['flight_id'] for x in brief['review_priorities']]==['f1']
    assert brief['sampled_flights_scored']==2
    assert brief['horizon_hours']==6
    assert 'dep_delay_min' not in str(brief) and 'cancelled' not in str(brief)
    assert 'separate review briefing' not in str(brief)

@pytest.mark.parametrize('selection',[snap('KDFW'),snap(lead=12),snap(asof=c.ASOF+pd.Timedelta(hours=4))])
def test_absent_exact_key_never_falls_back(selection):
    brief,error=views.review_priorities(bundle(),selection)
    assert error is None and brief['status']=='unavailable'
    assert brief['review_priorities']==[]

def test_no_flags_is_not_airport_all_clear():
    b=bundle()
    b.tables['predictions']['threshold']=1.
    brief,error=views.review_priorities(b,snap())
    assert error is None and brief['status']=='available'
    assert brief['flagged_flights']==0 and 'not an airport all-clear' in brief['summary']

@pytest.mark.parametrize('mutation',['future_selection','future_weather','wrong_run','duplicate','missing_schema'])
def test_untrusted_prediction_evidence_is_withheld(mutation):
    b=bundle()
    rows=b.tables['predictions']
    if mutation=='future_selection': rows['selection_end_utc']=c.ASOF+pd.Timedelta(hours=1)
    elif mutation=='future_weather':
        rows['model_kind']='weather_enhanced'
        rows['weather_available_at_utc']=c.ASOF+pd.Timedelta(hours=1)
    elif mutation=='wrong_run': rows['run_id']='wrong'
    elif mutation=='duplicate': b.tables['predictions']=pd.concat([rows,rows.iloc[:1]])
    else: b.tables['predictions']=rows.drop(columns='selection_end_utc')
    brief,error=views.review_priorities(b,snap())
    assert brief is None and 'rejected' in error

def test_missing_publication_is_unavailable():
    b=bundle()
    b.tables.clear()
    assert views.review_priorities(b,snap())[0] is None


def test_real_artifacts_review_panel_shows_actions_without_outcomes():
    app=AppTest.from_string('''
from pathlib import Path
import pandas as pd
from src.dashboard.data import load_bundle
from src.dashboard.views import Snapshot, resolve_airport
from src.dashboard.app import review_actions_section
bundle=load_bundle(Path(r"ROOT_PATH"))
review_actions_section(bundle, Snapshot(resolve_airport("KATL"),pd.Timestamp("2025-07-12T20:00:00Z"),3))
'''.replace('ROOT_PATH',str(ROOT)),default_timeout=30).run()
    assert not app.exception
    words=' '.join(str(x.value) for kind in ('markdown','caption') for x in getattr(app,kind))
    assert 'Review current weather and airline/inbound-aircraft status' in words
    assert 'Historical replay' in words and '0949771a54bb4e49b4e215528eb5d46b' in words
    table=app.dataframe[0].value
    assert len(table)==2
    assert table.flight_id.tolist()==['460f3042c18b22443112','a6e1ef65ebf371bd00f0']
    assert list(table.columns)==['flight_id','probability','threshold','model_kind']


def test_real_compare_shows_scenario_assumptions_and_retains_operational_gate():
    app=AppTest.from_string('''
from pathlib import Path
import pandas as pd
from src.dashboard.data import load_bundle
from src.dashboard.views import Snapshot, resolve_airport
from src.dashboard.app import compare_tab
bundle=load_bundle(Path(r"ROOT_PATH"))
compare_tab(bundle, Snapshot(resolve_airport("KATL"),pd.Timestamp("2025-07-12T20:00:00Z"),3),6,False)
'''.replace('ROOT_PATH',str(ROOT)),default_timeout=30).run()
    assert not app.exception
    words=' '.join(str(x.value) for kind in ('markdown','caption','error','info') for x in getattr(app,kind))
    assert 'Illustrative arrival scenario' in words
    assert 'constant model-estimated capacity' in words
    assert 'No decision output for this selection' in words
    assert 'Reveal outcomes' in words
    assert not any('dep_delay_min' in frame.value.columns for frame in app.dataframe)
