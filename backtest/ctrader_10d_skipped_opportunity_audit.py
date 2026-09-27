#!/usr/bin/env python3
"""Create a clearly-labelled audit of selected but non-executed opportunities."""
from __future__ import annotations
import csv, json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'backtest/ctrader_allocator_10d_comparison'
DATA=ROOT/'backtest/ctrader_volume_data'
selected=json.loads((OUT/'signal_cache.json').read_text())['selected_by_pair']
all_selected=[s for values in selected.values() for s in values]
trades={}
for portfolio in ('equal_weight','adaptive'):
    rows=list(csv.DictReader((OUT/f'trades_{portfolio}.csv').open()))
    trades[portfolio]=rows
weights=list(csv.DictReader((OUT/'allocation_weights.csv').open()))
weight_times=[(pd.Timestamp(r['time']),r) for r in weights]

def reason(signal, portfolio):
    t=pd.Timestamp(signal['signal_close_utc'])
    rows=trades[portfolio]
    same=[]; active=[]
    for r in rows:
        entry=pd.Timestamp(r['entry_time_utc']); exit=pd.Timestamp(r['exit_time_utc'])
        if entry <= t < exit:
            active.append(r)
            if r['pair']==signal['pair']: same.append(r)
    if same: return 'SKIPPED_POSITION_OPEN'
    if len(active)>=3: return 'SKIPPED_MAX_OPEN_POSITIONS'
    if portfolio=='adaptive':
        prior=[r for ts,r in weight_times if ts<=t]
        if prior and float(prior[-1].get('weight_'+signal['pair'],0))<=1e-12:
            return 'SKIPPED_ZERO_ALLOCATOR_WEIGHT'
    return 'NOT_IN_EXECUTION_LOG'

def counterfactual(signal):
    pair=signal['pair']; rows=json.loads((DATA/f'{pair}_m5_10d.json').read_text())['candles']
    df=pd.DataFrame(rows); df['time']=pd.to_datetime(df['time'],utc=True); df=df.sort_values('time').set_index('time')
    t=pd.Timestamp(signal['signal_close_utc']); idx=df.index.searchsorted(t,side='left')
    if idx>=len(df): return '', '', None, 'NO_FUTURE_BAR'
    fill=float(df.iloc[idx].open); side=1 if signal['side']=='LONG' else -1; stop=float(signal['stop']); target=float(signal['target']); risk=abs(fill-stop)
    if (side==1 and not stop<fill<target) or (side==-1 and not target<fill<stop): return '', '', None, 'INVALID_FILL'
    exitp=float(df.iloc[-1].close); why='end_of_sample_mark'
    for j in range(idx,len(df)):
        b=df.iloc[j]; op,hi,lo=float(b.open),float(b.high),float(b.low)
        if side==1:
            checks=((op<=stop,op,'stop_gap'),(op>=target,target,'target_gap'),(lo<=stop,stop,'stop'),(hi>=target,target,'target'))
        else:
            checks=((op>=stop,op,'stop_gap'),(op<=target,target,'target_gap'),(hi>=stop,stop,'stop'),(lo<=target,target,'target'))
        hit=next((x for x in checks if x[0]),None)
        if hit: _,exitp,why=hit; break
    net=(side*(exitp-fill)-1.5*0.0001)/risk
    return why, 'WIN' if net>0 else 'LOSS', net, 'VALID_COUNTERFACTUAL'

executed={p:{r['signal_id'] for r in trades[p]} for p in trades}
rows=[]
for s in all_selected:
    if s['signal_id'] in executed['equal_weight'] and s['signal_id'] in executed['adaptive']:
        continue
    why,outcome,net,status=counterfactual(s)
    rows.append({'record_type':'HYPOTHETICAL_NOT_EXECUTED','pair':s['pair'],'variant':s['variant'],'signal_id':s['signal_id'],'signal_close_utc':s['signal_close_utc'],'side':s['side'],'reason_equal_weight':reason(s,'equal_weight'),'reason_adaptive':reason(s,'adaptive'),'counterfactual_status':status,'counterfactual_exit_reason':why,'counterfactual_outcome':outcome,'counterfactual_net_R':net})
with (OUT/'skipped_opportunity_audit.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(json.dumps({'rows':len(rows),'wins':sum(r['counterfactual_outcome']=='WIN' for r in rows),'losses':sum(r['counterfactual_outcome']=='LOSS' for r in rows)},indent=2))
