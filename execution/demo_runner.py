"""Run the closed-bar scanner across all configured pairs.

Dry-run is the default.  Set CTRADER_DEMO_EXECUTE=true only after validating
on a cTrader demo account.  Every order is isolated in a fresh child process so
Twisted's reactor is not restarted in one parent process.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from config.settings import load_config, pairs as configured_pairs
from execution.demo_guard import require_demo_execution

load_dotenv()
STATE_PATH = Path(os.getenv("CTRADER_DEMO_STATE", "execution/demo_state.json"))


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"signals": {}}
    data = json.loads(STATE_PATH.read_text())
    return data if isinstance(data, dict) else {"signals": {}}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def _scan(pair: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "execution.bot_main", "--pair", pair],
        check=False, capture_output=True, text=True,
    )
    rows = []
    for line in proc.stdout.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("pair") == pair:
            rows.append(value)
    if proc.returncode or not rows:
        return {"pair": pair, "status": "ERROR", "error": proc.stderr[-1000:]}
    return rows[-1]


def main() -> int:
    cfg = load_config()
    pairs = [p.strip().upper() for p in os.getenv(
        "CTRADER_PAIRS", ",".join(configured_pairs(cfg))
    ).split(",") if p.strip()]
    execute = os.getenv("CTRADER_DEMO_EXECUTE", "false").lower() == "true"
    until_trade = os.getenv("CTRADER_RUN_UNTIL_TRADE", "false").lower() == "true"
    poll_seconds = max(10, int(os.getenv("CTRADER_POLL_SECONDS", "300")))
    if execute:
        require_demo_execution()
        if not os.getenv("CTRADER_ORDER_VOLUME_UNITS"):
            raise RuntimeError("CTRADER_ORDER_VOLUME_UNITS is required for demo execution")
    state = _load_state()
    state.setdefault("signals", {})
    print(json.dumps({"mode": ("DEMO_EXECUTE_UNTIL_TRADE" if execute and until_trade
                                else "DEMO_EXECUTE" if execute else "DRY_RUN"),
                      "pairs": pairs, "poll_seconds": poll_seconds}, sort_keys=True))
    while True:
        for pair in pairs:
            signal = _scan(pair)
            if signal.get("status") != "SIGNAL_ONLY":
                print(json.dumps(signal, sort_keys=True), flush=True)
                continue
            key = f"{pair}:{signal.get('timestamp') or signal.get('signal_close_utc')}"
            if key in state["signals"]:
                print(json.dumps({"pair": pair, "status": "SKIP_DUPLICATE", "key": key}), flush=True)
                continue
            if not execute:
                state["signals"][key] = {"status": "DRY_RUN", "signal": signal}
                _save_state(state)
                print(json.dumps({"pair": pair, "status": "DEMO_SIGNAL_NOT_SUBMITTED",
                                  "signal": signal}, sort_keys=True), flush=True)
                continue
            proc = subprocess.run(
                [sys.executable, "-m", "execution.demo_order"],
                input=json.dumps(signal), text=True, capture_output=True, check=False,
            )
            output = proc.stdout.strip() or proc.stderr.strip()
            print(output or json.dumps({"pair": pair, "status": "ORDER_NO_OUTPUT"}), flush=True)
            if proc.returncode == 0 and "ORDER_ACKNOWLEDGED" in output:
                state["signals"][key] = signal
                _save_state(state)
                if until_trade:
                    return 0
        if not until_trade:
            return 0
        print(json.dumps({"status": "WAITING_FOR_SIGNAL", "sleep_seconds": poll_seconds}), flush=True)
        time.sleep(poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
