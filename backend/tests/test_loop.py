"""Integrationstest der Regelschleife mit Simulatoren — Entladesperre (§5.1) und Fail-Safe E1 (§7)."""

import asyncio
from datetime import datetime, timedelta

from leo_ems.config import RegelConfig
from leo_ems.core.loop import ControlLoop
from leo_ems.devices.e3dc import E3dcSimulator
from leo_ems.devices.goe import GoeSimulator
from leo_ems.safety import SafetyGuard
from leo_ems.store import Store

T0 = datetime(2026, 7, 15, 12, 0, 0)


def build(tmp_path):
    # Diese Tests prüfen den AKTIV-Betrieb; der Beobachtungsmodus (read_only,
    # Default True) hat eigene Tests in test_observation.py.
    cfg = RegelConfig(read_only=False)
    store = Store(tmp_path / "test.db")
    guard = SafetyGuard(cfg)
    # 2900 W Überschuss (Netz -3000, residual 100), Batterie entlädt 300 W (<-200 → Sperre)
    e3dc = E3dcSimulator(p_netz_w=-3000, p_batterie_w=-300, soc_pct=60)
    goe = GoeSimulator(connected=True, power_w=0)
    loop = ControlLoop(cfg, guard, store, {"e3dc": e3dc, "goe": goe})
    return loop, e3dc, goe, guard


def test_laden_und_entladesperre(tmp_path):
    """Nach der Einschaltverzögerung lädt die Wallbox und die E3DC-Entladesperre wird gesetzt."""
    loop, e3dc, goe, guard = build(tmp_path)

    asyncio.run(loop.tick(T0))                       # Einschaltverzögerung startet
    assert not goe.charging

    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))   # Ladung beginnt
    assert goe.charging
    assert ("charging", True) in goe.commands
    assert e3dc.entladesperre is True                # Sperre gesetzt (§5.1)
    assert guard.active("e3dc_entladesperre", T0 + timedelta(seconds=60))


def test_failsafe_e1_schaltet_ab(tmp_path):
    """E3DC nicht erreichbar → Ladung wird gestoppt (Spec §7/E1)."""
    loop, e3dc, goe, guard = build(tmp_path)
    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))
    assert goe.charging

    e3dc.available = False                           # Ausfall provozieren
    asyncio.run(loop.tick(T0 + timedelta(seconds=70)))   # 10 s ohne Daten → Grace, noch keine Änderung
    assert goe.charging is True
    asyncio.run(loop.tick(T0 + timedelta(seconds=130)))  # >60 s ohne Daten → abschalten
    assert goe.charging is False
    assert loop.status()["state"] == "abgeschaltet"


def test_lease_laeuft_ohne_erneuerung_aus(tmp_path):
    """ADR-005: Wird nach gesetzter Sperre nicht mehr getickt, läuft sie per TTL aus (T4-Kern)."""
    loop, e3dc, goe, guard = build(tmp_path)
    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))
    assert guard.active("e3dc_entladesperre", T0 + timedelta(seconds=60))
    # EMS "stirbt" → keine Ticks mehr → Lease abgelaufen nach TTL (900 s)
    assert not guard.active("e3dc_entladesperre", T0 + timedelta(seconds=60 + 901))
