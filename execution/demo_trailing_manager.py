#!/usr/bin/env python3
"""Demo-only manager for the validated +1.5R -> +0.75R stop ratchet."""
from __future__ import annotations
import json, os
from pathlib import Path
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOATradeSide
from twisted.internet import reactor
from data.ctrader import CTraderData
from execution.demo_guard import require_demo_execution

STATE=Path(os.getenv('CTRADER_DEMO_STATE','execution/demo_state.json'))

def price(value, digits):
    value=float(value or 0)
    return value/(10**digits) if abs(value)>100 else value

def main():
    require_demo_execution()
    if os.getenv('CTRADER_DYNAMIC_STOP_MODE','TRAIL_1_5R') != 'TRAIL_1_5R':
        raise RuntimeError('demo trailing manager supports only TRAIL_1_5R')
    state=json.loads(STATE.read_text()) if STATE.exists() else {'signals':{}}
    signals=[]
    for value in state.get('signals',{}).values():
        if isinstance(value,dict) and isinstance(value.get('signal'),dict): signals.append(value['signal'])
    by_pair={str(s.get('pair','')).upper():s for s in signals}
    feed=CTraderData()
    positions={}; spots={}
    def refresh():
        try: feed.request_account_state()
        finally: reactor.callLater(15, refresh)
    def on_symbols(symbols):
        for pair in by_pair:
            try: feed.subscribe_spots(feed.symbol_id(pair))
            except Exception as exc: print(json.dumps({'event':'trailing_symbol_error','pair':pair,'error':str(exc)}),flush=True)
    def amend(position,pair,spot):
        signal=by_pair.get(pair)
        if not signal: return
        td=position.tradeData; side=int(td.tradeSide)
        is_long=side==ProtoOATradeSide.Value('BUY')
        entry=float(position.price)
        initial=float(signal.get('stop_price',0))
        risk=abs(entry-initial)
        if risk<=0: return
        digits=feed.symbol_info(pair).digits
        current=price(spot.bid if is_long else spot.ask,digits)
        favorable=(current-entry) if is_long else (entry-current)
        if favorable < 1.5*risk: return
        desired=entry+(0.75*risk if is_long else -0.75*risk)
        current_stop=price(position.stopLoss,digits)
        improve=(is_long and (current_stop<=0 or desired>current_stop)) or ((not is_long) and (current_stop<=0 or desired<current_stop))
        if not improve: return
        take=price(position.takeProfit,digits)
        feed.amend_position_protection(int(position.positionId),stop_loss=desired,take_profit=take if take>0 else None)
        print(json.dumps({'event':'trailing_amend','pair':pair,'position_id':int(position.positionId),'entry':entry,'current':current,'old_stop':current_stop,'new_stop':desired,'target':take},sort_keys=True),flush=True)
    def on_reconcile(items,_orders):
        positions.clear()
        for position in items:
            pair=next((str(name).upper() for name,symbol in feed.symbols.items() if int(getattr(symbol,'symbolId',-1))==int(position.tradeData.symbolId)),None)
            if pair: positions[pair]=position
        for pair,position in positions.items():
            if pair in spots: amend(position,pair,spots[pair])
    def on_spot(spot):
        symbol_id=int(spot.symbolId); spots[symbol_id]=spot
        for pair,position in positions.items():
            if int(position.tradeData.symbolId)==symbol_id: amend(position,pair,spot)
    feed.on_reconcile=on_reconcile; feed.on_spot=on_spot
    feed.on_account_ready=lambda: feed.request_symbols(on_symbols)
    feed.connect(); reactor.callLater(15,refresh); reactor.run(); return 0
if __name__=='__main__': raise SystemExit(main())
