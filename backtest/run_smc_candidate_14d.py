#!/usr/bin/env python3
from __future__ import annotations
import csv,json,os
from pathlib import Path
from allocation.opportunity_quality import score_opportunity_v2
from backtest.ctrader_allocator_strategy_comparison import PAIRS,CYCLE_CONFIG,_load_pair,_rows,run_portfolio,AllocatorConfig
from strategy.volume_cycle_allocator import build_volume_cycles
ROOT=Path(__file__).resolve().parents[1]
def main():
    suffix=os.getenv('SMC_DATA_SUFFIX','14d')
    data_dir=ROOT/'backtest/ctrader_volume_data'
    source=ROOT/f'backtest/ablation_{suffix}_gate_displacement'
    out=ROOT/f'backtest/ablation_{suffix}_smc_candidate'
    frames={}; volume_rows={}
    for pair in PAIRS:
        frame,_=_load_pair(data_dir/f'{pair}_m5_{suffix}.json'); frames[pair]=frame; volume_rows[pair]=_rows(frame,include_volume=True)
    cache=json.loads((source/'signal_cache.json').read_text())
    signals=[s for values in cache['selected_by_pair'].values() for s in values]
    multipliers={}; scores=[]
    for signal in signals:
        quality=score_opportunity_v2(signal,frames[signal['pair']])
        multipliers[signal['signal_id']]=quality['allocation_multiplier']
        scores.append({'signal_id':signal['signal_id'],'pair':signal['pair'],'signal_close_utc':signal['signal_close_utc'],'regime_state':quality['regime']['state'],'quality_score':quality['quality_score'],'allocation_multiplier':quality['allocation_multiplier']})
    cycles={p:build_volume_cycles(p,volume_rows[p],CYCLE_CONFIG) for p in PAIRS}
    initial={p:1/len(PAIRS) for p in PAIRS}; results={}
    adaptive=os.getenv('SMC_ADAPTIVE','true').lower() == 'true'
    floor=float(os.getenv('SMC_MIN_WEIGHT','0'))
    allocator_config=AllocatorConfig(**{**CYCLE_CONFIG.__dict__,'min_weight':floor})
    for label,mode in [('baseline',None),('trail_1_5r','TRAIL_1_5R')]:
        results[label]=run_portfolio('displacement_regime_'+label,list(PAIRS),frames,signals,cycles,initial,adaptive=adaptive,signal_multipliers=multipliers,dynamic_stop_mode=mode,allocator_config=allocator_config)
    out.mkdir(parents=True,exist_ok=True)
    for label,result in results.items():
        rows=result['trades']
        if rows:
            with (out/f'trades_{label}.csv').open('w',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    summary={'note':'BOS_AFTER_CHOCH + displacement gate (ratio >= 1.0) + causal Liquidity Regime v2 multiplier; conservative trail waits for 1.5R and then moves stop to +0.75R.','adaptive_allocator':adaptive,'min_weight_floor':floor,'selected_opportunities':len(signals),'results':{key:{'metrics':value['metrics'],'skipped':value['skipped']} for key,value in results.items()}}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (out/'opportunity_scores.csv').write_text('signal_id,pair,signal_close_utc,regime_state,quality_score,allocation_multiplier\n'+'\n'.join(','.join(str(row[col]) for col in scores[0]) for row in scores)+'\n' if scores else '')
    (out/'report.md').write_text(f'#{suffix} SMC candidate\n\n'+summary['note']+'\n\n```json\n'+json.dumps(summary,indent=2)+'\n```\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
