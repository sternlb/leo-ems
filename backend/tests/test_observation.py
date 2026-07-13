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
    e3dc = E3dcSimulator(p_netz_w=-3000, p_batterie_w=-500, soc_pct=61)  # speist ein, Batterie entlädt
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
    assert ("entladesperre", True) in e3dc.commands # Batterie entlud → Sperre gesetzt (Spec §5.1)


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
