#!/usr/bin/env python3
"""Research-only executable CRT-SMC hybrid; preserves every CRT candidate."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from run_crt_failure_diagnostics_24d import load_frames, atr, pivots, structural_stop, simulate, metric

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backtest/crt_trader_24d_results/crt_smc_hybrid/trade_matrix.csv"
OUT = ROOT / "backtest/crt_trader_24d_results/crt_smc_hybrid_execution"


def causal_path_target(frame, row, entry_idx):
    entry=float(row.entry); eq=float(row.equilibrium); target=float(row.target); side=str(row.side).upper(); direction=1 if side=="LONG" else -1
    if abs(target-entry) <= 6*atr(frame,entry_idx):
        return target, "CRT_BOUNDARY"
    highs,lows=pivots(frame,entry_idx,3)
    candidates=[p for i,p in (highs if side=="LONG" else lows) if i+3<=entry_idx and (p-entry)*direction > (eq-entry)*direction and (p-target)*direction <= 0]
    if candidates:
        return min(candidates,key=lambda p: abs(p-entry)), "CAUSAL_OPPOSING_SWING"
    return eq, "EQUILIBRIUM_FALLBACK"


def run():
    data=pd.read_csv(SOURCE); frames=load_frames(); rows=[]
    for _,row in data.iterrows():
        frame=frames[str(row.instrument).upper()]; ei=frame.index.get_indexer([pd.Timestamp(row.entry_time)])[0]; side=str(row.side).upper()
        stop,stop_available=structural_stop(frame,ei,float(row.entry),side)
        target,target_reason=causal_path_target(frame,row,ei)
        if target == float(row.equilibrium):
            r,reason=simulate(frame,row,stop,target,"eq_full")
        else:
            r,reason=simulate(frame,row,stop,target,"current")
        aligned=bool(row.smc_htf_alignment); fvg=bool(row.smc_fvg_near_entry)
        base={"instrument":row.instrument,"entry_time":row.entry_time,"r_multiple":r,"structural_stop_available":stop_available,"target_reason":target_reason,"target_used":target,"htf_aligned":aligned,"fvg_near_entry":fvg,"ob_near_entry":bool(row.smc_ob_near_entry)}
        rows.append(base)
    d=pd.DataFrame(rows)
    d["baseline_r"]=data.r_multiple.to_numpy()
    d["hybrid_r"]=d.r_multiple
    d["hybrid_htf025_r"]=d.r_multiple*d.htf_aligned.map({True:1.0,False:0.25})
    d["hybrid_htf025_fvg075_r"]=d.r_multiple*d.htf_aligned.map({True:1.0,False:0.25})*d.fvg_near_entry.map({True:1.0,False:0.75})
    variants={"baseline":d.baseline_r,"structural_stop_path_target":d.hybrid_r,"hybrid_htf025":d.hybrid_htf025_r,"hybrid_htf025_fvg075":d.hybrid_htf025_fvg075_r}
    metrics={name:metric(values) for name,values in variants.items()}
    cost={name:{f"cost_{c:.2f}R":metric(values-c) for c in [0.05,0.10]} for name,values in variants.items()}
    summary={"trades_preserved":len(d),"metrics":metrics,"cost_sensitivity":cost,"counts":{"target_crt_boundary":int((d.target_reason=="CRT_BOUNDARY").sum()),"target_causal_swing":int((d.target_reason=="CAUSAL_OPPOSING_SWING").sum()),"target_equilibrium_fallback":int((d.target_reason=="EQUILIBRIUM_FALLBACK").sum()),"structural_stop_available":int(d.structural_stop_available.sum()),"htf_aligned":int(d.htf_aligned.sum()),"fvg_near_entry":int(d.fvg_near_entry.sum())},"policy":"All CRT candidates are retained; HTF and FVG affect soft risk only.","limitations":["The target is causal only from confirmed pre-entry pivots; it is not a full opposing-liquidity engine.","FVG/OB are evidence/risk features here, not a delayed retest-entry model.","Risk multipliers are hypotheses and must be walk-forward validated.","No spread, slippage, commission, or news data are in the fixtures."]}
    OUT.mkdir(parents=True,exist_ok=True); d.to_csv(OUT/"trade_matrix.csv",index=False); (OUT/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    lines=["# CRT-SMC executable hybrid — 24 days","","> Every CRT candidate is preserved. Structural stop and causal target alter management; HTF/FVG alter only soft risk.","","| Variant | Trades | Win rate | Total R | Avg R | PF | Max DD R |","|---|---:|---:|---:|---:|---:|---:|"]
    for name,m in metrics.items(): lines.append(f"| {name} | {m['trades']} | {m['win_rate_pct']:.2f}% | {m['total_r']:.4f} | {m['avg_r']:.4f} | {m['profit_factor']} | {m['max_drawdown_r']:.4f} |")
    lines += ["","## Implementation counts",""]+[f"- {k}: {v}" for k,v in summary['counts'].items()]+["","## Limitations",""]+[f"- {x}" for x in summary['limitations']]+[""]
    (OUT/"report.md").write_text("\n".join(lines)); print(json.dumps(summary,indent=2))

if __name__=="__main__": run()
