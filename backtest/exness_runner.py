"""ICT backtest using Exness public historical tick data. No MT5/login."""
import argparse,csv,json
from datetime import datetime,timezone
from data.exness_ticks import ExnessTickData
from strategy.ict_strategy import evaluate_ict_2022
def dt(v): return datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(timezone.utc)
def session_for(t):
 h=t.hour
 return "london" if 7<=h<12 else "overlap" if 12<=h<13 else "new_york" if 13<=h<17 else "other"
def outcome(candles,i,side,stop,target):
 for j in range(i+1,len(candles)):
  c=candles[j]; sl=c["low"]<=stop if side=="LONG" else c["high"]>=stop; tp=c["high"]>=target if side=="LONG" else c["low"]<=target
  if sl: return "SL",j,stop
  if tp: return "TP",j,target
 return "OPEN",len(candles)-1,candles[-1]["close"]
def run(symbol,start,end,cache_dir="data/exness_cache"):
 feed=ExnessTickData(cache_dir); h1=feed.bars(symbol,start,end,"1H"); h4=feed.bars(symbol,start,end,"4H")
 if len(h1)<100 or len(h4)<40: raise RuntimeError(f"Not enough Exness data: H1={len(h1)}, H4={len(h4)}")
 trades=[]; last_exit=-1
 for i in range(60,len(h1)-1):
  if i<=last_exit: continue
  t=dt(h1[i]["time"]); s=session_for(t)
  if s not in ("london","new_york","overlap"): continue
  h4c=[c for c in h4 if dt(c["time"])<=t]
  if len(h4c)<30: continue
  setup=evaluate_ict_2022(h1[:i+1],h4c,symbol,session_context=s)
  if not setup: continue
  entry,stop,target=setup["entry_mid"],setup["stop_price"],setup["tp_target"]; result,ei,px=outcome(h1,i,setup["side"],stop,target); risk=abs(entry-stop)
  r=((px-entry)/risk if setup["side"]=="LONG" else (entry-px)/risk) if risk else 0
  trades.append({"pair":symbol,"time_utc":h1[i]["time"],"side":setup["side"],"entry":entry,"stop":stop,"tp1":target,"tp2":target,"outcome":result,"pnl_r":r,"rr":setup["rr"],"spread_avg":h1[i].get("spread_avg",0),"exit_time_utc":h1[ei]["time"]}); last_exit=ei
 return trades
def metrics(trades):
 if not trades: return {"trades":0,"wins":0,"losses":0,"win_rate":0,"profit_factor":0,"expectancy_r":0,"max_drawdown_r":0}
 rs=[t["pnl_r"] for t in trades]; w=[r for r in rs if r>0]; l=[r for r in rs if r<0]; eq=peak=dd=0
 for r in rs: eq+=r; peak=max(peak,eq); dd=max(dd,peak-eq)
 return {"trades":len(rs),"wins":len(w),"losses":len(l),"win_rate":len(w)/len(rs),"profit_factor":sum(w)/abs(sum(l)) if l else float("inf"),"expectancy_r":sum(rs)/len(rs),"max_drawdown_r":dd}
def main():
 p=argparse.ArgumentParser(); p.add_argument("--symbol",default="EURUSD"); p.add_argument("--start",required=True); p.add_argument("--end",required=True); p.add_argument("--csv"); p.add_argument("--json"); a=p.parse_args()
 trades=run(a.symbol,dt(a.start),dt(a.end)); report=metrics(trades)
 if a.csv:
  fields=list(trades[0]) if trades else ["pair","time_utc","side","entry","stop","tp1","tp2","outcome","pnl_r","rr","spread_avg","exit_time_utc"]
  with open(a.csv,"w",newline="") as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(trades)
 if a.json:
  with open(a.json,"w") as f: json.dump(report,f,indent=2)
 print(json.dumps(report,indent=2))
if __name__=="__main__": main()
