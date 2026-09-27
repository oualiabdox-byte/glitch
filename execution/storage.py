"""SQLite persistence for research, OMS state, raw broker events, and audit records."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


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
            CREATE INDEX IF NOT EXISTS scans_pair_time ON scans(pair, recorded_at_utc);
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
            CREATE TABLE IF NOT EXISTS oms_orders (
                internal_order_id TEXT PRIMARY KEY,
                account_id INTEGER,
                client_order_id TEXT NOT NULL,
                broker_order_id INTEGER,
                position_id INTEGER,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                requested_volume REAL NOT NULL,
                executed_volume REAL NOT NULL DEFAULT 0,
                remaining_volume REAL,
                execution_price REAL,
                state TEXT NOT NULL,
                reason TEXT,
                error_code TEXT,
                error_description TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS oms_orders_account_state
                ON oms_orders(account_id, state);
            CREATE TABLE IF NOT EXISTS broker_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                account_id INTEGER,
                internal_order_id TEXT,
                broker_order_id INTEGER,
                deal_id INTEGER,
                position_id INTEGER,
                execution_type TEXT,
                resulting_state TEXT,
                recorded_at_utc TEXT NOT NULL,
                raw_payload_hex TEXT,
                raw_event_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reconciliation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                recorded_at_utc TEXT NOT NULL,
                status TEXT NOT NULL,
                details_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS execution_halts (
                account_id INTEGER PRIMARY KEY,
                halted INTEGER NOT NULL,
                reason TEXT NOT NULL,
                set_at_utc TEXT NOT NULL,
                cleared_at_utc TEXT
            );
            """
        )
        self.connection.commit()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, default=str)

    def record_scan(self, recorded_at_utc: str, pair: str, result: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT INTO scans(recorded_at_utc,pair,status,reason_codes_json,result_json) VALUES(?,?,?,?,?)",
            (recorded_at_utc, pair, result.get("status", "UNKNOWN"),
             self._json(result.get("reason_codes", [])), self._json(result)),
        )
        self.connection.commit()

    def record_order(self, recorded_at_utc: str, pair: str, event: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT INTO order_events(recorded_at_utc,pair,status,return_code,event_json) VALUES(?,?,?,?,?)",
            (recorded_at_utc, pair, event.get("status", "UNKNOWN"),
             event.get("returncode"), self._json(event)),
        )
        self.connection.commit()

    def record_selection(self, recorded_at_utc: str, pair: str, selection: dict[str, Any]) -> None:
        selected = selection.get("selected_signal") or {}
        self.connection.execute(
            "INSERT INTO signal_selections(recorded_at_utc,pair,status,selected_variant,selected_signal_id,conflict_json,selection_json) VALUES(?,?,?,?,?,?,?)",
            (recorded_at_utc, pair, selection.get("status", "UNKNOWN"),
             selected.get("variant"), selection.get("selected_signal_id"),
             self._json(selection.get("conflict")), self._json(selection)),
        )
        self.connection.commit()

    def record_outcome(self, recorded_at_utc: str, pair: str, outcome: dict[str, Any]) -> None:
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
             self._json(outcome)),
        )
        self.connection.commit()

    def record_order_intent(self, recorded_at_utc: str, intent: dict[str, Any], state: str = "NEW") -> None:
        self.connection.execute(
            """INSERT INTO oms_orders(
                internal_order_id,account_id,client_order_id,symbol,side,requested_volume,
                remaining_volume,state,created_at_utc,updated_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (intent["internal_order_id"], intent.get("account_id"), intent["client_order_id"],
             intent["symbol"], intent["side"], intent["requested_volume"],
             intent["requested_volume"], state, recorded_at_utc, recorded_at_utc),
        )
        self.connection.commit()

    def record_order_state(self, recorded_at_utc: str, internal_order_id: str, state: str,
                           *, broker_order_id: int | None = None, position_id: int | None = None,
                           executed_volume: float | None = None, remaining_volume: float | None = None,
                           execution_price: float | None = None, reason: str | None = None,
                           error_code: str | None = None, error_description: str | None = None) -> None:
        self.connection.execute(
            """UPDATE oms_orders SET state=?,broker_order_id=COALESCE(?,broker_order_id),
                position_id=COALESCE(?,position_id),executed_volume=COALESCE(?,executed_volume),
                remaining_volume=COALESCE(?,remaining_volume),execution_price=COALESCE(?,execution_price),
                reason=COALESCE(?,reason),error_code=COALESCE(?,error_code),
                error_description=COALESCE(?,error_description),updated_at_utc=?
                WHERE internal_order_id=?""",
            (state, broker_order_id, position_id, executed_volume, remaining_volume,
             execution_price, reason, error_code, error_description,
             recorded_at_utc, internal_order_id),
        )
        self.connection.commit()

    def record_broker_event(self, recorded_at_utc: str, event: dict[str, Any],
                            resulting_state: str | None = None) -> bool:
        try:
            self.connection.execute(
                """INSERT INTO broker_events(
                    event_id,account_id,internal_order_id,broker_order_id,deal_id,position_id,
                    execution_type,resulting_state,recorded_at_utc,raw_payload_hex,raw_event_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (event["event_id"], event.get("account_id"), event.get("internal_order_id"),
                 event.get("broker_order_id"), event.get("deal_id"), event.get("position_id"),
                 event.get("execution_type"), resulting_state, recorded_at_utc,
                 event.get("raw_payload_hex"), self._json(event.get("raw_event", event))),
            )
        except sqlite3.IntegrityError:
            self.connection.rollback()
            return False
        self.connection.commit()
        return True

    def record_reconciliation(self, recorded_at_utc: str, account_id: int, result: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT INTO reconciliation_runs(account_id,recorded_at_utc,status,details_json) VALUES(?,?,?,?)",
            (account_id, recorded_at_utc, result.get("status", "UNKNOWN"), self._json(result)),
        )
        self.connection.commit()

    def set_execution_halt(self, account_id: int, recorded_at_utc: str, reason: str) -> None:
        self.connection.execute(
            """INSERT INTO execution_halts(account_id,halted,reason,set_at_utc)
               VALUES(?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET
               halted=1,reason=excluded.reason,set_at_utc=excluded.set_at_utc,cleared_at_utc=NULL""",
            (account_id, 1, reason, recorded_at_utc),
        )
        self.connection.commit()

    def clear_execution_halt(self, account_id: int, recorded_at_utc: str) -> None:
        self.connection.execute(
            "UPDATE execution_halts SET halted=0,cleared_at_utc=? WHERE account_id=?",
            (recorded_at_utc, account_id),
        )
        self.connection.commit()

    def is_execution_halted(self, account_id: int) -> bool:
        row = self.connection.execute(
            "SELECT halted FROM execution_halts WHERE account_id=?", (account_id,)
        ).fetchone()
        return bool(row and row["halted"])

    def active_oms_orders(self, account_id: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM oms_orders WHERE state NOT IN ('FILLED','CANCELLED','REJECTED','EXPIRED','FAILED')"
        params: tuple[Any, ...] = ()
        if account_id is not None:
            query += " AND account_id=?"
            params = (account_id,)
        return [dict(row) for row in self.connection.execute(query, params).fetchall()]

    def close(self) -> None:
        self.connection.close()
