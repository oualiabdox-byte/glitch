#!/usr/bin/env python3
"""Diagnose CRT failure modes without silently changing the canonical strategy."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backtest/ctrader_volume_data"
SOURCE = ROOT / "backtest/crt_trader_24d_results/crt_smc_hybrid/trade_matrix.csv"
OUT = ROOT / "backtest/crt_trader_24d_results/failure_diagnostics"


def load_frames():
    out = {}
    for path in sorted(DATA.glob("*_m5_24d.json")):
        payload = json.loads(path.read_text())
        pair = str(payload.get("pair") or path.name.split("_")[0]).upper()
        frame = pd.DataFrame(payload["candles"])
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frame = frame.sort_values("time").drop_duplicates("time").set_index("time")
        out[pair] = frame.astype({c: float for c in ["open", "high", "low", "close", "volume"]})
    return out


def atr(frame, idx, window=14):
    sample = frame.iloc[max(0, idx-window):idx]
    value = float((sample.high-sample.low).median()) if len(sample) else 0.0
    return value if value > 0 else max(abs(float(frame.close.iloc[idx]))*1e-5, 1e-12)


def pivots(frame, end=None, length=3):
    end = len(frame) if end is None else min(end, len(frame))
    highs, lows = [], []
    for i in range(length, min(end-length, len(frame)-length)):
        hi=float(frame.high.iloc[i]); lo=float(frame.low.iloc[i])
        if hi >= max(float(frame.high.iloc[i-j]) for j in range(1,length+1)) and hi > max(float(frame.high.iloc[i+j]) for j in range(1,length+1)):
            highs.append((i,hi))
        if lo <= min(float(frame.low.iloc[i-j]) for j in range(1,length+1)) and lo < min(float(frame.low.iloc[i+j]) for j in range(1,length+1)):
            lows.append((i,lo))
    return highs,lows


def nearest_target(frame, entry_idx, entry, eq, target, side):
    lo, hi = sorted((entry, target)); highs,lows=pivots(frame)
    candidates=[(i,p) for i,p in (highs if side=="LONG" else lows) if entry_idx < i < len(frame) and lo < p < hi]
    direction = 1 if side=="LONG" else -1
    beyond=[(i,p) for i,p in candidates if (p-entry)*direction > (eq-entry)*direction]
    if not beyond: return target, False
    return beyond[0][1], True


def structural_stop(frame, entry_idx, entry, side):
    highs,lows=pivots(frame, entry_idx, 3); unit=atr(frame,entry_idx); buf=0.05*unit
    if side=="LONG":
        eligible=[p for i,p in lows if i+3<=entry_idx and p<entry]
        return (eligible[-1]-buf if eligible else entry-unit), bool(eligible)
    eligible=[p for i,p in highs if i+3<=entry_idx and p>entry]
    return (eligible[-1]+buf if eligible else entry+unit), bool(eligible)


def simulate(frame, row, stop, target, mode="current", end_idx=None):
    side=str(row.side).upper(); long=side=="LONG"; direction=1 if long else -1
    entry=float(row.entry); eq=float(row.equilibrium); risk=abs(entry-stop)
    if risk<=0: return np.nan, "INVALID"
    entry_idx=frame.index.get_indexer([pd.Timestamp(row.entry_time)])[0]
    if entry_idx<0: return np.nan,"INVALID"
    recorded=frame.index.get_indexer([pd.Timestamp(row.exit_time)])[0]
    end_idx=len(frame)-1 if recorded<0 else max(entry_idx,recorded) if end_idx is None else end_idx
    if mode=="eq_full":
        for i in range(entry_idx+1,end_idx+1):
            hi=float(frame.high.iloc[i]); lo=float(frame.low.iloc[i])
            if (hi>=eq if long else lo<=eq): return abs(eq-entry)/risk,"EQ_FULL"
            if (lo<=stop if long else hi>=stop): return -1.0,"STOP_BEFORE_EQ"
        return ((float(frame.close.iloc[end_idx])-entry)*direction)/risk,"DATA_END"
    be=False; realized=0.0
    for i in range(entry_idx+1,end_idx+1):
        hi=float(frame.high.iloc[i]); lo=float(frame.low.iloc[i])
        effective_stop = entry if (be and mode=="current") else stop
        if (lo<=effective_stop if long else hi>=effective_stop):
            if not be: realized=-1.0
            return realized, "BE" if be else "STOP"
        if mode=="no_be":
            if (hi>=target if long else lo<=target): return abs(target-entry)/risk,"TARGET"
        else:
            if not be and (hi>=eq if long else lo<=eq):
                realized += 0.5*abs(eq-entry)/risk; be=True
            if be and (hi>=target if long else lo<=target):
                realized += 0.5*abs(target-entry)/risk; return realized,"TARGET"
    close=float(frame.close.iloc[end_idx]); move=(close-entry)*direction/risk
    return realized + (move if mode=="no_be" else 0.5*(move if be else move*2)), "DATA_END"


def metric(values):
    v=pd.Series(values,dtype=float).dropna(); wins=v[v>0]; losses=v[v<0]; gl=abs(float(losses.sum())); eq=v.cumsum(); dd=float((eq.cummax()-eq).max()) if len(v) else 0.0
    return {"trades":int(len(v)),"win_rate_pct":round(float((v>0).mean()*100),2) if len(v) else 0.0,"total_r":round(float(v.sum()),6),"avg_r":round(float(v.mean()),6) if len(v) else 0.0,"profit_factor":round(float(wins.sum()/gl),6) if gl else None,"max_drawdown_r":round(dd,6)}


def main():
    data=pd.read_csv(SOURCE); frames=load_frames(); rows=[]
    for _,row in data.iterrows():
        frame=frames[str(row.instrument).upper()]; entry_idx=frame.index.get_indexer([pd.Timestamp(row.entry_time)])[0]
        entry=float(row.entry); side=str(row.side).upper(); unit=atr(frame,entry_idx)
        # Stop and target experiments.
        extra_stop=(float(row.stop)+0.25*unit if side=="SHORT" else float(row.stop)-0.25*unit)
        struct_stop, struct_available=structural_stop(frame,entry_idx,entry,side)
        nt, nt_available=nearest_target(frame,entry_idx,entry,float(row.equilibrium),float(row.target),side)
        vals={}
        vals["baseline_current"],_=simulate(frame,row,float(row.stop),float(row.target),"current")
        vals["wider_stop_0.25_atr"],_=simulate(frame,row,extra_stop,float(row.target),"current")
        vals["structural_stop"],_=simulate(frame,row,struct_stop,float(row.target),"current")
        vals["no_breakeven"],_=simulate(frame,row,float(row.stop),float(row.target),"no_be")
        vals["full_exit_equilibrium"],_=simulate(frame,row,float(row.stop),float(row.equilibrium),"eq_full")
        vals["nearest_swing_beyond_eq"],_=simulate(frame,row,float(row.stop),nt,"current")
        r=row.to_dict(); r.update(vals); r["structural_stop_available"]=struct_available; r["nearest_target_available"]=nt_available; r["nearest_target"]=nt; r["target_cap_6atr"] = abs(float(row.target)-entry) <= 6*unit
        rows.append(r)
    result=pd.DataFrame(rows)
    OUT.mkdir(parents=True,exist_ok=True); result.to_csv(OUT/"trade_matrix.csv",index=False)
    variants=["baseline_current","wider_stop_0.25_atr","structural_stop","no_breakeven","full_exit_equilibrium","nearest_swing_beyond_eq"]
    variant_metrics={v:metric(result[v]) for v in variants}
    groups={}
    for name,group in result.groupby("htf_directional_alignment",dropna=False): groups[f"htf_alignment={name}"]=metric(group.baseline_current)
    for name,group in result.groupby("smc_fvg_near_entry",dropna=False): groups[f"fvg_near_entry={name}"]=metric(group.baseline_current)
    for name,group in result.groupby("smc_ob_near_entry",dropna=False): groups[f"ob_near_entry={name}"]=metric(group.baseline_current)
    for name,group in result.groupby("outcome_path",dropna=False): groups[f"path={name}"]=metric(group.baseline_current)
    cost_sensitivity={f"cost_{c:.2f}R":metric(result.baseline_current-c) for c in [0.02,0.05,0.10,0.15,0.20]}
    target_groups={"target_le_6_atr":metric(result.loc[result.target_cap_6atr,"baseline_current"]),"target_gt_6_atr":metric(result.loc[~result.target_cap_6atr,"baseline_current"])}
    summary={"trades":len(result),"variant_metrics":variant_metrics,"groups":groups,"cost_sensitivity":cost_sensitivity,"target_distance_groups":target_groups,"counts":{"structural_stop_available":int(result.structural_stop_available.sum()),"nearest_target_available":int(result.nearest_target_available.sum()),"target_le_6_atr":int(result.target_cap_6atr.sum())},"limitations":["Nearest swing and structural stop use causal 3-bar pivots as a research approximation.","FVG/OB groups use causal proximity evidence from the hybrid layer; they are not yet a retest-entry engine.","Costs are sensitivity assumptions in R because the fixture has no bid/ask or commission.","No variant changes the production CRT engine."]}
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    lines=["# CRT failure diagnostics — 24 days","","> Diagnostic variants only; canonical CRT signals were not modified.","","## Exit and stop variants","","| Variant | Trades | Win rate | Total R | Avg R | PF | Max DD R |","|---|---:|---:|---:|---:|---:|---:|"]
    for v,m in variant_metrics.items(): lines.append(f"| {v} | {m['trades']} | {m['win_rate_pct']:.2f}% | {m['total_r']:.4f} | {m['avg_r']:.4f} | {m['profit_factor']} | {m['max_drawdown_r']:.4f} |")
    lines += ["","## Baseline groups","","| Group | Trades | Win rate | Total R | PF | Max DD R |","|---|---:|---:|---:|---:|---:|"]
    for name,m in groups.items(): lines.append(f"| {name} | {m['trades']} | {m['win_rate_pct']:.2f}% | {m['total_r']:.4f} | {m['profit_factor']} | {m['max_drawdown_r']:.4f} |")
    lines += ["","## Execution cost sensitivity","","| Cost per trade | Total R | PF | Max DD R |","|---|---:|---:|---:|"]
    for name,m in cost_sensitivity.items(): lines.append(f"| {name.replace('cost_','')} | {m['total_r']:.4f} | {m['profit_factor']} | {m['max_drawdown_r']:.4f} |")
    lines += ["","## Caveats","",*[f"- {x}" for x in summary['limitations']],""]
    (OUT/"report.md").write_text("\n".join(lines)); print(json.dumps(summary,indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())
