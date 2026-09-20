"""Simple, testable Forex strategies used for controlled A/B comparison."""
from __future__ import annotations

def atr(c, n=14):
    if len(c)<n+1:return 0.0
    trs=[]
    for i in range(len(c)-n,len(c)):
        pc=c[i-1]["close"]; h=c[i]["high"]; l=c[i]["low"]
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(trs)/len(trs)

def sma(c,n):
    return sum(x["close"] for x in c[-n:])/n if len(c)>=n else 0.0

def _setup(side, entry, stop, target, name, t):
    risk=(entry-stop) if side=="LONG" else (stop-entry)
    reward=(target-entry) if side=="LONG" else (entry-target)
    if risk<=0 or reward<=0:return None
    return {"side":side,"entry":entry,"stop":stop,"target":target,"rr":reward/risk,"strategy":name,"time":t}

def three_ducks(c4,c1,c5,pair):
    if len(c4)<61 or len(c1)<61 or len(c5)<65:return None
    a4=sma(c4,60); a1=sma(c1,60); a5=sma(c5,60)
    p5=c5[-1]["close"]; prev=c5[-2]["close"]; a5prev=sma(c5[:-1],60); a=atr(c5)
    if not a:return None
    if c4[-1]["close"]>a4 and c1[-1]["close"]>a1 and prev<=a5prev and p5>a5:
        s=min(x["low"] for x in c5[-6:])-0.10*a
        return _setup("LONG",p5,s,p5+2*(p5-s),"3DUCKS",c5[-1]["time"])
    if c4[-1]["close"]<a4 and c1[-1]["close"]<a1 and prev>=a5prev and p5<a5:
        s=max(x["high"] for x in c5[-6:])+0.10*a
        return _setup("SHORT",p5,s,p5-2*(s-p5),"3DUCKS",c5[-1]["time"])
    return None

def breakout_retest(c1,c5,pair):
    if len(c1)<25 or len(c5)<30:return None
    a=atr(c5)
    if not a:return None
    prior=c1[-21:-1]; hi=max(x["high"] for x in prior); lo=min(x["low"] for x in prior); last=c1[-1]
    if last["close"]>hi:
        recent=c5[-6:]
        if min(x["low"] for x in recent)<=hi and recent[-1]["close"]>hi:
            e=recent[-1]["close"]; s=min(x["low"] for x in recent)-0.10*a
            return _setup("LONG",e,s,e+2*(e-s),"BREAK_RETEST",recent[-1]["time"])
    if last["close"]<lo:
        recent=c5[-6:]
        if max(x["high"] for x in recent)>=lo and recent[-1]["close"]<lo:
            e=recent[-1]["close"]; s=max(x["high"] for x in recent)+0.10*a
            return _setup("SHORT",e,s,e-2*(s-e),"BREAK_RETEST",recent[-1]["time"])
    return None

def sweep_choch(c1,c5,pair):
    if len(c1)<15 or len(c5)<30:return None
    a=atr(c5)
    if not a:return None
    ref=c1[-7:-1]; last=c1[-1]; hi=max(x["high"] for x in ref); lo=min(x["low"] for x in ref)
    if last["low"]<lo and last["close"]>lo:
        sw=max(x["high"] for x in c5[-8:-1])
        if c5[-1]["close"]>sw:
            e=c5[-1]["close"]; s=last["low"]-0.10*a
            return _setup("LONG",e,s,e+2*(e-s),"SWEEP_CHOCH",c5[-1]["time"])
    if last["high"]>hi and last["close"]<hi:
        sw=min(x["low"] for x in c5[-8:-1])
        if c5[-1]["close"]<sw:
            e=c5[-1]["close"]; s=last["high"]+0.10*a
            return _setup("SHORT",e,s,e-2*(s-e),"SWEEP_CHOCH",c5[-1]["time"])
    return None
