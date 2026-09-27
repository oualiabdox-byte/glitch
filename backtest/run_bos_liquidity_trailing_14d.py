#!/usr/bin/env python3
from __future__ import annotations
import csv,json
from pathlib import Path
import pandas as pd
from allocation.opportunity_quality import score_opportunity_v2
from backtest.ctrader_allocator_strategy_comparison import PAIRS,CYCLE_CONFIG,_load_pair,_rows,run_portfolio
from strategy.volume_cycle_allocator import build_volume_cycles
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'backtest/ctrader_volume_data'; BOS=ROOT/'backtest/ablation_14d_bos_after_choch'; OUT=ROOT/'backtest/ablation_14d_bos_liquidity_trailing'
def main():
 frames={}; volume_rows={}
 for pair in PAIRS:
  frame,_=_load_pair(DATA/f'{pair}_m5_14d.json'); frames[pair]=frame; volume_rows[pair]=_rows(frame,include_volume=True)
 cache=json.loads((BOS/'signal_cache.json').read_text()); signals=[s for values in cache['selected_by_pair'].values() for s in values]
 multipliers={}; scores=[]
 for s in signals:
  q=score_opportunity_v2(s,frames[s['pair']]); multipliers[s['signal_id']]=q['allocation_multiplier']; scores.append({'signal_id':s['signal_id'],'pair':s['pair'],'signal_close_utc':s['signal_close_utc'],'regime_state':q['regime']['state'],'quality_score':q['quality_score'],'allocation_multiplier':q['allocation_multiplier']})
 cycles={p:build_volume_cycles(p,volume_rows[p],CYCLE_CONFIG) for p in PAIRS}; initial={p:1/len(PAIRS) for p in PAIRS}
 results={}
 for label,mode in [('baseline',None),('be_1r','BE_1R'),('trail_1r','TRAIL_1R'),('trail_1_5r','TRAIL_1_5R')]:
  results[label]=run_portfolio('bos_regime_'+label,list(PAIRS),frames,signals,cycles,initial,adaptive=True,signal_multipliers=multipliers,dynamic_stop_mode=mode)
 OUT.mkdir(parents=True,exist_ok=True)
 for label,r in results.items():
  rows=r['trades'];
  with (OUT/f'trades_{label}.csv').open('w',newline='') as h:
   w=csv.DictWriter(h,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
 summary={'note':'BOS_AFTER_CHOCH plus causal Liquidity Regime v2 soft multiplier. Dynamic stops update only from prior completed M5 bars, avoiding same-bar lookahead. BE_1R moves stop to entry after prior-bar favorable movement reaches 1R; TRAIL_1R moves to +0.25R after 1R and +0.75R after 1.5R; TRAIL_1_5R waits until 1.5R before moving to +0.75R.','selected_opportunities':len(signals),'results':{k:{'metrics':v['metrics'],'skipped':v['skipped']} for k,v in results.items()}}
 (OUT/'opportunity_scores.csv').write_text('signal_id,pair,signal_close_utc,regime_state,quality_score,allocation_multiplier\n'+'\n'.join(','.join(str(x[c]) for c in scores[0]) for x in scores)+'\n')
 (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 lines=['# 14-day BOS + Liquidity Regime dynamic-stop test','',summary['note'],'','| Metric | Baseline | BE after 1R | Trail after 1R/1.5R | Conservative trail after 1.5R |','|---|---:|---:|---:|---:|']
 for k,label in [('total_trades','Trades'),('win_rate_pct','Win rate %'),('profit_factor','PF'),('total_R_raw','Total R raw'),('total_R_weighted','Total R weighted'),('return_pct','Return %'),('max_DD_pct','Max DD %'),('average_R_weighted','Average weighted R')]:
  vals=[results[x]['metrics'].get(k) for x in ['baseline','be_1r','trail_1r','trail_1_5r']]; lines.append('| '+label+' | '+' | '.join('n/a' if v is None else f'{v:.6f}' for v in vals)+' |')
 (OUT/'report.md').write_text('\n'.join(lines)+'\n'); print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
