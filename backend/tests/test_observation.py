"""Beobachtungsmodus (read_only): volle Entscheidungslogik, NULL Gerätebefehle.

Kern der Migrationsstrategie (specs/03-architecture.md): das EMS läuft parallel
zu EVCC, entscheidet mit, fasst aber nichts an — und die Snapshots liefern die
Auswertung fürs Cockpit (EMS-hätte vs. EVCC-real).
"""

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from leo_ems.config import RegelConfig
from leo_ems.core.loop import ControlLoop
from leo_ems.devices.e3dc import E3dcSimulator
from leo_ems.devices.goe import GoeSimulator
from leo_ems.safety import SafetyGuard
from leo_ems.store import Store

T0 = datetime(2026, 7, 16, 12, 0)


def make_loop(read_only: bool):
    cfg = RegelConfig(read_only=read_only)
    store = Store(Path(tempfile.mkdtemp()) / "test.db")
    e3dc = E3dcSimulator(p_netz_w=-3000, p_batterie_w=0, soc_pct=61)  # speist 3 kW ein
    goe = GoeSimulator(connected=True)
    loop = ControlLoop(cfg, SafetyGuard(cfg), store, {"e3dc": e3dc, "goe": goe})
    return loop, store, e3dc, goe


def zwei_ticks(loop):
    """Tick 1 startet die Einschalt-Hysterese, Tick 2 (nach 61 s) löst die Ladung aus."""
    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=61)))


def test_read_only_keine_geraetebefehle():
    loop, store, e3dc, goe = make_loop(read_only=True)
    zwei_ticks(loop)
    st = loop.status()
    assert st["laedt"] is True                      # Entscheidung fällt ganz normal …
    assert st["grund"].startswith("[Beobachtung]")  # … ist als Beobachtung markiert …
    assert goe.commands == [] and e3dc.commands == []  # … aber KEIN Gerät wird angefasst


def test_aktiv_sendet_befehle():
    loop, store, e3dc, goe = make_loop(read_only=False)
    zwei_ticks(loop)
    assert ("charging", True) in goe.commands
    assert ("current", 12) in goe.commands          # 2900 W / 230 V = 12 A, 1-phasig
    assert ("entladelimit", 200) in e3dc.commands   # Entladegrenze gesetzt (Spec §5.1)


def test_read_only_failsafe_e1_stoppt_nichts():
    """E3DC weg → im Aktivbetrieb würde die Ladung gestoppt; in Beobachtung darf
    EVCCs laufende Ladung NICHT abgewürgt werden."""
    loop, store, e3dc, goe = make_loop(read_only=True)
    e3dc.available = False
    asyncio.run(loop.tick(T0))
    assert loop.status()["state"] == "abgeschaltet"
    assert goe.commands == []


def test_snapshots_und_summary():
    loop, store, e3dc, goe = make_loop(read_only=True)
    zwei_ticks(loop)
    snaps = store.snapshots_recent()
    assert len(snaps) == 2
    assert snaps[-1]["wuerde_laden"] == 1 and snaps[-1]["read_only"] == 1

    s = store.observation_summary(interval_s=10)
    assert s["snapshots"] == 2
    assert s["ueberschuss_max_w"] == 2900
    # 1 Lade-Tick à 12 A × 1p × 230 V × 10 s = 7,7 Wh "hätte geladen"
    assert abs(s["ems_haette_geladen_wh"] - 7.7) < 0.1
    assert s["real_wallbox_wh"] == 0                # EVCC lud im Szenario nicht
    assert len(s["taeglich"]) == 1 and s["taeglich"][0]["tag"] == "2026-07-16"


def test_summary_ohne_daten():
    store = Store(Path(tempfile.mkdtemp()) / "leer.db")
    assert store.observation_summary()["snapshots"] == 0


# --- Aktive Zeiten der Wärmepumpe (Issue #14) --------------------------------

def _snap(store, ts, ww=0, hk=0):
    store.log_snapshot(ts, ueberschuss_w=0, p_netz_w=0, p_batterie_w=0, soc_batt=50,
                       soc_v=50, p_wallbox_w=0, p_sungrow_w=0, wuerde_laden=0,
                       strom_a=0, phasen=1, garantie=0, read_only=1,
                       entladelimit_w=None, wp_ww_boost=ww, wp_hk_boost=hk)


def test_wp_aktive_zeiten_kommen_aus_den_snapshots():
    """Die WP hat keinen eigenen Zähler — eine Verbrauchskurve wäre erfunden.
    Wann das EMS sie angefordert hat, steht dagegen in jedem Tick."""
    store = Store(Path(tempfile.mkdtemp()) / "wp.db")
    t = datetime(2026, 8, 30, 11, 0)
    for i in range(60):                                  # eine Stunde à 60 Ticks
        _snap(store, t + timedelta(seconds=i * 10), ww=1 if i < 30 else 0)
    zeilen = store.wp_aktiv_stunden("2026-08-30")
    assert len(zeilen) == 24
    elf = next(z for z in zeilen if z["stunde"].endswith(" 11"))
    assert elf["ww"] == 0.5 and elf["ticks"] == 60


def test_stunde_ohne_ticks_ist_nicht_null_sondern_unbekannt():
    """Eine Stunde, in der das EMS nicht lief, ist keine Stunde ohne Boost.
    Beides als 0 auszuweisen hieße, eine Aussage zu erfinden."""
    store = Store(Path(tempfile.mkdtemp()) / "wp2.db")
    _snap(store, datetime(2026, 8, 30, 11, 0), ww=1)
    zeilen = store.wp_aktiv_stunden("2026-08-30")
    assert next(z for z in zeilen if z["stunde"].endswith(" 11"))["ww"] == 1.0
    assert next(z for z in zeilen if z["stunde"].endswith(" 03"))["ww"] is None


def test_wp_aktiv_zaehlt_nur_den_angefragten_tag():
    """substr auf dem Zeitstempel schneidet leicht daneben — ein Tick um
    Mitternacht des Folgetags gehört nicht in diese Liste."""
    store = Store(Path(tempfile.mkdtemp()) / "wp3.db")
    _snap(store, datetime(2026, 8, 30, 23, 59, 50), ww=1)
    _snap(store, datetime(2026, 8, 31, 0, 0, 0), ww=1)
    zeilen = store.wp_aktiv_stunden("2026-08-30")
    assert sum(z["ticks"] for z in zeilen) == 1


def test_ticks_von_vor_der_umstellung_gelten_als_unbekannt():
    """Snapshot-Zeilen aus der Zeit vor v0.17 führen die Spalten als NULL. Über
    COUNT(*) gemittelt ergäbe das 0,0 — „es lief kein Boost" — und wäre für
    jede Stunde falsch, in der einer lief."""
    store = Store(Path(tempfile.mkdtemp()) / "wp4.db")
    # So sah eine Zeile vor v0.17 aus: ohne die beiden Spalten.
    store._db.execute("INSERT INTO snapshots (ts, soc_batt) VALUES (?, ?)",
                      ("2026-08-30T11:00:00", 50.0))
    store._db.commit()
    zeilen = store.wp_aktiv_stunden("2026-08-30")
    elf = next(z for z in zeilen if z["stunde"].endswith(" 11"))
    assert elf["ticks"] == 0 and elf["ww"] is None
