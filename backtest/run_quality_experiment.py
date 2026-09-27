#!/usr/bin/env python3
from __future__ import annotations
import csv,json
from pathlib import Path
import pandas as pd
from allocation.opportunity_quality import score_opportunity
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'backtest/ctrader_volume_data'; OUT=ROOT/'backtest/quality_14d_experiment'
PAIRS=('AUDUSD','EURUSD','GBPUSD','NZDUSD','USDCAD','USDCHF','USDJPY')

def load(pair):
 d=json.loads((DATA/f'{pair}_m5_14d.json').read_text()); f=pd.DataFrame(d['candles']); f['time']=pd.to_datetime(f['time'],utc=True); return f.sort_values('time').set_index('time')
def outcome(s, f):
 idx=f.index.searchsorted(pd.Timestamp(s['signal_close_utc']),side='left'); fill=float(f.iloc[idx].open); side=1 if s['side']=='LONG' else -1; stop=float(s['stop']); target=float(s['target']); risk=abs(fill-stop)
 for j in range(idx,len(f)):
  b=f.iloc[j]; op,hi,lo=map(float,(b.open,b.high,b.low))
  checks=((op<=stop,op,'stop_gap'),(op>=target,target,'target_gap'),(lo<=stop,stop,'stop'),(hi>=target,target,'target')) if side==1 else ((op>=stop,op,'stop_gap'),(op<=target,target,'target_gap'),(hi>=stop,stop,'stop'),(lo<=target,target,'target'))
  hit=next((x for x in checks if x[0]),None)
  if hit: _,price,reason=hit; return (side*(price-fill)-0.00015)/risk,reason
 price=float(f.iloc[-1].close); return (side*(price-fill)-0.00015)/risk,'end_mark'
frames={p:load(p) for p in PAIRS}; cache=json.loads((ROOT/'backtest/ctrader_allocator_14d_demo_validation/signal_cache.json').read_text())['selected_by_pair']
rows=[]
for p,signals in cache.items():
 for s in signals:
  q=score_opportunity(s,frames[p]); net,reason=outcome(s,frames[p]); rows.append({'pair':p,'variant':s['variant'],'signal_close_utc':s['signal_close_utc'],'side':s['side'],'planned_rr':s['planned_rr'],'regime_state':q['regime']['state'],'regime_score':q['regime']['score'],'liquidity_score':q['liquidity']['score'],'quality_score':q['quality_score'],'net_R_counterfactual':net,'outcome':'WIN' if net>0 else 'LOSS','exit_reason':reason})
rows.sort(key=lambda r:r['signal_close_utc']); OUT.mkdir(parents=True,exist_ok=True)
with (OUT/'opportunity_scores.csv').open('w',newline='') as h:
 w=csv.DictWriter(h,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
def metrics(xs):
 wins=[r for r in xs if r['net_R_counterfactual']>0]; losses=[r for r in xs if r['net_R_counterfactual']<0]; return {'n':len(xs),'wins':len(wins),'win_rate_pct':100*len(wins)/len(xs) if xs else None,'total_R':sum(r['net_R_counterfactual'] for r in xs),'avg_R':sum(r['net_R_counterfactual'] for r in xs)/len(xs) if xs else None}
by_state={s:metrics([r for r in rows if r['regime_state']==s]) for s in sorted({r['regime_state'] for r in rows})}
ranked=sorted(rows,key=lambda r:r['quality_score'],reverse=True); half=max(1,len(ranked)//2)
summary={'note':'Causal signal-quality diagnostic only; scores use data at signal close. Counterfactual outcomes use future bars and are never inputs to scores. This is not yet wired into demo execution.','all_selected':metrics(rows),'top_half_regime':metrics(sorted(rows,key=lambda r:r['regime_score'],reverse=True)[:half]),'top_half_liquidity':metrics(sorted(rows,key=lambda r:r['liquidity_score'],reverse=True)[:half]),'top_half_combined_quality':metrics(ranked[:half]),'regime_breakdown':by_state}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
lines=['# 14-Day Causal Quality Experiment','',summary['note'],'','| Cohort | N | Win rate | Total R | Avg R |','|---|---:|---:|---:|---:|']
for k,label in [('all_selected','A — all canonical valid signals'),('top_half_regime','C — top half by market regime score'),('top_half_liquidity','D — top half by liquidity quality'),('top_half_combined_quality','E — top half by combined quality')]:
 m=summary[k]; lines.append(f"| {label} | {m['n']} | {m['win_rate_pct']:.2f}% | {m['total_R']:.4f} | {m['avg_R']:.4f} |")
lines += ['','## Regime breakdown','', '| Regime | N | Win rate | Total R | Avg R |','|---|---:|---:|---:|---:|']
for state,m in by_state.items(): lines.append(f"| {state} | {m['n']} | {m['win_rate_pct']:.2f}% | {m['total_R']:.4f} | {m['avg_R']:.4f} |")
lines += ['','The cohorts above are diagnostic selections, not live filters. The combined quality score is not enabled in the demo robot.']
(OUT/'report.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,indent=2))
