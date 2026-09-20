"""Controlled alternative-strategy backtest on Exness public tick history."""
import argparse,csv,json
from datetime import datetime,timezone,timedelta
from data.exness_ticks import ExnessTickData
from strategy.alternative_strategies import three_ducks,breakout_retest,sweep_choch

def dt(v): return datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(timezone.utc)

def outcome(candles,i,side,stop,target):
    for j in range(i+1,len(candles)):
        c=candles[j]
        if side=="LONG":
            sl=c.get("bid_low",c["low"])<=stop; tp=c.get("bid_high",c["high"])>=target
        else:
            sl=c.get("ask_high",c["high"])>=stop; tp=c.get("ask_low",c["low"])<=target
        if sl and tp:return "SL",j,stop
        if sl:return "SL",j,stop
        if tp:return "TP",j,target
    px=candles[-1].get("bid_close",candles[-1]["close"]) if side=="LONG" else candles[-1].get("ask_close",candles[-1]["close"])
    return "OPEN",len(candles)-1,px

def run(symbol,start,end,strategy):
    feed=ExnessTickData()
    c5=feed.bars(symbol,start,end,"5M"); c1=feed.bars(symbol,start,end,"1H"); c4=feed.bars(symbol,start,end,"4H")
    if min(len(c5),len(c1),len(c4))==0: raise RuntimeError("No Exness bars loaded")
    fn={"3DUCKS":three_ducks,"BREAK_RETEST":breakout_retest,"SWEEP_CHOCH":sweep_choch}[strategy]
    trades=[]; last_exit=-1
    for i in range(70,len(c5)-1):
        if i<=last_exit: continue
        t=dt(c5[i]["time"])
        h1=[x for x in c1 if dt(x["time"])+timedelta(hours=1)<=t]
        h4=[x for x in c4 if dt(x["time"])+timedelta(hours=4)<=t]
        if len(h1)<70 or len(h4)<61: continue
        setup=fn(h4,h1,c5[:i+1],symbol) if strategy=="3DUCKS" else fn(h1,c5[:i+1],symbol)
        if not setup or setup["rr"]<2: continue
        spread=c5[i].get("spread_avg",0.0)
        entry=setup["entry"]+spread/2 if setup["side"]=="LONG" else setup["entry"]-spread/2
        result,ei,px=outcome(c5,i,setup["side"],setup["stop"],setup["target"])
        risk=abs(entry-setup["stop"])
        r=((px-entry)/risk if setup["side"]=="LONG" else (entry-px)/risk) if risk else 0
        trades.append({"pair":symbol,"strategy":strategy,"time_utc":setup["time"],"side":setup["side"],"entry":entry,"stop":setup["stop"],"target":setup["target"],"outcome":result,"pnl_r":r,"rr":setup["rr"],"spread_avg":spread,"exit_time_utc":c5[ei]["time"]})
        last_exit=ei
    return trades

def metrics(ts):
    rs=[x["pnl_r"] for x in ts]; w=[r for r in rs if r>0]; l=[r for r in rs if r<0]
    eq=peak=dd=0
    for r in rs:
        eq+=r; peak=max(peak,eq); dd=max(dd,peak-eq)
    return {"trades":len(rs),"wins":len(w),"losses":len(l),"win_rate":len(w)/len(rs) if rs else 0,"profit_factor":sum(w)/abs(sum(l)) if l else 0,"expectancy_r":sum(rs)/len(rs) if rs else 0,"avg_r":sum(rs)/len(rs) if rs else 0,"max_drawdown_r":dd,"net_r":sum(rs)}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--symbol",required=True); p.add_argument("--strategy",choices=["3DUCKS","BREAK_RETEST","SWEEP_CHOCH"],required=True); p.add_argument("--start",required=True); p.add_argument("--end",required=True); p.add_argument("--csv",required=True); p.add_argument("--json",required=True); a=p.parse_args()
    ts=run(a.symbol,dt(a.start),dt(a.end),a.strategy); report=metrics(ts)
    with open(a.json,"w") as f: json.dump(report,f,indent=2)
    fields=["pair","strategy","time_utc","side","entry","stop","target","outcome","pnl_r","rr","spread_avg","exit_time_utc"]
    with open(a.csv,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(ts)
    print(json.dumps(report,indent=2))
if __name__=="__main__": main()
