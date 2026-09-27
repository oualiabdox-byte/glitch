#!/usr/bin/env python3
from __future__ import annotations
import csv,json
from pathlib import Path
import pandas as pd
from allocation.opportunity_quality import score_opportunity_v2
from backtest.ctrader_allocator_strategy_comparison import (
    PAIRS,CYCLE_CONFIG,_load_pair,_rows,run_portfolio
)
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'backtest/ctrader_volume_data'
BOS=ROOT/'backtest/ablation_14d_bos_after_choch'
OUT=ROOT/'backtest/ablation_14d_bos_liquidity_regime'

def main():
    frames={}; volume_rows={}
    for pair in PAIRS:
        frame,_=_load_pair(DATA/f'{pair}_m5_14d.json'); frames[pair]=frame; volume_rows[pair]=_rows(frame,include_volume=True)
    payload=json.loads((BOS/'signal_cache.json').read_text())
    signals=[s for values in payload['selected_by_pair'].values() for s in values]
    scored=[]; multipliers={}
    for signal in signals:
        q=score_opportunity_v2(signal,frames[signal['pair']]); sid=signal['signal_id']; multipliers[sid]=q['allocation_multiplier']
        scored.append({'signal_id':sid,'pair':signal['pair'],'signal_close_utc':signal['signal_close_utc'],'regime_state':q['regime']['state'],'regime_score':q['regime']['score'],'liquidity_score':q['liquidity']['score'],'quality_score':q['quality_score'],'allocation_multiplier':q['allocation_multiplier']})
    cycles={pair:__import__('strategy.volume_cycle_allocator',fromlist=['build_volume_cycles']).build_volume_cycles(pair,volume_rows[pair],CYCLE_CONFIG) for pair in PAIRS}
    equal_weights={pair:1/len(PAIRS) for pair in PAIRS}
    adaptive_weights={pair:1/len(PAIRS) for pair in PAIRS}
    # The allocator is stateful, so run the ordinary BOS adaptive portfolio once
    # with the same initial weights and then rerun with quality multipliers.
    base_equal=run_portfolio('bos_equal_weight',list(PAIRS),frames,signals,cycles,equal_weights,adaptive=False)
    base_adaptive=run_portfolio('bos_adaptive',list(PAIRS),frames,signals,cycles,adaptive_weights,adaptive=True)
    quality_equal=run_portfolio('bos_liquidity_regime_equal',list(PAIRS),frames,signals,cycles,equal_weights,adaptive=False,signal_multipliers=multipliers)
    quality_adaptive=run_portfolio('bos_liquidity_regime_adaptive',list(PAIRS),frames,signals,cycles,adaptive_weights,adaptive=True,signal_multipliers=multipliers)
    def export(result):
        name=result['name'];
        with (OUT/f'trades_{name}.csv').open('w',newline='') as h:
            rows=result['trades'];
            if rows:
                w=csv.DictWriter(h,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    OUT.mkdir(parents=True,exist_ok=True)
    for r in (base_equal,base_adaptive,quality_equal,quality_adaptive): export(r)
    with (OUT/'opportunity_scores.csv').open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(scored[0])); w.writeheader(); w.writerows(scored)
    summary={'note':'BOS_AFTER_CHOCH signals are fixed from the 14-day ablation. Liquidity Regime v2 changes only a causal bounded soft multiplier (0.85–1.20); it does not reject signals or change entry/SL/TP.','selected_opportunities':len(signals),'multiplier_min':min(multipliers.values()),'multiplier_max':max(multipliers.values()),'bos_equal':base_equal['metrics'],'bos_adaptive':base_adaptive['metrics'],'bos_regime_equal':quality_equal['metrics'],'bos_regime_adaptive':quality_adaptive['metrics'],'bos_adaptive_skipped':base_adaptive['skipped'],'bos_regime_adaptive_skipped':quality_adaptive['skipped']}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# 14-day BOS_AFTER_CHOCH + Liquidity Regime v2','',summary['note'],'','| Metric | BOS adaptive | BOS + Regime adaptive |','|---|---:|---:|']
    for k,label in [('total_trades','Trades'),('win_rate_pct','Win rate %'),('profit_factor','PF'),('total_R_raw','Total R raw'),('total_R_weighted','Total R weighted'),('return_pct','Return %'),('max_DD_pct','Max DD %'),('average_R_weighted','Average weighted R')]:
        a=base_adaptive['metrics'].get(k); b=quality_adaptive['metrics'].get(k); lines.append(f'| {label} | {"n/a" if a is None else f"{a:.6f}"} | {"n/a" if b is None else f"{b:.6f}"} |')
    lines += ['',f"Selected opportunities: {len(signals)}",f"Multiplier range: {min(multipliers.values()):.4f}–{max(multipliers.values()):.4f}",'','The regime multiplier is research-only and is not enabled in the demo robot.']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
