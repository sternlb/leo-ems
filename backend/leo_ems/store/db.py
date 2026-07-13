"""SQLite-Persistenz: Regeln, Entscheidungs-Log, Kennzahlen (ADR-002, REQ-062/070/073).

Eine Datei im Add-on-Datenverzeichnis (/data/leo_ems.db). Regeln werden sofort
persistiert und überstehen einen Neustart (Abnahmetest T6).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, time
from pathlib import Path

from ..planner.rules import ChargingRule

SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    weekdays TEXT NOT NULL,          -- JSON-Liste, 0=Mo … 6=So
    departure TEXT NOT NULL,         -- "HH:MM"
    soc_min INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS decision_log (
    ts TEXT NOT NULL,
    regel TEXT NOT NULL,             -- Trigger/Regel (REQ-062)
    inputs TEXT NOT NULL,            -- Eingangswerte als JSON
    befehl TEXT NOT NULL,
    ergebnis TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_log_ts ON decision_log(ts);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(SCHEMA)

    # --- Regeln (REQ-070) ---------------------------------------------------
    def list_rules(self) -> list[ChargingRule]:
        rows = self._db.execute("SELECT id, weekdays, departure, soc_min, active FROM rules").fetchall()
        return [
            ChargingRule(
                rule_id=r[0],
                weekdays=frozenset(json.loads(r[1])),
                departure=time.fromisoformat(r[2]),
                soc_min_pct=r[3],
                active=bool(r[4]),
            )
            for r in rows
        ]

    def add_rule(self, rule: ChargingRule) -> int:
        cur = self._db.execute(
            "INSERT INTO rules (weekdays, departure, soc_min, active) VALUES (?, ?, ?, ?)",
            (json.dumps(sorted(rule.weekdays)), rule.departure.isoformat("minutes"), rule.soc_min_pct, int(rule.active)),
        )
        self._db.commit()
        return cur.lastrowid

    def update_rule(self, rule_id: int, rule: ChargingRule) -> bool:
        cur = self._db.execute(
            "UPDATE rules SET weekdays=?, departure=?, soc_min=?, active=? WHERE id=?",
            (json.dumps(sorted(rule.weekdays)), rule.departure.isoformat("minutes"), rule.soc_min_pct, int(rule.active), rule_id),
        )
        self._db.commit()
        return cur.rowcount > 0

    def delete_rule(self, rule_id: int) -> bool:
        cur = self._db.execute("DELETE FROM rules WHERE id=?", (rule_id,))
        self._db.commit()
        return cur.rowcount > 0

    # --- Entscheidungs-Log (REQ-062) -----------------------------------------
    def log_decision(self, ts: datetime, regel: str, inputs: dict, befehl: str, ergebnis: str) -> None:
        self._db.execute(
            "INSERT INTO decision_log (ts, regel, inputs, befehl, ergebnis) VALUES (?, ?, ?, ?, ?)",
            (ts.isoformat(), regel, json.dumps(inputs, ensure_ascii=False), befehl, ergebnis),
        )
        self._db.commit()

    def recent_decisions(self, limit: int = 200) -> list[dict]:
        rows = self._db.execute(
            "SELECT ts, regel, inputs, befehl, ergebnis FROM decision_log ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {"ts": r[0], "regel": r[1], "inputs": json.loads(r[2]), "befehl": r[3], "ergebnis": r[4]}
            for r in rows
        ]
