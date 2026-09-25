"""Submit exactly one protected market order to cTrader demo.

Input is one JSON signal on stdin.  This process refuses live environments,
requires the explicit demo gate, and exits after the broker acknowledgement.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

from ctrader_open_api import Protobuf
from twisted.internet import reactor

from data.ctrader import CTraderData
from execution.demo_guard import require_demo_execution


def main() -> int:
    require_demo_execution()
    if os.getenv("CTRADER_ENV", "demo").strip().lower() != "demo":
        raise RuntimeError("demo_order refuses non-demo environments")
    signal = json.load(sys.stdin)
    pair = str(signal["pair"]).upper()
    side = str(signal["side"]).upper()
    if side not in {"LONG", "SHORT", "BUY", "SELL"}:
        raise ValueError("signal side must be LONG or SHORT")
    stop = float(signal["stop_price"])
    target_value = signal.get("target_price")
    if target_value is None:
        target_value = signal["tp_target"]
    target = float(target_value)
    entry = float(signal["entry_price"])
    stop_distance = abs(entry - stop)
    target_distance = abs(target - entry)
    if stop_distance <= 0 or target_distance <= 0:
        raise ValueError("signal must have positive SL and TP distances")
    volume = float(os.environ["CTRADER_ORDER_VOLUME_UNITS"])
    cap = float(os.environ["CTRADER_MAX_ORDER_VOLUME_UNITS"])
    if volume <= 0 or volume > cap:
        raise ValueError("CTRADER_ORDER_VOLUME_UNITS must be positive and <= cap")

    feed = CTraderData()
    result = {"pair": pair, "status": "CONNECTING"}
    client_order_id = f"CRT-{pair}-{uuid.uuid4().hex[:16]}"

    def submit(_symbols):
        symbol_id = feed.symbol_id(pair)
        deferred = feed.submit_market_order(
            symbol_id,
            side,
            volume,
            relative_stop_loss=stop_distance,
            relative_take_profit=target_distance,
            client_order_id=client_order_id,
            label="CRT-DEMO",
            comment=f"CRT {signal.get('timestamp', '')}",
        )
        def acknowledged(message):
            result.update({"pair": pair, "status": "ORDER_ACKNOWLEDGED",
                           "client_order_id": client_order_id,
                           "response": str(Protobuf.extract(message))})
            print(json.dumps(result, sort_keys=True))
            if reactor.running:
                reactor.stop()
            return message
        deferred.addCallback(acknowledged)

    feed.on_account_ready = lambda: feed.request_symbols(submit)
    feed.connect()
    reactor.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
