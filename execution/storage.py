"""Persistent local storage for bot research and execution events."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from intelligence.hindsight_memory import retain_event


class EventStore:
    def __init__(self, path: str | Path = "results/trading.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at_utc TEXT NOT NULL,
                pair TEXT NOT NULL,
                status TEXT NOT NULL,
                reason_codes_json TEXT NOT NULL,
                result_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS scans_pair_time
                ON scans(pair, recorded_at_utc);
            CREATE TABLE IF NOT EXISTS order_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at_utc TEXT NOT NULL,
                pair TEXT NOT NULL,
                status TEXT NOT NULL,
                return_code INTEGER,
                event_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signal_selections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at_utc TEXT NOT NULL,
                pair TEXT NOT NULL,
                status TEXT NOT NULL,
                selected_variant TEXT,
                selected_signal_id TEXT,
                conflict_json TEXT,
                selection_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS signal_selections_pair_time
                ON signal_selections(pair, recorded_at_utc);
            CREATE TABLE IF NOT EXISTS trade_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at_utc TEXT NOT NULL,
                pair TEXT NOT NULL,
                client_order_id TEXT,
                entry_time_utc TEXT,
                exit_time_utc TEXT,
                side TEXT,
                volume_units REAL,
                entry_price REAL,
                exit_price REAL,
                stop_price REAL,
                target_price REAL,
                pnl REAL,
                pnl_r REAL,
                outcome TEXT,
                outcome_json TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    @staticmethod
    def _memory_event(event_type: str, payload: dict[str, Any]) -> None:
        """Best-effort async handoff; Hindsight never blocks trading."""
        thread = threading.Thread(
            target=retain_event,
            args=(event_type, payload),
            daemon=True,
            name="glitch-hindsight",
        )
        thread.start()

    def record_scan(self, recorded_at_utc: str, pair: str, result: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT INTO scans(recorded_at_utc,pair,status,reason_codes_json,result_json) VALUES(?,?,?,?,?)",
            (recorded_at_utc, pair, result.get("status", "UNKNOWN"),
             json.dumps(result.get("reason_codes", []), sort_keys=True),
             json.dumps(result, sort_keys=True)),
        )
        self.connection.commit()

    def record_order(self, recorded_at_utc: str, pair: str, event: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT INTO order_events(recorded_at_utc,pair,status,return_code,event_json) VALUES(?,?,?,?,?)",
            (recorded_at_utc, pair, event.get("status", "UNKNOWN"),
             event.get("returncode"), json.dumps(event, sort_keys=True)),
        )
        self.connection.commit()
        self._memory_event("ORDER_EVENT", {"recorded_at_utc": recorded_at_utc, "pair": pair, **event})

    def record_selection(self, recorded_at_utc: str, pair: str,
                         selection: dict[str, Any]) -> None:
        selected = selection.get("selected_signal") or {}
        self.connection.execute(
            "INSERT INTO signal_selections("
            "recorded_at_utc,pair,status,selected_variant,selected_signal_id,"
            "conflict_json,selection_json) VALUES(?,?,?,?,?,?,?)",
            (recorded_at_utc, pair, selection.get("status", "UNKNOWN"),
             selected.get("variant"), selection.get("selected_signal_id"),
             json.dumps(selection.get("conflict"), sort_keys=True),
             json.dumps(selection, sort_keys=True)),
        )
        self.connection.commit()
        self._memory_event(
            "SIGNAL_SELECTION",
            {"recorded_at_utc": recorded_at_utc, "pair": pair, **selection},
        )

    def record_outcome(self, recorded_at_utc: str, pair: str,
                       outcome: dict[str, Any]) -> None:
        self.connection.execute(
            """INSERT INTO trade_outcomes(
                recorded_at_utc,pair,client_order_id,entry_time_utc,exit_time_utc,
                side,volume_units,entry_price,exit_price,stop_price,target_price,
                pnl,pnl_r,outcome,outcome_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (recorded_at_utc, pair, outcome.get("client_order_id"),
             outcome.get("entry_time_utc"), outcome.get("exit_time_utc"),
             outcome.get("side"), outcome.get("volume_units"),
             outcome.get("entry_price"), outcome.get("exit_price"),
             outcome.get("stop_price"), outcome.get("target_price"),
             outcome.get("pnl"), outcome.get("pnl_r"), outcome.get("outcome"),
             json.dumps(outcome, sort_keys=True)),
        )
        self.connection.commit()
        self._memory_event(
            "TRADE_OUTCOME",
            {"recorded_at_utc": recorded_at_utc, "pair": pair, **outcome},
        )

    def close(self) -> None:
        self.connection.close()
