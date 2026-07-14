"""Zustandsmaschine Spec §3/§4.1/§4.2 — inkl. Abnahmetests T1 (Überschussfolge) und T2 (Phasenwechsel)."""

from datetime import datetime, timedelta

from leo_ems.config import RegelConfig
from leo_ems.planner.charge_control import ChargeController, ChargeState

CFG = RegelConfig()
T0 = datetime(2026, 7, 15, 12, 0, 0)


def s(sec: int) -> datetime:
    return T0 + timedelta(seconds=sec)


def upd(ctrl, sec, surplus, mode="Nur-PV", connected=True, guarantee=False, soc=None, limit=100):
    return ctrl.update(s(sec), surplus_w=surplus, connected=connected, mode=mode,
                       guarantee_active=guarantee, soc_fahrzeug=soc, vehicle_limit_soc=limit)


def test_t1_ueberschussfolge():
    """Spec §10/T1: Einspeise-Sprung → Ladung startet nach 60 s ~12 A 1p; Wegfall stoppt nach 180 s."""
    ctrl = ChargeController(CFG)
    assert not upd(ctrl, 0, 2900).charging          # Einschaltverzögerung läuft
    assert not upd(ctrl, 59, 2900).charging
    cmd = upd(ctrl, 60, 2900)
    assert cmd.charging and cmd.phases == 1 and cmd.current_a == 12   # floor(2900/230)=12

    # Überschuss fällt weg
    assert upd(ctrl, 61, 0).charging                # innerhalb der 180 s Ausschaltverzögerung
    assert upd(ctrl, 240, 0).charging               # 179 s → noch an
    stop = upd(ctrl, 241, 0)                        # 180 s → aus
    assert not stop.charging and stop.state == ChargeState.PAUSIERT


def test_t2_phasenwechsel():
    """Spec §10/T2: 3p nach 60 s bei ≥5 kW; zurück auf 1p erst nach 180 s UND ≥10 min Abstand."""
    ctrl = ChargeController(CFG)
    upd(ctrl, 0, 5000)                              # Einschaltverzögerung
    assert upd(ctrl, 60, 5000).phases == 1          # Start immer 1p
    assert upd(ctrl, 120, 5000).phases == 3         # nach 60 s hohem Überschuss → 3p

    # Überschuss fällt unter phase_down (4000), aber 10-min-Sperre greift
    assert upd(ctrl, 300, 3000).phases == 3         # 180 s down, aber erst 180 s seit Umschaltung
    assert upd(ctrl, 719, 3000).phases == 3         # immer noch < 10 min Abstand
    assert upd(ctrl, 720, 3000).phases == 1         # 600 s Abstand erreicht → zurück auf 1p


def test_modus_aus_kein_laden():
    ctrl = ChargeController(CFG)
    cmd = upd(ctrl, 0, 5000, mode="Aus")
    assert not cmd.charging and "Aus" in cmd.reason


def test_modus_schnell_max_sofort():
    ctrl = ChargeController(CFG)
    cmd = upd(ctrl, 0, 0, mode="Schnell")           # kein Überschuss, trotzdem max
    assert cmd.charging and cmd.current_a == 16 and cmd.phases == 3


def test_garantie_uebersteuert_aus():
    """Festlegung 5: Garantieladung lädt auch im Modus 'Aus'."""
    ctrl = ChargeController(CFG)
    cmd = upd(ctrl, 0, 0, mode="Aus", guarantee=True)
    assert cmd.charging and cmd.current_a == 16 and "Garantie" in cmd.reason


def test_pv_min_laedt_immer_mindestens():
    """Spec §3: PV+Min lädt nie unter 6 A, Rest aus Netz/Batterie."""
    ctrl = ChargeController(CFG)
    cmd = upd(ctrl, 0, 200, mode="PV+Min")          # fast kein Überschuss
    assert cmd.charging and cmd.current_a == 6 and "Netz/Batterie" in cmd.reason


def test_fahrzeug_limit_beendet():
    ctrl = ChargeController(CFG)
    cmd = upd(ctrl, 0, 5000, soc=80, limit=80)
    assert not cmd.charging and cmd.state == ChargeState.BEENDET


def test_phase_diagnose_entprellung():
    """REQ-050: Während der 60-s-Entprellung 1p→3p ist der Grund samt Fortschritt sichtbar."""
    ctrl = ChargeController(CFG)
    upd(ctrl, 0, 5000)                       # Einschalt-Hysterese läuft
    upd(ctrl, 60, 5000)                      # Ladung startet 1p, phase_up-Timer beginnt
    d = ctrl.phase_diagnose(s(90), 5000)     # 30 s von 60 s gehalten
    assert d["phasen"] == 1 and d["wechsel_ziel"] == 3
    assert d["entprellung_aktiv"] is True
    assert d["entprellung_seit_s"] == 30 and d["entprellung_noetig_s"] == 60
    assert "Entprellung" in d["grund"]


def test_phase_diagnose_umschaltsperre():
    """Nach dem Wechsel auf 3p blockiert die 10-min-Sperre den Rückweg — mit Restzeit."""
    ctrl = ChargeController(CFG)
    upd(ctrl, 0, 5000)
    upd(ctrl, 60, 5000)
    upd(ctrl, 120, 5000)                     # → 3p, Umschaltsperre startet
    d = ctrl.phase_diagnose(s(180), 3000)    # Überschuss unter 4 kW, aber Sperre aktiv
    assert d["phasen"] == 3 and d["wechsel_ziel"] == 1
    assert d["umschaltsperre_aktiv"] is True
    assert d["umschaltsperre_rest_s"] == 540  # 600 s − 60 s
    assert "Umschaltsperre" in d["grund"]


def test_phase_diagnose_stabil():
    ctrl = ChargeController(CFG)
    d = ctrl.phase_diagnose(T0, 2000)        # 1p, Überschuss unter 3p-Schwelle
    assert d["wechsel_ziel"] is None and d["grund"].startswith("bleibt 1p")


def test_kein_fahrzeug_frei():
    ctrl = ChargeController(CFG)
    cmd = upd(ctrl, 0, 5000, connected=False)
    assert not cmd.charging and cmd.state == ChargeState.FREI
