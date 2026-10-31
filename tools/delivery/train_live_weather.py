"""Fit a small reproducible weather transition model from historical METARs."""
import json
from hashlib import sha256
from pathlib import Path
import numpy as np
import pandas as pd
from src.dashboard.live_prediction import state, EVENTS


def main():
    source=Path('artifacts/capacity/weather.parquet')
    all_rows=pd.read_parquet(source)
    obs=all_rows[all_rows.kind.eq('observation')].copy()
    document={'version':1,'airports':['KATL','KDFW'],'source_sha256':sha256(source.read_bytes()).hexdigest(),
              'models':{},'evaluation':[], 'label':'First METAR at/after target within 60 minutes'}
    for airport in document['airports']:
        d=obs[obs.airport.eq(airport)].sort_values('available_at_utc').drop_duplicates('valid_from_utc',keep='last')
        d=d.dropna(subset=['visibility_sm','ceiling_ft_agl','wind_gust_kt','thunderstorm_flag'])
        d['state']=[state(r.visibility_sm,r.ceiling_ft_agl,r.wind_gust_kt,r.thunderstorm_flag,r.available_at_utc.month) for r in d.itertuples()]
        for lead in (3,6,12):
            x=d[['available_at_utc','state']].copy(); x['target']=x.available_at_utc+pd.Timedelta(hours=lead)
            labels=d[['valid_from_utc','available_at_utc','visibility_sm','ceiling_ft_agl','wind_gust_kt','thunderstorm_flag']].rename(columns={'available_at_utc':'label_available'})
            joined=pd.merge_asof(x.sort_values('target'),labels.sort_values('valid_from_utc'),left_on='target',right_on='valid_from_utc',direction='forward',tolerance=pd.Timedelta(hours=1)).dropna()
            y=np.column_stack([joined.thunderstorm_flag.eq(1), joined.visibility_sm.lt(3),joined.ceiling_ft_agl.lt(1000),joined.wind_gust_kt.ge(25)]).astype(float)
            train=(joined.available_at_utc.dt.year.eq(2023)&joined.label_available.lt(pd.Timestamp('2024-01-01',tz='UTC'))).to_numpy()
            val=(joined.available_at_utc.dt.year.eq(2024)&joined.label_available.lt(pd.Timestamp('2025-01-01',tz='UTC'))).to_numpy()
            test=joined.available_at_utc.dt.year.eq(2025).to_numpy()
            if not all(mask.any() for mask in (train,val,test)): raise ValueError('Missing chronological cohort')
            baseline=y[train].mean(axis=0); cells={}
            for key in joined.loc[train,'state'].unique():
                mask=train & joined.state.eq(key).to_numpy(); n=int(mask.sum())
                cells[key]={'n':n,'probabilities':((y[mask].sum(axis=0)+30*baseline)/(n+30)).tolist()}
            prediction=np.array([cells.get(k,{'probabilities':baseline})['probabilities'] for k in joined.state])
            selected=[]
            for i,event in enumerate(EVENTS):
                use=np.mean((prediction[val,i]-y[val,i])**2)<np.mean((baseline[i]-y[val,i])**2)
                selected.append('transition' if use else 'climatology')
                score=prediction[test,i] if use else np.full(test.sum(),baseline[i])
                document['evaluation'].append({'Airport':airport,'Lead':lead,'Condition':event,'Method':selected[-1], 'Test rows':int(test.sum()),'Brier':float(np.mean((score-y[test,i])**2)),'Baseline Brier':float(np.mean((baseline[i]-y[test,i])**2))})
            document['models'][f'{airport}/{lead}']={'cells':cells,'baseline':baseline.tolist(),'selected':selected,'train_rows':int(train.sum()),'validation_rows':int(val.sum())}
    dest=Path('artifacts/live_weather/model.json'); dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Published',dest, 'with',len(document['evaluation']),'evaluated condition/horizon cells')

if __name__=='__main__': main()
