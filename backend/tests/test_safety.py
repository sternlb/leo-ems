"""Lease/TTL-Prinzip (ADR-005, Spec §5.1) und Befehls-Validierung (REQ-063) — Basis für T4."""

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
