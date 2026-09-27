#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
import pandas as pd
from allocation.opportunity_quality import score_opportunity_v2
ROOT=Path(__file__).resolve().parents[1]; PAIRS=('AUDUSD','EURUSD','GBPUSD','NZDUSD','USDCAD','USDCHF','USDJPY')
def load(data,suffix,p):
 d=json.loads((data/f'{p}_m5_{suffix}.json').read_text()); f=pd.DataFrame(d['candles']); f['time']=pd.to_datetime(f['time'],utc=True); return f.sort_values('time').set_index('time')
def outcome(s,f):
 idx=f.index.searchsorted(pd.Timestamp(s['signal_close_utc']),side='left'); fill=float(f.iloc[idx].open); side=1 if s['side']=='LONG' else -1; stop=float(s['stop']); target=float(s['target']); risk=abs(fill-stop)
 for j in range(idx,len(f)):
  b=f.iloc[j]; op,hi,lo=map(float,(b.open,b.high,b.low)); checks=((op<=stop,op,'stop_gap'),(op>=target,target,'target_gap'),(lo<=stop,stop,'stop'),(hi>=target,target,'target')) if side==1 else ((op>=stop,op,'stop_gap'),(op<=target,target,'target_gap'),(hi>=stop,stop,'stop'),(lo<=target,target,'target'))
  hit=next((x for x in checks if x[0]),None)
  if hit: _,price,reason=hit; return (side*(price-fill)-0.00015)/risk,reason
 price=float(f.iloc[-1].close); return (side*(price-fill)-0.00015)/risk,'end_mark'
def metrics(rows,weighted=False):
 vals=[r['net_R']*(r['multiplier'] if weighted else 1.0) for r in rows]; wins=[r for r in rows if r['net_R']>0]; return {'trades':len(rows),'wins':len(wins),'win_rate_pct':100*len(wins)/len(rows) if rows else None,'total_R':sum(vals),'avg_R':sum(vals)/len(vals) if vals else None,'weighted':weighted}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--suffix',default='14d'); ap.add_argument('--data-dir',type=Path,default=ROOT/'backtest/ctrader_volume_data'); ap.add_argument('--output-dir',type=Path); a=ap.parse_args(); out=a.output_dir or ROOT/f'backtest/quality_v2_{a.suffix}_experiment'; out.mkdir(parents=True,exist_ok=True)
 frames={p:load(a.data_dir,a.suffix,p) for p in PAIRS}; cache=json.loads((ROOT/f'backtest/ctrader_allocator_{a.suffix}_demo_validation/signal_cache.json' if a.suffix=='14d' else ROOT/f'backtest/ctrader_allocator_{a.suffix}_comparison/signal_cache.json').read_text())['selected_by_pair']
 rows=[]
 for p,ss in cache.items():
  for s in ss:
   q=score_opportunity_v2(s,frames[p]); net,reason=outcome(s,frames[p]); rows.append({'pair':p,'variant':s['variant'],'signal_close_utc':s['signal_close_utc'],'regime_state':q['regime']['state'],'regime_score':q['regime']['score'],'liquidity_score':q['liquidity']['score'],'quality_score':q['quality_score'],'multiplier':q['allocation_multiplier'],'net_R':net,'outcome':'WIN' if net>0 else 'LOSS','exit_reason':reason})
 rows.sort(key=lambda x:x['signal_close_utc']);
 with (out/'opportunity_scores.csv').open('w',newline='') as h: w=csv.DictWriter(h,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
 summary={'note':'All canonical valid signals remain eligible. v2 changes only a bounded research allocation multiplier 0.85–1.20; it is not connected to demo execution. Counterfactual net_R uses future bars for evaluation only.','unweighted':metrics(rows),'soft_weighted':metrics(rows,True),'multiplier_min':min(r['multiplier'] for r in rows),'multiplier_max':max(r['multiplier'] for r in rows),'states':{}}
 for st in sorted({r['regime_state'] for r in rows}): summary['states'][st]=metrics([r for r in rows if r['regime_state']==st],True)
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 lines=[f'# Quality v2 soft-allocation experiment ({a.suffix})','',summary['note'],'','| Metric | Unweighted | Soft weighted |','|---|---:|---:|']
 for k,l in [('trades','Trades'),('win_rate_pct','Win rate %'),('total_R','Total R'),('avg_R','Average R')]: lines.append(f"| {l} | {summary['unweighted'][k]:.4f} | {summary['soft_weighted'][k]:.4f} |" if isinstance(summary['unweighted'][k],float) else f"| {l} | {summary['unweighted'][k]} | {summary['soft_weighted'][k]} |")
 lines += ['',f"Multiplier range: {summary['multiplier_min']:.4f} to {summary['multiplier_max']:.4f}",'','| State | N | Weighted win rate | Weighted total R |','|---|---:|---:|---:|']
 for st,m in summary['states'].items(): lines.append(f"| {st} | {m['trades']} | {m['win_rate_pct']:.2f}% | {m['total_R']:.4f} |")
 (out/'report.md').write_text('\n'.join(lines)+'\n'); print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
