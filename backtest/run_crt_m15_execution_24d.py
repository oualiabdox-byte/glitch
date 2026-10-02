#!/usr/bin/env python3
"""Compare M5 CRT execution with M15 and M15+M5 confirmation variants."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.crt_tbs_14d import body_tbs_candidates, htf_purges, simulate_trade
from backtest.crt_trader_14d import load_frame, metrics

DATA = ROOT / "backtest/ctrader_volume_data"
BASE = ROOT / "backtest/crt_trader_24d_results/trades.csv"
OUT = ROOT / "backtest/crt_trader_24d_results/m15_execution"


def complete_general(frame, minutes, min_count):
    htf = frame.resample("2h", label="left", closed="left").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
    counts = frame.close.resample("2h", label="left", closed="left").count()
    htf = htf.loc[counts[counts >= min_count].index]
    return frame, htf


def aggregate_15m(m5):
    return m5.resample("15min", label="left", closed="left").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()


def run_pair(path, mode, max_gap=6, window_buckets=1):
    payload=json.loads(path.read_text()); pair=str(payload.get("pair") or path.name.split("_")[0]).upper(); m5=load_frame(path); m15=aggregate_15m(m5)
    # 2H CRT ranges are built from completed M15 candles (8 bars per range).
    exec_frame, htf=complete_general(m15,15,8); purges=htf_purges(exec_frame,htf); rows=[]
    for bucket,purge in purges.items():
        pos=htf.index.get_loc(bucket)
        if pos+window_buckets>=len(htf): continue
        start=int(exec_frame.index.searchsorted(bucket)); end=int(exec_frame.index.searchsorted(htf.index[pos+window_buckets]))
        if end<=start+8: continue
        candidates=body_tbs_candidates(exec_frame,start,end,purge["side"], max_gap=max_gap)
        if not candidates: continue
        chosen=None
        for c in candidates[:1]:
            # Hybrid confirmation: at least one M5 close in the M15 entry bar
            # must confirm the re-entry side; this does not create a new signal.
            if mode=="m15_m5_confirm":
                t=exec_frame.index[int(c["entry"])]
                m5_start=m5.index.searchsorted(t); m5_end=m5.index.searchsorted(t+pd.Timedelta(minutes=15))
                closes=m5.close.iloc[int(m5_start):int(m5_end)]
                level=float(c["level"])
                ok=bool((closes>level).any()) if purge["side"]=="LONG" else bool((closes<level).any())
                if not ok: continue
            trade=simulate_trade(exec_frame,c,purge["side"],purge,purge["purge_time"])
            if trade is not None: chosen=trade
        if chosen is not None:
            row=chosen.__dict__.copy(); row.update({"instrument":pair,"symbol":pair,"execution_mode":mode}); rows.append(row)
    return rows


def duration_metrics(rows):
    d=pd.DataFrame(rows)
    if d.empty: return {"trades":0}
    d["entry_time"]=pd.to_datetime(d.entry_time,utc=True); d["exit_time"]=pd.to_datetime(d.exit_time,utc=True); mins=(d.exit_time-d.entry_time).dt.total_seconds()/60
    m=metrics(rows); m.update({"median_duration_min":round(float(mins.median()),2),"mean_duration_min":round(float(mins.mean()),2),"pct_le_15m":round(float((mins<=15).mean()*100),2),"pct_le_30m":round(float((mins<=30).mean()*100),2),"pct_gt_60m":round(float((mins>60).mean()*100),2),"eq_reached_pct":round(float((d.exit_reason.isin(["BREAKEVEN","TARGET"])).mean()*100),2)})
    return m


def main():
    baseline=pd.read_csv(BASE).to_dict("records") if BASE.exists() else []
    all_rows={"m15":[],"m15_gap12":[],"m15_4h":[],"m15_4h_gap12":[],"m15_4h_m5_confirm":[],"m15_4h_gap12_m5_confirm":[]}
    for path in sorted(DATA.glob("*_m5_24d.json")):
        for mode in all_rows:
            wide = "gap12" in mode
            four_h = "4h" in mode
            all_rows[mode].extend(run_pair(path,mode,max_gap=12 if wide else 6,window_buckets=2 if four_h else 1))
    results={"m5_current":duration_metrics(baseline),**{mode:duration_metrics(rows) for mode,rows in all_rows.items()}}
    costs={name:{f"cost_{c:.2f}R":metrics([{"r_multiple": float(r["r_multiple"])-c} for r in rows]) for c in [0.05,0.10]} for name,rows in {"m5_current":baseline,**all_rows}.items()}
    summary={"results":results,"cost_sensitivity":costs,"rows_preserved_m5":len(baseline),"limitations":["M15 aggregates the repository M5 OHLC into 15-minute bars; intrabar ordering remains unknown.","The Hybrid requires an M5 close inside the M15 re-entry bar; it is not a full delayed M5-to-M15 retest model.","No spread, slippage, commission, or news costs are in the fixtures."]}
    OUT.mkdir(parents=True,exist_ok=True); (OUT/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    for mode,rows in all_rows.items(): pd.DataFrame(rows).to_csv(OUT/f"{mode}_trades.csv",index=False)
    lines=["# CRT M15 execution comparison — 24 days","","> M15 is a separate execution backtest. The original M5 CRT is unchanged.","","| Mode | Trades | Win rate | Total R | PF | Max DD R | Median min | <=15m | >60m | Eq reached |","|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name,m in results.items(): lines.append(f"| {name} | {m.get('trades',0)} | {m.get('win_rate_pct',0):.2f}% | {m.get('total_r',0):.4f} | {m.get('profit_factor')} | {m.get('max_drawdown_r',0):.4f} | {m.get('median_duration_min')} | {m.get('pct_le_15m')}% | {m.get('pct_gt_60m')}% | {m.get('eq_reached_pct')}% |")
    lines += ["","## Cost sensitivity","","| Mode | Cost | Total R | PF |","|---|---:|---:|---:|"]
    for mode,vals in costs.items():
        for cost,m in vals.items(): lines.append(f"| {mode} | {cost.replace('cost_','')} | {m['total_r']:.4f} | {m['profit_factor']} |")
    lines += ["","## Caveats","",*[f"- {x}" for x in summary['limitations']],""]
    (OUT/"report.md").write_text("\n".join(lines)); print(json.dumps(summary,indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())
