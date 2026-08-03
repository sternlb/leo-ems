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
    """Spec §10/T2: 3p nach 60 s bei ≥5 kW; Rückfall auf 1p nach 60 s, ohne Sperre.

    Geändert mit Issue #7 (v0.8.0): Der Rückfall wartete früher zusätzlich die
    10-min-Umschaltsperre ab — in dieser Zeit stand die Wallbox 3-phasig unter
    ihrem eigenen Minimum und holte sich die Differenz aus dem Netz.
    """
    ctrl = ChargeController(CFG)
    upd(ctrl, 0, 5000)                              # Einschaltverzögerung
    assert upd(ctrl, 60, 5000).phases == 1          # Start immer 1p
    assert upd(ctrl, 120, 5000).phases == 3         # nach 60 s hohem Überschuss → 3p

    # Überschuss fällt unter das 3p-Minimum (4140 W) → Rückfall nach 60 s
    assert upd(ctrl, 130, 3000).phases == 3         # Bedingung ab hier gehalten
    assert upd(ctrl, 189, 3000).phases == 3         # Entprellung läuft
    assert upd(ctrl, 190, 3000).phases == 1         # 60 s gehalten → zurück, trotz laufender Sperre


def test_hochschalten_wartet_weiter_auf_die_sperre():
    """Die 10-min-Sperre bleibt für den Weg NACH OBEN bestehen (Issue #7)."""
    ctrl = ChargeController(CFG)
    upd(ctrl, 0, 5000)
    upd(ctrl, 60, 5000)
    assert upd(ctrl, 120, 5000).phases == 3         # Umschaltung → Sperre startet bei 120 s
    upd(ctrl, 130, 3000)
    assert upd(ctrl, 190, 3000).phases == 1         # Rückfall → Sperre startet neu bei 190 s
    upd(ctrl, 200, 5000)                            # Überschuss wieder da, Entprellung startet
    assert upd(ctrl, 260, 5000).phases == 1         # Bedingung erfüllt, aber < 600 s Abstand
    assert upd(ctrl, 789, 5000).phases == 1
    assert upd(ctrl, 790, 5000).phases == 3         # 600 s nach dem Rückfall → wieder 3p


def test_3p_unter_minimum_zieht_keinen_dauernetzbezug():
    """Issue #7: 3p bei 2 kW Überschuss hieß 4,14 kW Ladung — 2,1 kW aus dem Netz, dauerhaft.

    Ursache war eine phasenblinde Abschaltschwelle: geprüft wurde gegen das
    1p-Minimum (1,38 kW), gebraucht wurden 3 × 6 A (4,14 kW). Die Bedingung
    „kein Überschuss mehr" wurde damit nie wahr.
    """
    ctrl = ChargeController(CFG)
    upd(ctrl, 0, 5000)
    upd(ctrl, 60, 5000)
    assert upd(ctrl, 120, 5000).phases == 3

    # Ein weiterer Verbraucher geht an, es bleiben 2 kW: 3p kann das nicht
    cmd = upd(ctrl, 130, 2000)
    assert cmd.phases == 3 and "aus dem Netz" in cmd.reason   # Lage steht im Klartext
    # ... aber der Zustand ist nach spätestens 60 s beendet
    cmd = upd(ctrl, 190, 2000)
    assert cmd.charging and cmd.phases == 1 and cmd.current_a == 8   # floor(2000/230)
    assert "aus dem Netz" not in cmd.reason                          # 2 kW tragen 1p vollständig


def test_pause_erst_wenn_auch_1p_nicht_mehr_traegt():
    """Nach dem Rückfall auf 1p läuft die 180-s-Abschaltung gegen das 1p-Minimum."""
    ctrl = ChargeController(CFG)
    upd(ctrl, 0, 5000)
    upd(ctrl, 60, 5000)
    upd(ctrl, 120, 5000)                            # 3p
    upd(ctrl, 130, 500)                             # Bedingung ab hier: unter beiden Minima
    assert upd(ctrl, 190, 500).phases == 1          # Rückfall nach 60 s
    assert upd(ctrl, 300, 500).charging             # 1p-Minimum unterschritten, Entprellung läuft
    assert not upd(ctrl, 310, 500).charging         # 180 s nach Beginn der Unterschreitung → pausiert


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
    """Spec §3: PV+Min lädt nie unter 6 A, den Rest aus dem Netz.

    `netz_gewollt` sagt der Entladegrenze, dass dieser Netzbezug Absicht ist —
    sonst spränge die Hausbatterie ein und liefe über das Auto leer (Spec §5.1).
    """
    ctrl = ChargeController(CFG)
    cmd = upd(ctrl, 0, 200, mode="PV+Min")          # fast kein Überschuss
    assert cmd.charging and cmd.current_a == 6 and "Minimum aus Netz" in cmd.reason
    assert cmd.netz_gewollt is True

    cmd = upd(ctrl, 60, 5000, mode="PV+Min")        # PV trägt → normaler PV-Betrieb
    assert cmd.charging and cmd.netz_gewollt is False


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
    """Die 10-min-Sperre blockiert den Weg nach oben — mit Restzeit (REQ-050)."""
    ctrl = ChargeController(CFG)
    upd(ctrl, 0, 5000)
    upd(ctrl, 60, 5000)
    upd(ctrl, 120, 5000)                     # → 3p
    upd(ctrl, 130, 3000)
    upd(ctrl, 190, 3000)                     # → Rückfall auf 1p, Sperre startet bei 190 s
    d = ctrl.phase_diagnose(s(250), 5000)    # Überschuss wieder da, aber Sperre aktiv
    assert d["phasen"] == 1 and d["wechsel_ziel"] == 3
    assert d["umschaltsperre_aktiv"] is True
    assert d["umschaltsperre_rest_s"] == 540  # 600 s − 60 s
    assert "Umschaltsperre" in d["grund"]


def test_phase_diagnose_rueckfall_nennt_keine_sperre():
    """Der Rückfall 3p→1p wartet auf nichts — das darf die Anzeige nicht anders behaupten."""
    ctrl = ChargeController(CFG)
    upd(ctrl, 0, 5000)
    upd(ctrl, 60, 5000)
    upd(ctrl, 120, 5000)                     # → 3p, Sperre läuft
    d = ctrl.phase_diagnose(s(130), 3000)
    assert d["phasen"] == 3 and d["wechsel_ziel"] == 1
    assert d["umschaltsperre_aktiv"] is False
    assert d["entprellung_aktiv"] is True and d["entprellung_noetig_s"] == 60
    assert "Umschaltsperre" not in d["grund"]


def test_phase_diagnose_stabil():
    ctrl = ChargeController(CFG)
    d = ctrl.phase_diagnose(T0, 2000)        # 1p, Überschuss unter 3p-Schwelle
    assert d["wechsel_ziel"] is None and d["grund"].startswith("bleibt 1p")


def test_kein_fahrzeug_frei():
    ctrl = ChargeController(CFG)
    cmd = upd(ctrl, 0, 5000, connected=False)
    assert not cmd.charging and cmd.state == ChargeState.FREI
