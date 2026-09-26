#!/usr/bin/env python3
"""Run the three requested original forex_bot variants on open Yahoo 5m data.

This uses the repository's existing strategy.engine unchanged. It is a research
backtest only; Yahoo candles are indicative and do not represent executable bid/ask history.
"""
from __future__ import annotations
import argparse, time
from pathlib import Path
import sys
import requests
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strategy.variants import build_variant

ROOT = Path(__file__).resolve().parents[1]
PAIRS = {"EURUSD": ("EURUSD=X", 0.0001), "GBPUSD": ("GBPUSD=X", 0.0001)}
CASES = [
    {"pair":"EURUSD", "variant":"eurusd_swing3_choch_or_bos", "swing":3, "mode":"CHOCH_OR_BOS"},
    {"pair":"GBPUSD", "variant":"gbpusd_swing2_choch_only", "swing":2, "mode":"CHOCH_ONLY"},
    {"pair":"EURUSD", "variant":"eurusd_swing2_choch_or_bos", "swing":2, "mode":"CHOCH_OR_BOS"},
]


def fetch(pair, days, cache, refresh=False):
    ticker, _ = PAIRS[pair]
    cache.mkdir(exist_ok=True)
    path = cache / f"{pair}_5m_{days}d.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, parse_dates=["timestamp"], index_col="timestamp")
    end = int(time.time()); start = end - days * 86400
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}", params={
        "period1": start, "period2": end, "interval": "5m", "includePrePost": "true",
        "events": "div,splits"}, headers={"User-Agent":"Mozilla/5.0"}, timeout=30)
    r.raise_for_status(); result = (r.json().get("chart", {}).get("result") or [])
    if not result: raise RuntimeError(f"No Yahoo data for {pair}")
    x = result[0]; q = x["indicators"]["quote"][0]
    d = pd.DataFrame({"timestamp":pd.to_datetime(x["timestamp"],unit="s",utc=True),
        "open":q["open"],"high":q["high"],"low":q["low"],"close":q["close"]})
    d = d.dropna().drop_duplicates("timestamp").set_index("timestamp").sort_index()
    d.to_csv(path); return d


def rows(d):
    return [{"time":ts.isoformat(),"open":float(r.open),"high":float(r.high),
             "low":float(r.low),"close":float(r.close)} for ts,r in d.iterrows()]


def signals(raw, variant):
    h1 = raw.resample("1h", label="left", closed="left").agg(
        {"open":"first","high":"max","low":"min","close":"last"}).dropna()
    m5 = rows(raw); h1r = rows(h1); strategy = build_variant(variant)
    out=[]; last=None
    for i in range(100, len(m5)):
        current = pd.Timestamp(m5[i]["time"]); cutoff = current.floor("1h")
        closed_h1 = [r for r in h1r if pd.Timestamp(r["time"])+pd.Timedelta(hours=1) <= cutoff]
        if len(closed_h1) < 20: continue
        decision = strategy.evaluate(closed_h1, m5[:i+1])
        if not decision.is_signal: continue
        event = decision.evidence.get("m5_bos", {}); event_time = event.get("time")
        if event_time == last: continue
        last = event_time
        out.append({"time":pd.Timestamp(event_time),"side":1 if decision.side=="LONG" else -1,
                    "entry":float(decision.entry_price),"sl":float(decision.stop_price),
                    "tp":float(decision.target_price),"rr":float(decision.risk_reward or 0)})
    return out


def simulate(raw, signal, pip):
    idx = raw.index.searchsorted(signal["time"], side="right")
    if idx >= len(raw): return None
    side=signal["side"]; entry=signal["entry"]; sl=signal["sl"]; tp=signal["tp"]
    reason="end"; exit_px=float(raw.iloc[-1].close)
    for j in range(idx,len(raw)):
        b=raw.iloc[j]
        if side==1:
            if b.low<=sl: exit_px=sl; reason="sl"; break
            if b.high>=tp: exit_px=tp; reason="tp"; break
        else:
            if b.high>=sl: exit_px=sl; reason="sl"; break
            if b.low<=tp: exit_px=tp; reason="tp"; break
    raw_return=side*(exit_px-entry)/entry-(1.5*pip)/entry
    risk=abs(entry-sl)/entry
    return {"account_return":0.005*(raw_return/risk if risk else 0),"reason":reason}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--days",type=int,default=7); ap.add_argument("--refresh",action="store_true"); args=ap.parse_args()
    cache=ROOT/"backtest"/"forex_test_data"; results=[]
    for case in CASES:
        raw=fetch(case["pair"],args.days,cache,args.refresh); _,pip=PAIRS[case["pair"]]
        trades=[x for s in signals(raw,case["variant"]) if (x:=simulate(raw,s,pip))]
        vals=[x["account_return"] for x in trades]; wins=[x for x in vals if x>0]; losses=[x for x in vals if x<0]
        equity=1.; peak=1.; dd=0.
        for v in vals: equity*=1+v; peak=max(peak,equity); dd=max(dd,(peak-equity)/peak)
        results.append({**case,"data_days":args.days,"bars_5m":len(raw),"trades":len(vals),
            "wins":len(wins),"losses":len(vals)-len(wins),"win_rate":len(wins)/len(vals) if vals else 0,
            "profit_factor":sum(wins)/abs(sum(losses)) if losses else (float("inf") if wins else 0),
            "return_pct":(equity-1)*100,"max_drawdown_pct":dd*100})
    out=ROOT/"backtest"/"original_forex_variants_7d_results.csv"; pd.DataFrame(results).to_csv(out,index=False)
    print(pd.DataFrame(results).to_string(index=False)); print(f"Saved {out}")

if __name__ == "__main__": main()
