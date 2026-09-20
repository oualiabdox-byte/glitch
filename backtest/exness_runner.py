"""ICT backtest using Exness public historical tick data. No MT5/login."""
import argparse,csv,json
from datetime import datetime,timezone,timedelta
from data.exness_ticks import ExnessTickData
from strategy.ict_strategy import evaluate_ict_2022

def dt(v): return datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(timezone.utc)

def session_for(t):
    h=t.hour
    return "london" if 7<=h<12 else "overlap" if 12<=h<13 else "new_york" if 13<=h<17 else "other"

def outcome(candles,i,side,stop,target):
    for j in range(i+1,len(candles)):
        c=candles[j]
        if side=="LONG":
            sl=c.get("bid_low",c["low"])<=stop
            tp=c.get("bid_high",c["high"])>=target
        else:
            sl=c.get("ask_high",c["high"])>=stop
            tp=c.get("ask_low",c["low"])<=target
        if sl and tp:
            return "SL",j,stop
        if sl: return "SL",j,stop
        if tp: return "TP",j,target
    px=(candles[-1].get("bid_close",candles[-1]["close"]) if side=="LONG"
        else candles[-1].get("ask_close",candles[-1]["close"]))
    return "OPEN",len(candles)-1,px

def run(symbol,start,end,cache_dir="data/exness_cache"):
    feed=ExnessTickData(cache_dir)
    h1=feed.bars(symbol,start,end,"1H")
    h4=feed.bars(symbol,start,end,"4H")
    if len(h1)<100 or len(h4)<40:
        raise RuntimeError(f"Not enough Exness data: H1={len(h1)}, H4={len(h4)}")
    trades=[]; last_exit=-1
    for i in range(60,len(h1)-1):
        if i<=last_exit: continue
        t=dt(h1[i]["time"])
        s=session_for(t)
        if s not in ("london","new_york","overlap"): continue

        # h1[i] is evaluated at its close; only H4 candles whose full 4h
        # interval has closed by that moment are allowed.
        close_time=t+timedelta(hours=1)
        h4c=[c for c in h4 if dt(c["time"])+timedelta(hours=4)<=close_time]
        if len(h4c)<30: continue

        setup=evaluate_ict_2022(h1[:i+1],h4c,symbol,session_context=s)
        if not setup: continue

        side=setup["side"]
        spread=h1[i].get("spread_avg",0.0)
        # FVG midpoint is the modeled signal price; execution pays half the
        # current average spread in the direction of the spread.
        entry=(setup["entry_mid"]+spread/2 if side=="LONG"
               else setup["entry_mid"]-spread/2)
        stop,target=setup["stop_price"],setup["tp_target"]
        result,ei,px=outcome(h1,i,side,stop,target)
        risk=abs(entry-stop)
        r=((px-entry)/risk if side=="LONG" else (entry-px)/risk) if risk else 0
        trades.append({
            "pair":symbol,"time_utc":h1[i]["time"],"side":side,
            "entry":entry,"stop":stop,"tp1":target,"tp2":target,
            "outcome":result,"pnl_r":r,"rr":setup["rr"],
            "spread_avg":spread,"exit_time_utc":h1[ei]["time"]
        })
        last_exit=ei
    return trades

def metrics(trades):
    if not trades:
        return {"trades":0,"wins":0,"losses":0,"win_rate":0,
                "profit_factor":0,"expectancy_r":0,"max_drawdown_r":0,
                "avg_r":0}
    rs=[t["pnl_r"] for t in trades]
    w=[r for r in rs if r>0]; l=[r for r in rs if r<0]
    eq=peak=dd=0
    for r in rs:
        eq+=r; peak=max(peak,eq); dd=max(dd,peak-eq)
    return {
        "trades":len(rs),"wins":len(w),"losses":len(l),
        "win_rate":len(w)/len(rs),
        "profit_factor":sum(w)/abs(sum(l)) if l else float("inf"),
        "expectancy_r":sum(rs)/len(rs),"avg_r":sum(rs)/len(rs),
        "max_drawdown_r":dd,"net_r":sum(rs)
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--symbol",default="EURUSD")
    p.add_argument("--start",required=True)
    p.add_argument("--end",required=True)
    p.add_argument("--csv")
    p.add_argument("--json")
    a=p.parse_args()
    trades=run(a.symbol,dt(a.start),dt(a.end))
    report=metrics(trades)
    if a.csv:
        fields=["pair","time_utc","side","entry","stop","tp1","tp2","outcome",
                "pnl_r","rr","spread_avg","exit_time_utc"]
        with open(a.csv,"w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(trades)
    if a.json:
        with open(a.json,"w") as f: json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))

if __name__=="__main__": main()
