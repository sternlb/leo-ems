"""Lease/TTL-Prinzip (ADR-005, Spec §5.1) und Befehls-Validierung (REQ-063) — Basis für T4."""

import asyncio
from datetime import datetime, timedelta

from leo_ems.config import RegelConfig
from leo_ems.safety import SafetyGuard

NOW = datetime(2026, 7, 15, 12, 0)


def make_guard(**overrides) -> SafetyGuard:
    return SafetyGuard(RegelConfig(**overrides))


def test_lease_laeuft_nach_ttl_aus():
    """T4-Kern: Entladesperre ohne Erneuerung ⇒ nach 15 min automatisch weg."""
    guard = make_guard()
    guard.acquire("e3dc_entladesperre", NOW, reason="EV lädt")
    assert guard.active("e3dc_entladesperre", NOW + timedelta(minutes=14))
    assert not guard.active("e3dc_entladesperre", NOW + timedelta(minutes=15, seconds=1))


def test_sweep_meldet_abgelaufene_leases():
    guard = make_guard()
    guard.acquire("e3dc_entladesperre", NOW)
    abgelaufen = guard.sweep(NOW + timedelta(minutes=16))
    assert [l.name for l in abgelaufen] == ["e3dc_entladesperre"]
    assert guard.sweep(NOW + timedelta(minutes=17)) == []


def test_strom_validierung_6_bis_16_a():
    guard = make_guard()
    assert guard.validate_current(6) == 6
    assert guard.validate_current(16) == 16
    assert guard.validate_current(5) is None
    assert guard.validate_current(17) is None


def test_batterie_reserve():
    """REQ-021: kein aktives Entladen unter die Reserve (Default 0 %, hier 20 %)."""
    guard = make_guard(soc_reserve_pct=20)
    assert guard.validate_battery_discharge(soc_pct=25)
    assert not guard.validate_battery_discharge(soc_pct=20)


# --- Hängendes Gerät (2026-08-30) -------------------------------------------

def test_haengendes_geraet_haelt_die_regelschleife_nicht_an():
    """Am 30.08.2026 blieb der Škoda-Cloud-Adapter nach einem Update in einem
    `await` stehen. Das EMS hat danach **keinen einzigen Tick** mehr zu Ende
    gebracht — aus einem Cloud-Problem wurde ein totes EMS. Kein Gerät ist
    wichtig genug, um die Regelung anzuhalten."""
    import tempfile
    from pathlib import Path
    from leo_ems.config import RegelConfig
    from leo_ems.core import loop as loop_modul
    from leo_ems.core.loop import ControlLoop
    from leo_ems.devices.e3dc import E3dcSimulator
    from leo_ems.devices.goe import GoeSimulator
    from leo_ems.safety import SafetyGuard
    from leo_ems.store import Store

    class HaengenderAdapter:
        name = "skoda"
        last_update = None

        async def read(self):
            await asyncio.sleep(3600)          # kommt nie zurück

    cfg = RegelConfig(read_only=True)
    store = Store(Path(tempfile.mkdtemp()) / "hang.db")
    loop = ControlLoop(cfg, SafetyGuard(cfg), store,
                       {"e3dc": E3dcSimulator(p_netz_w=-1000, soc_pct=50),
                        "goe": GoeSimulator(connected=False),
                        "skoda": HaengenderAdapter()})

    async def lauf():
        # Timeout kurz setzen, damit der Test nicht 15 s wartet.
        monkey = loop_modul.GERAET_TIMEOUT_S
        loop_modul.GERAET_TIMEOUT_S = 0.05
        try:
            await asyncio.wait_for(loop.tick(datetime(2026, 8, 30, 12, 0)), timeout=5)
        finally:
            loop_modul.GERAET_TIMEOUT_S = monkey

    asyncio.run(lauf())
    # Der Tick ist durchgelaufen: Es gibt einen Status und ein Protokoll.
    assert loop._last_status.get("grund")
    assert loop._last_status.get("soc_fahrzeug") is None      # das Gerät fehlt eben
    assert loop.status()["geraete"]["skoda"]["fehler"].startswith("antwortet nicht")
