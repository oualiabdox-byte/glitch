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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from config.settings import load_config, pairs as configured_pairs
from execution.demo_guard import require_demo_execution
from execution.storage import EventStore

load_dotenv()
STATE_PATH = Path(os.getenv("CTRADER_DEMO_STATE", "execution/demo_state.json"))
DIAGNOSTICS_PATH = Path(os.getenv(
    "CTRADER_DIAGNOSTICS_PATH", "results/demo_diagnostics.jsonl"
))
DATABASE_PATH = os.getenv("CTRADER_DATABASE_PATH", "results/trading.db")
STORAGE_LIMIT_BYTES = int(float(os.getenv("CTRADER_STORAGE_LIMIT_MB", "550")) * 1024 * 1024)
TRANSIENT_SCAN_REASONS = {
    "INSUFFICIENT_CLOSED_DATA", "ABNORMAL_VOLATILITY", "NEWS_BLACKOUT",
    "STALE_H1_DATA", "STALE_M5_DATA",
}


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"signals": {}, "setups": {}}
    data = json.loads(STATE_PATH.read_text())
    if not isinstance(data, dict):
        return {"signals": {}, "setups": {}}
    if not isinstance(data.get("signals"), dict):
        data["signals"] = {}
    if not isinstance(data.get("setups"), dict):
        data["setups"] = {}
    now = datetime.now(timezone.utc)
    for key, value in list(data["signals"].items()):
        signal = value.get("signal", value) if isinstance(value, dict) else {}
        timestamp = signal.get("signal_close_utc") or signal.get("timestamp")
        try:
            created = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            del data["signals"][key]
            continue
        if now - created > timedelta(days=7):
            del data["signals"][key]
    for pair, setup in list(data["setups"].items()):
        if not isinstance(setup, dict):
            del data["setups"][pair]
            continue
        timestamp = setup.get("terminal_at") if setup.get("status") in {
            "EXPIRED", "INVALIDATED", "TARGET_REACHED", "TARGET_INVALID",
        } else setup.get("updated_at")
        try:
            updated = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            del data["setups"][pair]
            continue
        retention = timedelta(hours=24) if setup.get("status") in {
            "EXPIRED", "INVALIDATED", "TARGET_REACHED", "TARGET_INVALID",
        } else timedelta(days=7)
        if now - updated > retention:
            del data["setups"][pair]
    return data


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_name(STATE_PATH.name + ".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    temporary.replace(STATE_PATH)


def _preserve_setup_on_scan_result(signal: dict) -> bool:
    """Transient feed/safety failures do not invalidate an existing H1 premise."""
    return (signal.get("status") == "ERROR"
            or (signal.get("status") == "NO_TRADE"
                and bool(set(signal.get("reason_codes", [])) & TRANSIENT_SCAN_REASONS)))


def _record(event: dict, store: EventStore) -> None:
    recorded_at = datetime.now(timezone.utc).isoformat()
    row = {"recorded_at_utc": recorded_at, **event}
    encoded = (json.dumps(row, sort_keys=True) + "\n").encode()
    current_bytes = sum(
        path.stat().st_size for path in DIAGNOSTICS_PATH.parent.glob("*")
        if path.is_file()
    )
    if current_bytes + len(encoded) >= STORAGE_LIMIT_BYTES:
        print(json.dumps({"status": "STORAGE_QUOTA_REACHED",
                          "limit_mb": STORAGE_LIMIT_BYTES / 1024 / 1024,
                          "path": str(DIAGNOSTICS_PATH.parent)}, sort_keys=True),
              flush=True)
        return
    DIAGNOSTICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DIAGNOSTICS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    if event.get("event") == "scan":
        store.record_scan(recorded_at, event["pair"], event["result"])
    elif event.get("event") == "order_attempt":
        store.record_order(recorded_at, event["pair"], event)


def _scan(pair: str, setup_state: dict | None = None) -> dict:
    env = os.environ.copy()
    if setup_state:
        env["CTRADER_SETUP_STATE_JSON"] = json.dumps(setup_state, sort_keys=True)
    else:
        env.pop("CTRADER_SETUP_STATE_JSON", None)
    proc = subprocess.run(
        [sys.executable, "-m", "execution.bot_main", "--pair", pair],
        check=False, capture_output=True, text=True, env=env,
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
    store = EventStore(DATABASE_PATH)
    print(json.dumps({"mode": ("DEMO_EXECUTE_UNTIL_TRADE" if execute and until_trade
                                else "DEMO_EXECUTE" if execute else "DRY_RUN"),
                      "pairs": pairs, "poll_seconds": poll_seconds}, sort_keys=True))
    while True:
        for pair in pairs:
            prior_setup = state["setups"].get(pair)
            signal = _scan(pair, setup_state=prior_setup)
            _record({"event": "scan", "pair": pair, "result": signal}, store)
            next_setup = signal.get("setup_state")
            if next_setup:
                if next_setup.get("status") in {"EXPIRED", "INVALIDATED", "TARGET_REACHED", "TARGET_INVALID"}:
                    next_setup["terminal_at"] = datetime.now(timezone.utc).isoformat()
                state["setups"][pair] = next_setup
                _save_state(state)
            elif not _preserve_setup_on_scan_result(signal):
                state["setups"].pop(pair, None)
                _save_state(state)
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
            _record({"event": "order_attempt", "pair": pair,
                     "signal": signal, "returncode": proc.returncode,
                     "output": output}, store)
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
