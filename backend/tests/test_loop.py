"""Integrationstest der Regelschleife mit Simulatoren — Entladesperre (§5.1) und Fail-Safe E1 (§7)."""

import asyncio
from datetime import datetime, timedelta

from leo_ems.config import RegelConfig
from leo_ems.core.loop import ControlLoop
from leo_ems.devices.e3dc import E3dcSimulator
from leo_ems.devices.goe import GoeSimulator
from leo_ems.devices.vaillant import VaillantSimulator
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


def test_status_enthaelt_energieverteilung_und_phaseninfo(tmp_path):
    """Dashboard-Daten (REQ-051): Leistungsbilanz + Entprellungs-Transparenz im Status."""
    cfg = RegelConfig(read_only=False)
    store = Store(tmp_path / "test.db")
    e3dc = E3dcSimulator(p_netz_w=-3000, p_batterie_w=-300, soc_pct=60, p_pv_w=5000)
    goe = GoeSimulator(connected=True, power_w=0)
    loop = ControlLoop(cfg, SafetyGuard(cfg), store, {"e3dc": e3dc, "goe": goe})
    asyncio.run(loop.tick(T0))

    st = loop.status()
    assert st["p_pv_w"] == 5000
    # Haus = PV + Netz − Batterieladung − Wallbox = 5000 − 3000 + 300 − 0
    assert st["p_haus_w"] == 2300
    pi = st["phasen_info"]
    assert pi["phasen"] == 1 and "grund" in pi
    assert {"entprellung_aktiv", "umschaltsperre_aktiv", "umschaltsperre_rest_s"} <= pi.keys()


def test_lease_laeuft_ohne_erneuerung_aus(tmp_path):
    """ADR-005: Wird nach gesetzter Sperre nicht mehr getickt, läuft sie per TTL aus (T4-Kern)."""
    loop, e3dc, goe, guard = build(tmp_path)
    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))
    assert guard.active("e3dc_entladesperre", T0 + timedelta(seconds=60))
    # EMS "stirbt" → keine Ticks mehr → Lease abgelaufen nach TTL (900 s)
    assert not guard.active("e3dc_entladesperre", T0 + timedelta(seconds=60 + 901))


def test_waermepumpe_bekommt_ueberschuss_nach_wallbox(tmp_path):
    """Vorrang Auto (Leo, 2026-07-25): die WP sieht nur den Rest nach der Ladezuteilung."""
    cfg = RegelConfig(read_only=False)
    store = Store(tmp_path / "test.db")
    # 14,9 kW Überschuss: genug für 16 A 3p (11,0 kW) UND danach noch für die WP
    e3dc = E3dcSimulator(p_netz_w=-15000, p_batterie_w=0, soc_pct=60, p_pv_w=16000)
    goe = GoeSimulator(connected=True, power_w=0)
    wp = VaillantSimulator()
    loop = ControlLoop(cfg, SafetyGuard(cfg), store, {"e3dc": e3dc, "goe": goe, "vaillant": wp})

    asyncio.run(loop.tick(T0))
    st = loop.status()
    assert st["wp"]["verbunden"] is True
    assert st["wp"]["warmwasser"]["ist_c"] == 40.0
    assert st["wp"]["heizkreis"]["vorlauf_c"] == 27.5
    # Noch lädt niemand (Einschalt-Hysterese) → die WP sieht den vollen Überschuss
    assert st["wp"]["frei_w"] == st["ueberschuss_w"]

    # Nach der Bedingungszeit startet der Warmwasser-Boost und geht an die Anlage
    for i in range(1, 70):
        asyncio.run(loop.tick(T0 + timedelta(seconds=i * 10)))
    assert loop.heatpump.ww_boost is True
    assert ("ww_soll", 60.0) in wp.commands

    # Jetzt lädt das Auto — die WP bekommt nur noch, was danach übrig ist
    st = loop.status()
    assert st["laedt"] is True
    assert st["wp"]["frei_w"] < st["ueberschuss_w"]


def test_waermepumpe_im_beobachtungsmodus_stumm(tmp_path):
    """read_only: die Entscheidung steht im Status, aber nichts geht an die Cloud."""
    cfg = RegelConfig(read_only=True)
    store = Store(tmp_path / "test.db")
    e3dc = E3dcSimulator(p_netz_w=-10000, p_batterie_w=0, soc_pct=60, p_pv_w=11000)
    wp = VaillantSimulator()
    loop = ControlLoop(cfg, SafetyGuard(cfg), store, {"e3dc": e3dc, "vaillant": wp})

    for i in range(70):
        asyncio.run(loop.tick(T0 + timedelta(seconds=i * 10)))
    assert loop.heatpump.ww_boost is True
    assert wp.commands == [] and wp.werte["ww_soll_c"] == 45.0


def test_waermepumpe_ausfall_stoert_das_laden_nicht(tmp_path):
    """Fail-Safe E7: WP/HA weg → keine WP-Befehle, Ladebetrieb unverändert."""
    cfg = RegelConfig(read_only=False)
    store = Store(tmp_path / "test.db")
    e3dc = E3dcSimulator(p_netz_w=-3000, p_batterie_w=-300, soc_pct=60)
    goe = GoeSimulator(connected=True, power_w=0)
    wp = VaillantSimulator()
    wp.available = False
    loop = ControlLoop(cfg, SafetyGuard(cfg), store, {"e3dc": e3dc, "goe": goe, "vaillant": wp})

    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))
    assert goe.charging                       # Laden läuft trotz WP-Ausfall
    assert wp.commands == []
    assert loop.status()["wp"]["verbunden"] is False


def test_lesefehler_steht_im_status_und_im_protokoll(tmp_path):
    """T-WP-1 (v0.6.2): ein ausgefallenes Gerät nennt den Grund, statt nur zu fehlen.

    Bis v0.6.1 hat `_safe_read` jede Ausnahme verschluckt — die nicht angebundene
    Wärmepumpe sah im Dashboard genauso aus wie eine gar nicht konfigurierte.
    """
    cfg = RegelConfig(read_only=False)
    store = Store(tmp_path / "test.db")
    e3dc = E3dcSimulator(p_netz_w=-3000, p_batterie_w=0, soc_pct=60)
    wp = VaillantSimulator()
    wp.available = False
    loop = ControlLoop(cfg, SafetyGuard(cfg), store, {"e3dc": e3dc, "vaillant": wp})

    asyncio.run(loop.tick(T0))
    st = loop.status()
    assert "nicht erreichbar" in st["wp"]["fehler"]
    assert st["geraete"]["vaillant"]["ok"] is False
    assert st["geraete"]["e3dc"]["ok"] is True
    assert st["geraete"]["e3dc"]["letzte_lesung"] is not None
    # Der Ausfall steht auch im Protokoll (REQ-062) — genau einmal, nicht je Tick
    for i in range(1, 30):
        asyncio.run(loop.tick(T0 + timedelta(seconds=i * 10)))
    meldungen = [d for d in store.recent_decisions(500) if "vaillant" in str(d)]
    assert len(meldungen) == 1

    # Kommt das Gerät zurück, verschwindet der Fehler und die Rückkehr wird gemeldet
    wp.available = True
    asyncio.run(loop.tick(T0 + timedelta(seconds=300)))
    st = loop.status()
    assert st["wp"]["verbunden"] is True and st["wp"]["fehler"] is None
    assert st["geraete"]["vaillant"]["ok"] is True
    assert len([d for d in store.recent_decisions(500) if "vaillant" in str(d)]) == 2
