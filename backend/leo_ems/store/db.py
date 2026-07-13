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
CREATE TABLE IF NOT EXISTS snapshots (       -- je Regel-Tick ein Messbild (Cockpit/REQ-052)
    ts TEXT NOT NULL,
    ueberschuss_w REAL, p_netz_w REAL, p_batterie_w REAL,
    soc_batt REAL, soc_v REAL,
    p_wallbox_w REAL,                        -- real gemessene Wallbox-Leistung (= EVCC im Beobachtungsmodus)
    p_sungrow_w REAL,
    wuerde_laden INTEGER, strom_a INTEGER, phasen INTEGER,  -- EMS-Entscheidung (im read_only: "hätte")
    garantie INTEGER, read_only INTEGER
);
CREATE INDEX IF NOT EXISTS idx_snap_ts ON snapshots(ts);
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

    # --- Snapshots / Beobachtungs-Auswertung (Cockpit) -------------------------
    def log_snapshot(self, ts: datetime, **felder) -> None:
        spalten = ("ueberschuss_w", "p_netz_w", "p_batterie_w", "soc_batt", "soc_v",
                   "p_wallbox_w", "p_sungrow_w", "wuerde_laden", "strom_a", "phasen",
                   "garantie", "read_only")
        werte = [ts.isoformat()] + [
            int(felder.get(s) or 0) if s in ("wuerde_laden", "garantie", "read_only", "strom_a", "phasen")
            else felder.get(s)
            for s in spalten
        ]
        self._db.execute(
            f"INSERT INTO snapshots (ts, {', '.join(spalten)}) VALUES ({', '.join('?' * 13)})", werte
        )
        self._db.commit()

    def snapshots_recent(self, limit: int = 1000) -> list[dict]:
        cur = self._db.execute("SELECT * FROM snapshots ORDER BY ts DESC LIMIT ?", (limit,))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()][::-1]  # chronologisch

    def observation_summary(self, interval_s: int = 10) -> dict:
        """Aggregierte Auswertung für das Cockpit (EMS-Entscheidung vs. real gemessen)."""
        basis = self._db.execute(
            "SELECT COUNT(*), MIN(ts), MAX(ts), AVG(ueberschuss_w), MAX(ueberschuss_w) FROM snapshots"
        ).fetchone()
        if not basis[0]:
            return {"snapshots": 0, "hinweis": "Noch keine Beobachtungsdaten"}
        energie = self._db.execute(
            "SELECT SUM(wuerde_laden),"
            " SUM(CASE WHEN wuerde_laden=1 THEN strom_a*phasen*230.0 ELSE 0 END),"
            " SUM(p_wallbox_w), SUM(garantie) FROM snapshots"
        ).fetchone()
        faktor_wh = interval_s / 3600.0
        taeglich = self._db.execute(
            "SELECT substr(ts,1,10) AS tag, COUNT(*),"
            " ROUND(SUM(CASE WHEN wuerde_laden=1 THEN strom_a*phasen*230.0 ELSE 0 END)*?, 1),"
            " ROUND(SUM(p_wallbox_w)*?, 1), ROUND(MAX(ueberschuss_w)),"
            " ROUND(AVG(soc_batt), 1)"
            " FROM snapshots GROUP BY tag ORDER BY tag", (faktor_wh, faktor_wh)
        ).fetchall()
        return {
            "snapshots": basis[0],
            "von": basis[1], "bis": basis[2],
            "ueberschuss_avg_w": round(basis[3] or 0),
            "ueberschuss_max_w": round(basis[4] or 0),
            "ems_haette_geladen_wh": round((energie[1] or 0) * faktor_wh, 1),
            "real_wallbox_wh": round((energie[2] or 0) * faktor_wh, 1),
            "ticks_laden": energie[0] or 0,
            "ticks_garantie": energie[3] or 0,
            "taeglich": [
                {"tag": t[0], "ticks": t[1], "ems_wh": t[2], "real_wh": t[3],
                 "max_ueberschuss_w": t[4], "soc_batt_avg": t[5]}
                for t in taeglich
            ],
        }

    def recent_decisions(self, limit: int = 200) -> list[dict]:
        rows = self._db.execute(
            "SELECT ts, regel, inputs, befehl, ergebnis FROM decision_log ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {"ts": r[0], "regel": r[1], "inputs": json.loads(r[2]), "befehl": r[3], "ergebnis": r[4]}
            for r in rows
        ]
