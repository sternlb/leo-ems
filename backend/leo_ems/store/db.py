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
    garantie INTEGER, read_only INTEGER,
    entladelimit_w REAL,                     -- Entladegrenze Hausbatterie; NULL = keine (Spec §5.1)
    wp_ww_boost INTEGER,                     -- lief in diesem Tick ein Warmwasser-Boost? (Issue #14)
    wp_hk_boost INTEGER                      -- lief eine Heizkreis-Anhebung?
);
CREATE INDEX IF NOT EXISTS idx_snap_ts ON snapshots(ts);
CREATE TABLE IF NOT EXISTS energie_tag (   -- Tagesbilanz je Kanal in Wh (Issue #13)
    tag TEXT PRIMARY KEY,                  -- YYYY-MM-DD, Ortszeit
    pv_haus_wh REAL NOT NULL DEFAULT 0,
    pv_garage_wh REAL NOT NULL DEFAULT 0,
    netz_bezug_wh REAL NOT NULL DEFAULT 0,
    netz_einspeisung_wh REAL NOT NULL DEFAULT 0,
    batt_laden_wh REAL NOT NULL DEFAULT 0,
    batt_entladen_wh REAL NOT NULL DEFAULT 0,
    haus_wh REAL NOT NULL DEFAULT 0,       -- Hausverbrauch OHNE Wallbox
    wallbox_wh REAL NOT NULL DEFAULT 0,
    quelle TEXT NOT NULL,                  -- 'ems' | 'e3dc' | 'e3dc-ohne-garage'
    aktualisiert TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS energie_stunde ( -- Stundenbilanz je Kanal in Wh (v0.15)
    stunde TEXT PRIMARY KEY,               -- 'YYYY-MM-DD HH', Ortszeit
    pv_haus_wh REAL NOT NULL DEFAULT 0,
    pv_garage_wh REAL NOT NULL DEFAULT 0,
    netz_bezug_wh REAL NOT NULL DEFAULT 0,
    netz_einspeisung_wh REAL NOT NULL DEFAULT 0,
    batt_laden_wh REAL NOT NULL DEFAULT 0,
    batt_entladen_wh REAL NOT NULL DEFAULT 0,
    haus_wh REAL NOT NULL DEFAULT 0,       -- Hausverbrauch OHNE Wallbox
    wallbox_wh REAL NOT NULL DEFAULT 0,
    aktualisiert TEXT NOT NULL
);
"""

# Spalten, die nach der ersten Auslieferung dazugekommen sind. CREATE TABLE
# IF NOT EXISTS lässt eine bestehende Tabelle unangetastet — für Leos laufende
# Datenbank auf dem Pi muss deshalb nachträglich erweitert werden.
NACHRUESTUNG = (
    ("snapshots", "entladelimit_w", "REAL"),
    ("snapshots", "wp_ww_boost", "INTEGER"),
    ("snapshots", "wp_hk_boost", "INTEGER"),
)


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        for tabelle, spalte, typ in NACHRUESTUNG:
            try:
                self._db.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {typ}")
            except sqlite3.OperationalError:
                pass    # gibt es schon — neue Datenbank oder bereits nachgerüstet
        self._db.commit()

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
                   "garantie", "read_only", "entladelimit_w", "wp_ww_boost", "wp_hk_boost")
        ganzzahlig = ("wuerde_laden", "garantie", "read_only", "strom_a", "phasen",
                      "wp_ww_boost", "wp_hk_boost")
        werte = [ts.isoformat()] + [
            int(felder.get(s) or 0) if s in ganzzahlig else felder.get(s)
            for s in spalten
        ]
        self._db.execute(
            f"INSERT INTO snapshots (ts, {', '.join(spalten)})"
            f" VALUES ({', '.join('?' * (len(spalten) + 1))})", werte
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

    # --- Energie-Tagesbilanz (Issue #13) -------------------------------------
    # Die Tabelle ist das Gedächtnis für Monats- und Jahresauswertungen. Sie
    # hält **Tageswerte**, keine Ticks: Ticks liegen schon in `snapshots` und
    # werden dort nach Tagen gelöscht; die Jahresübersicht muss aber auch in
    # fünf Jahren noch da sein. Ein Tag ist die kleinste Einheit, in der Leo
    # laut Issue #13 auswerten will, und ~365 Zeilen/Jahr bleiben winzig.

    ENERGIE_KANAELE = (
        "pv_haus_wh", "pv_garage_wh", "netz_bezug_wh", "netz_einspeisung_wh",
        "batt_laden_wh", "batt_entladen_wh", "haus_wh", "wallbox_wh",
    )

    def energie_tag_schreiben(self, tag: str, werte: dict, quelle: str,
                              jetzt: datetime | None = None) -> None:
        """Eine Tageszeile setzen (UPSERT, absolute Werte).

        Absolut statt inkrementell, weil der Zähler seinen Tagesstand ohnehin im
        Speicher führt: Ein verpasster oder doppelter Schreibvorgang verfälscht
        so nichts, während `SET x = x + ?` bei jedem Wiederholungslauf addieren
        würde. Der Preis ist, dass der Aufrufer den vollen Tagesstand kennen
        muss — genau das tut `Energiezaehler`.
        """
        spalten = ", ".join(self.ENERGIE_KANAELE)
        platz = ", ".join("?" * len(self.ENERGIE_KANAELE))
        setzt = ", ".join(f"{s}=excluded.{s}" for s in self.ENERGIE_KANAELE)
        werte_liste = [float(werte.get(s) or 0.0) for s in self.ENERGIE_KANAELE]
        ts = (jetzt or datetime.now()).isoformat(timespec="seconds")
        self._db.execute(
            f"INSERT INTO energie_tag (tag, {spalten}, quelle, aktualisiert)"
            f" VALUES (?, {platz}, ?, ?)"
            f" ON CONFLICT(tag) DO UPDATE SET {setzt},"
            f" quelle=excluded.quelle, aktualisiert=excluded.aktualisiert",
            [tag] + werte_liste + [quelle, ts],
        )
        self._db.commit()

    def energie_tag_lesen(self, tag: str) -> dict | None:
        cur = self._db.execute("SELECT * FROM energie_tag WHERE tag=?", (tag,))
        row = cur.fetchone()
        if row is None:
            return None
        return dict(zip([c[0] for c in cur.description], row))

    # --- Energie-Stundenbilanz (v0.15) ---------------------------------------
    # Damit die Tagesansicht den Tag über 24 Stunden zeigen kann, reicht die
    # Tageszeile nicht — sie ist genau eine Säule. Die Stundentabelle wird vom
    # selben Zähler gefüllt und nach denselben Regeln (absolute Stände, UPSERT).
    #
    # Kein Nachtrag für die Vergangenheit möglich: `snapshots` führt weder
    # `p_pv_e3dc_w` noch `p_haus_w`, und die E3DC-Historie liefert Tagessummen.
    # Stunden gibt es deshalb erst ab dem Tag, an dem diese Version läuft — die
    # Ansicht sagt das offen, statt eine flache Kurve zu erfinden.

    def energie_stunde_schreiben(self, stunde: str, werte: dict,
                                 jetzt: datetime | None = None) -> None:
        """Eine Stundenzeile setzen (UPSERT, absolute Werte wie beim Tag)."""
        spalten = ", ".join(self.ENERGIE_KANAELE)
        platz = ", ".join("?" * len(self.ENERGIE_KANAELE))
        setzt = ", ".join(f"{s}=excluded.{s}" for s in self.ENERGIE_KANAELE)
        werte_liste = [float(werte.get(s) or 0.0) for s in self.ENERGIE_KANAELE]
        ts = (jetzt or datetime.now()).isoformat(timespec="seconds")
        self._db.execute(
            f"INSERT INTO energie_stunde (stunde, {spalten}, aktualisiert)"
            f" VALUES (?, {platz}, ?)"
            f" ON CONFLICT(stunde) DO UPDATE SET {setzt},"
            f" aktualisiert=excluded.aktualisiert",
            [stunde] + werte_liste + [ts],
        )
        self._db.commit()

    def energie_stunde_lesen(self, stunde: str) -> dict | None:
        cur = self._db.execute("SELECT * FROM energie_stunde WHERE stunde=?", (stunde,))
        row = cur.fetchone()
        if row is None:
            return None
        return dict(zip([c[0] for c in cur.description], row))

    def energie_stunden(self, von: str | None = None,
                        bis: str | None = None) -> list[dict]:
        """Stundenzeilen eines Tagesfensters, in der Form der Diagrammreihe.

        `von`/`bis` sind **Tage** (YYYY-MM-DD) wie überall in der Historie; der
        Vergleich läuft trotzdem sauber, weil 'YYYY-MM-DD HH' mit dem Tag
        beginnt und lexikografisch sortiert. `bis` bekommt darum ein
        angehängtes 'Z', damit die letzte Stunde des Tages noch hineinfällt.

        Ausgegeben wird `periode` (nicht `stunde`), damit Diagramme, Tabelle
        und CSV-Export dieselbe Zeilenform sehen wie bei Tag/Woche/Monat/Jahr.
        `tage` gibt es hier nicht — eine Stunde ist kein Tag, und eine Spalte
        voller Nullen im Export wäre nur eine Einladung, sie zu summieren.
        """
        sql = "SELECT * FROM energie_stunde"
        bed, args = [], []
        if von:
            bed.append("stunde >= ?"); args.append(von)
        if bis:
            bed.append("stunde <= ?"); args.append(bis + "Z")
        if bed:
            sql += " WHERE " + " AND ".join(bed)
        cur = self._db.execute(sql + " ORDER BY stunde", args)
        cols = [c[0] for c in cur.description]
        zeilen = []
        for r in cur.fetchall():
            roh = dict(zip(cols, r))
            z = {"periode": roh["stunde"], "stunden": 1, "quellen": "ems"}
            z.update({k: roh.get(k) for k in self.ENERGIE_KANAELE})
            zeilen.append(z)
        return zeilen

    def energie_tage(self, von: str | None = None, bis: str | None = None) -> list[dict]:
        sql = "SELECT * FROM energie_tag"
        bed, args = [], []
        if von:
            bed.append("tag >= ?"); args.append(von)
        if bis:
            bed.append("tag <= ?"); args.append(bis)
        if bed:
            sql += " WHERE " + " AND ".join(bed)
        cur = self._db.execute(sql + " ORDER BY tag", args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    # Periodenschlüssel je Ebene (v0.14: Woche und Tag kamen dazu, damit die
    # Diagramme alle vier Ebenen aus derselben Abfrage bekommen).
    #
    # „woche" ist bewusst der **Montag als Datum** und keine Kalenderwochen-
    # nummer: SQLites `%W` zählt ab dem ersten Montag des Jahres, alles davor
    # landet in Woche 00, und zum Jahreswechsel gehören Tage zweier Jahre in
    # dieselbe Woche — ein Nummernpaar wäre dort mehrdeutig. Ein Datum ist
    # eindeutig, sortiert von allein richtig und lässt sich in der Anzeige
    # beschriften, wie man will. `date(tag,'-6 days','weekday 1')` liefert für
    # jeden Wochentag den Montag derselben Woche (SQLite bleibt bei `weekday`
    # stehen, wenn das Datum schon der gesuchte Tag ist).
    ENERGIE_PERIODE = {
        "tag": "tag",
        "woche": "date(tag, '-6 days', 'weekday 1')",
        "monat": "substr(tag, 1, 7)",
        "jahr": "substr(tag, 1, 4)",
    }

    def energie_gruppiert(self, ebene: str, jahr: str | None = None,
                          von: str | None = None, bis: str | None = None) -> list[dict]:
        """Summen je Tag / Woche / Monat / Jahr (Issue #13).

        Aggregiert wird in SQL statt in Python: Für „beliebige Jahre" müssten
        sonst alle Tageszeilen durch den Prozess wandern, nur um summiert zu
        werden.

        `von`/`bis` grenzen auf **Tagesebene** ein, nicht auf Periodenebene —
        das Diagramm zeigt immer ein Fenster (ein Monat in Tagen, ein Jahr in
        Wochen), und dessen Ränder sind Tage. Eine angeschnittene Randwoche ist
        damit die Summe ihrer Tage *innerhalb* des Fensters; `tage` weist aus,
        wie viele das waren, damit eine kurze Randsäule als solche erkennbar
        bleibt statt als schlechter Ertrag.
        """
        schluessel = self.ENERGIE_PERIODE[ebene]
        summen = ", ".join(f"ROUND(SUM({s}), 1) AS {s}" for s in self.ENERGIE_KANAELE)
        sql = (f"SELECT {schluessel} AS periode, COUNT(*) AS tage,"
               f" {summen}, GROUP_CONCAT(DISTINCT quelle) AS quellen FROM energie_tag")
        bed, args = [], []
        if jahr:
            bed.append("substr(tag, 1, 4) = ?"); args.append(jahr)
        if von:
            bed.append("tag >= ?"); args.append(von)
        if bis:
            bed.append("tag <= ?"); args.append(bis)
        if bed:
            sql += " WHERE " + " AND ".join(bed)
        cur = self._db.execute(sql + " GROUP BY periode ORDER BY periode", args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def wp_aktiv_stunden(self, tag: str) -> list[dict]:
        """Je Stunde des Tages: Anteil, in dem WW-Boost bzw. Heizkreis-Anhebung lief.

        Die Wärmepumpe hat keinen eigenen Zähler — ihr Verbrauch steckt im
        Hausverbrauch und lässt sich nicht herausrechnen. Eine Verbrauchskurve
        wäre also erfunden. Was das EMS dagegen genau weiß, ist **wann es die
        Anlage angefordert hat**: Das steht in jedem Tick-Snapshot.

        Gezählt wird als Anteil (0…1) und nicht in Minuten: Der Tick liegt bei
        10 s, war aber nicht immer dort, und nach einem Neustart fehlen Ticks.
        `treffer / ticks` bleibt auch dann richtig, während eine Minutenzahl aus
        `treffer × 10 s` still zu klein würde. `ticks` wird mitgeliefert, damit
        eine Stunde mit dünner Datenlage erkennbar bleibt.
        """
        cur = self._db.execute(
            "SELECT substr(ts, 1, 13) AS stunde, COUNT(*) AS ticks,"
            " SUM(COALESCE(wp_ww_boost, 0)) AS ww, SUM(COALESCE(wp_hk_boost, 0)) AS hk"
            " FROM snapshots WHERE ts >= ? AND ts < ? GROUP BY stunde ORDER BY stunde",
            (tag, tag + "T24"),
        )
        roh = {r[0]: r for r in cur.fetchall()}
        raus = []
        for h in range(24):
            r = roh.get(f"{tag}T{h:02d}")
            ticks = r[1] if r else 0
            raus.append({
                "stunde": f"{tag} {h:02d}",
                "ticks": ticks,
                "ww": round(r[2] / ticks, 3) if ticks else None,
                "hk": round(r[3] / ticks, 3) if ticks else None,
            })
        return raus

    def energie_bekannte_tage(self, quelle: str | None = None) -> set[str]:
        """Welche Tage stehen schon in der Tabelle? Für den Nachimport."""
        if quelle:
            rows = self._db.execute("SELECT tag FROM energie_tag WHERE quelle=?", (quelle,)).fetchall()
        else:
            rows = self._db.execute("SELECT tag FROM energie_tag").fetchall()
        return {r[0] for r in rows}
