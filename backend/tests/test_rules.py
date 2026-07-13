"""Abnahmekriterien Spec §4.3 (REQ-003/004/070) — inkl. T3-Mehrfachregel-Szenario."""

from datetime import datetime, time

from leo_ems.config import RegelConfig
from leo_ems.planner import ChargingRule, naechste_abfahrt, plane_garantieladung
from leo_ems.planner.rules import default_rule

CFG = RegelConfig()
MO_FR = frozenset(range(5))
SA = frozenset({5})

# Mittwoch, 2026-07-15
MITTWOCH_ABEND = datetime(2026, 7, 15, 22, 0)
FREITAG_ABEND = datetime(2026, 7, 17, 20, 0)


def test_akzeptanz_garantieladung_start():
    """Spec §4.3: SoC 30 %, Mo–Fr 07:30/50 % ⇒ Start spätestens 05:42 am Folgetag."""
    plan = plane_garantieladung([default_rule()], soc_ist_pct=30, now=MITTWOCH_ABEND, cfg=CFG)
    assert plan is not None
    assert plan.abfahrt == datetime(2026, 7, 16, 7, 30)
    assert plan.soc_min_pct == 50
    assert abs(plan.e_fehlt_kwh - 17.1) < 0.05                    # (50−30)% × 77 kWh / 0,9
    assert plan.t_start.strftime("%H:%M") == "05:41"              # 07:30 − 1:33 h − 15 min
    assert plan.t_start <= datetime(2026, 7, 16, 5, 42)


def test_akzeptanz_kein_bedarf():
    """Spec §4.3: SoC 55 % ⇒ keine Garantieladung nötig (t_start ≈ Abfahrt, garantie_aktiv False)."""
    plan = plane_garantieladung([default_rule()], soc_ist_pct=55, now=MITTWOCH_ABEND, cfg=CFG)
    assert plan.e_fehlt_kwh == 0
    assert not plan.garantie_aktiv(datetime(2026, 7, 16, 7, 0), soc_ist_pct=55)


def test_akzeptanz_t3_mehrere_regeln():
    """Spec §10/T3: Freitagabend, Regeln Mo–Fr 07:30/50 % + Sa 09:00/30 % ⇒ Planung auf Sa 09:00/30 %."""
    regeln = [
        ChargingRule(weekdays=MO_FR, departure=time(7, 30), soc_min_pct=50),
        ChargingRule(weekdays=SA, departure=time(9, 0), soc_min_pct=30),
    ]
    abfahrt, soc = naechste_abfahrt(regeln, FREITAG_ABEND)
    assert abfahrt == datetime(2026, 7, 18, 9, 0)   # Samstag
    assert soc == 30


def test_zeitgleiche_regeln_hoechster_soc_gewinnt():
    regeln = [
        ChargingRule(weekdays=MO_FR, departure=time(7, 30), soc_min_pct=50),
        ChargingRule(weekdays=MO_FR, departure=time(7, 30), soc_min_pct=70),
    ]
    _, soc = naechste_abfahrt(regeln, MITTWOCH_ABEND)
    assert soc == 70


def test_deaktivierte_regel_zaehlt_nicht():
    """Spec §4.3: Regel per App deaktiviert ⇒ keine Garantieplanung mehr."""
    regel = ChargingRule(weekdays=MO_FR, departure=time(7, 30), soc_min_pct=50, active=False)
    assert naechste_abfahrt([regel], MITTWOCH_ABEND) is None
    assert plane_garantieladung([regel], 30, MITTWOCH_ABEND, CFG) is None


def test_garantie_uebersteuert_aus_modus():
    """Festlegung 5: garantie_aktiv ist die Bedingung, die auch Modus 'Aus' übersteuert."""
    plan = plane_garantieladung([default_rule()], soc_ist_pct=30, now=MITTWOCH_ABEND, cfg=CFG)
    assert plan.garantie_aktiv(datetime(2026, 7, 16, 6, 0), soc_ist_pct=30)      # nach t_start, unter Ziel
    assert not plan.garantie_aktiv(datetime(2026, 7, 16, 6, 0), soc_ist_pct=52)  # Ziel erreicht
