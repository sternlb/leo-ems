"""Wärmepumpen-Steuerung (REQ-010/011/012/014/064).

Zeit kommt von außen — die Tests spulen Ticks vor, statt zu warten.
"""

import asyncio
from datetime import datetime, timedelta

from leo_ems.config import RegelConfig
from leo_ems.devices.vaillant import VaillantSimulator, _zahl
from leo_ems.planner import HeatPumpController

T0 = datetime(2026, 7, 25, 12, 0)

# Der Heizkreis ist per Default AUS (Issue #1) — die Heizkreis-Tests schalten
# ihn ausdrücklich ein, damit sie prüfen, was sie prüfen wollen.
def _cfg(**kw) -> RegelConfig:
    return RegelConfig(**{"wp_hk_aktiv": True, **kw})

# Sommer-Messbild: WW 40/45 °C, Heizkreis im Standby, 30 °C draußen
SOMMER = {
    "ww_ist_c": 40.0, "ww_soll_c": 45.0, "ww_modus": "Auto", "ww_sonderfunktion": None,
    "hk_vorlauf_c": 27.5, "hk_vorlauf_soll_c": 0.0, "hk_zustand": "STANDBY", "hk_modus": "Auto",
    "raum_ist_c": 26.0, "raum_soll_c": 0.0, "aussen_c": 29.9, "cop": 3.4,
}
WINTER = {**SOMMER, "aussen_c": 4.0, "raum_soll_c": 21.0, "hk_zustand": "HEATING", "raum_ist_c": 20.5}


def _ticks(hp, wp, frei_w, minuten, start=T0, schritt_s=10, senden=True):
    """Regelschleife simulieren: alle 10 s ein Tick, Befehle „senden"."""
    letzte = None
    for i in range(int(minuten * 60 / schritt_s)):
        now = start + timedelta(seconds=i * schritt_s)
        letzte = hp.update(now, frei_w=frei_w, wp=wp)
        if senden and (letzte.ww_soll_c is not None or letzte.raum_soll_c is not None):
            if letzte.ww_soll_c is not None:
                wp["ww_soll_c"] = letzte.ww_soll_c      # Cloud bestätigt beim nächsten Lesen
            if letzte.raum_soll_c is not None:
                wp["raum_soll_c"] = letzte.raum_soll_c
            hp.schreiben_bestaetigt(now)
    return letzte


# --- Warmwasser (REQ-010) ---------------------------------------------------
def test_ww_boost_startet_erst_nach_entprellung():
    """2,5 kW liegen an — vor Ablauf der Bedingungszeit passiert nichts (REQ-064)."""
    hp = HeatPumpController(RegelConfig())
    wp = dict(SOMMER)
    _ticks(hp, wp, 3000, minuten=5)
    assert hp.ww_boost is False and wp["ww_soll_c"] == 45.0
    _ticks(hp, wp, 3000, minuten=6, start=T0 + timedelta(minutes=5))
    assert hp.ww_boost is True and wp["ww_soll_c"] == 57.0


def test_ww_boost_startet_nicht_unter_der_schwelle():
    hp = HeatPumpController(RegelConfig())
    wp = dict(SOMMER)
    _ticks(hp, wp, 2400, minuten=30)   # knapp unter 2500 W
    assert hp.ww_boost is False and wp["ww_soll_c"] == 45.0


def test_ww_boost_stellt_bei_wegfallendem_ueberschuss_zurueck():
    """Issue #1: automatisch zurück auf 45 °C, wenn der Überschuss nicht mehr reicht."""
    hp = HeatPumpController(RegelConfig())
    wp = dict(SOMMER)
    t = T0
    _ticks(hp, wp, 3000, minuten=11, start=t)
    assert hp.ww_boost is True

    # Mindestlaufzeit abwarten (WP zieht ~2 kW, es bleibt 1 kW übrig), dann Wolke
    t += timedelta(minutes=11)
    _ticks(hp, wp, 1000, minuten=30, start=t)
    t += timedelta(minutes=30)
    _ticks(hp, wp, 0, minuten=10, start=t)
    assert hp.ww_boost is False
    assert wp["ww_soll_c"] == 45.0


def test_ww_boost_haelt_mindestlaufzeit_durch():
    """REQ-064: kein Schaltzyklus im Minutentakt, auch wenn der Überschuss sofort weg ist."""
    hp = HeatPumpController(RegelConfig())
    wp = dict(SOMMER)
    _ticks(hp, wp, 3000, minuten=11)
    assert hp.ww_boost is True
    _ticks(hp, wp, 0, minuten=10, start=T0 + timedelta(minutes=11))
    assert hp.ww_boost is True          # Mindestlaufzeit 30 min läuft noch
    assert wp["ww_soll_c"] == 57.0


def test_ww_boost_schaltet_sich_nicht_selbst_ab():
    """Das Hysterese-Band (2,5 → 0,5 kW) ist so breit wie der WP-Verbrauch.

    Ohne dieses Band würde der eigene Verbrauch den Überschuss unter die
    Aus-Schwelle drücken und den Boost sofort wieder beenden.
    """
    hp = HeatPumpController(RegelConfig())
    wp = dict(SOMMER)
    _ticks(hp, wp, 3000, minuten=11)
    assert hp.ww_boost is True
    # WP zieht jetzt ~2 kW → freier Überschuss bricht auf 1 kW ein, bleibt aber über 500 W
    letzte = _ticks(hp, wp, 1000, minuten=40, start=T0 + timedelta(minutes=11))
    assert hp.ww_boost is True
    assert "aktiv" in letzte.grund


def test_zu_schmales_band_fuehrt_nicht_zum_schaltzyklus():
    """Fehlkonfiguration an 1,5 kW / aus 0,5 kW: die Aus-Schwelle rutscht nach unten."""
    hp = HeatPumpController(RegelConfig(wp_ww_an_w=1500))
    wp = dict(SOMMER)
    _ticks(hp, wp, 1600, minuten=11)
    assert hp.ww_boost is True
    # WP zieht 2 kW → 400 W Netzbezug; toleriert statt Boost-Flattern
    _ticks(hp, wp, -400, minuten=40, start=T0 + timedelta(minutes=11))
    assert hp.ww_boost is True


def test_ww_boost_endet_bei_erreichter_temperatur():
    """Boost-Ziel 57 °C: die Anlage kommt real nur bis ~57,5 °C (belegt 31.07.2026)."""
    hp = HeatPumpController(RegelConfig())
    wp = dict(SOMMER)
    _ticks(hp, wp, 3000, minuten=11)
    assert hp.ww_boost is True
    wp["ww_ist_c"] = 57.0
    # Zurückstellen ist sofort entschieden, das Schreiben wartet aufs Cloud-Gap
    erster = hp.update(T0 + timedelta(minutes=11), frei_w=3000, wp=wp)
    assert hp.ww_boost is False and "erreicht" in erster.grund
    _ticks(hp, wp, 3000, minuten=17, start=T0 + timedelta(minutes=11))
    assert wp["ww_soll_c"] == 45.0


def test_ww_kein_boost_wenn_speicher_schon_warm():
    hp = HeatPumpController(RegelConfig())
    wp = {**SOMMER, "ww_ist_c": 61.0}
    _ticks(hp, wp, 5000, minuten=30)
    assert hp.ww_boost is False and wp["ww_soll_c"] == 45.0


def test_ww_komfortgrenze_hebt_rueckstellwert_an():
    """REQ-012: die harte Untergrenze sticht den Rückstellwert."""
    cfg = RegelConfig(hard_limit_ww_min_temp=50.0)
    hp = HeatPumpController(cfg)
    wp = dict(SOMMER)
    _ticks(hp, wp, 3000, minuten=11)
    wp["ww_ist_c"] = 57.0
    _ticks(hp, wp, 3000, minuten=17, start=T0 + timedelta(minutes=11))
    assert wp["ww_soll_c"] == 50.0


# --- Heizkreis (REQ-011/012) ------------------------------------------------
def test_heizkreis_im_sommer_unberuehrt():
    """Kein Sollwert im Zeitprogramm + 30 °C draußen → nichts anheben."""
    hp = HeatPumpController(_cfg())
    wp = dict(SOMMER)
    _ticks(hp, wp, 8000, minuten=60)
    assert hp.hk_boost is False and wp["raum_soll_c"] == 0.0


def test_heizkreis_anhebung_im_winter():
    hp = HeatPumpController(_cfg())
    wp = {**WINTER, "ww_ist_c": 61.0}   # Warmwasser schon warm → Heizkreis ist dran
    _ticks(hp, wp, 3000, minuten=11)
    assert hp.hk_boost is True
    assert wp["raum_soll_c"] == 22.5    # 21,0 + 1,5 K


def test_heizkreis_respektiert_komfort_obergrenze():
    hp = HeatPumpController(_cfg(wp_hk_max_raum_c=22.0))
    wp = {**WINTER, "ww_ist_c": 61.0, "raum_soll_c": 21.0}
    _ticks(hp, wp, 3000, minuten=11)
    assert wp["raum_soll_c"] == 22.0    # gekappt statt 21,0 + 1,5 K


def test_heizkreis_stellt_auf_basiswert_zurueck():
    hp = HeatPumpController(_cfg())
    wp = {**WINTER, "ww_ist_c": 61.0}
    _ticks(hp, wp, 3000, minuten=11)
    assert hp.hk_boost is True
    t = T0 + timedelta(minutes=11)
    _ticks(hp, wp, 1000, minuten=30, start=t)
    _ticks(hp, wp, 0, minuten=16, start=t + timedelta(minutes=30))
    assert hp.hk_boost is False and wp["raum_soll_c"] == 21.0


def test_warmwasser_hat_vorrang_vor_heizkreis():
    """Die WP kann nur eines zur Zeit — bei laufendem WW-Boost keine Anhebung."""
    hp = HeatPumpController(_cfg())
    wp = dict(WINTER)                    # WW kalt (40 °C) → WW-Boost gewinnt
    _ticks(hp, wp, 6000, minuten=11)
    assert hp.ww_boost is True and hp.hk_boost is False
    assert wp["raum_soll_c"] == 21.0


# --- Getrennt schaltbar (Issue #1) ------------------------------------------
def test_warmwasser_abgeschaltet_startet_keinen_boost():
    hp = HeatPumpController(RegelConfig(wp_ww_aktiv=False))
    wp = dict(SOMMER)
    letzte = _ticks(hp, wp, 8000, minuten=60)
    assert hp.ww_boost is False and wp["ww_soll_c"] == 45.0
    assert "abgeschaltet" in letzte.grund


def test_warmwasser_abschalten_stellt_laufenden_boost_sofort_zurueck():
    """Ein Ausschalter, der erst nach der Mindestlaufzeit wirkt, ist keiner.

    Zusätzlich muss die Rückstellung am Cloud-Gap vorbei: sonst stünde der
    Speicher nach dem Klick noch bis zu 15 min auf Boost-Temperatur.
    """
    cfg = RegelConfig()
    hp = HeatPumpController(cfg)
    wp = dict(SOMMER)
    _ticks(hp, wp, 3000, minuten=11)
    assert hp.ww_boost is True and wp["ww_soll_c"] == 57.0

    cfg.wp_ww_aktiv = False                        # Leo klickt den Schalter
    t = T0 + timedelta(minutes=11)                 # mitten in der Mindestlaufzeit
    cmd = hp.update(t, frei_w=3000, wp=wp)
    assert hp.ww_boost is False
    assert cmd.ww_soll_c == 45.0                   # sofort, nicht erst in 15 min
    assert "abgeschaltet" in cmd.grund


def test_heizkreis_abschalten_stellt_auf_basiswert_zurueck():
    cfg = _cfg()
    hp = HeatPumpController(cfg)
    wp = {**WINTER, "ww_ist_c": 61.0}
    _ticks(hp, wp, 3000, minuten=11)
    assert hp.hk_boost is True and wp["raum_soll_c"] == 22.5

    cfg.wp_hk_aktiv = False
    cmd = hp.update(T0 + timedelta(minutes=11), frei_w=3000, wp=wp)
    assert hp.hk_boost is False and cmd.raum_soll_c == 21.0


def test_funktionen_schalten_sich_nicht_gegenseitig_ab():
    """Getrennte Optionen: Warmwasser läuft weiter, auch ohne Heizkreis."""
    hp = HeatPumpController(RegelConfig(wp_ww_aktiv=True, wp_hk_aktiv=False))
    wp = dict(WINTER)
    _ticks(hp, wp, 6000, minuten=11)
    assert hp.ww_boost is True
    assert hp.hk_boost is False and wp["raum_soll_c"] == 21.0

    hp2 = HeatPumpController(RegelConfig(wp_ww_aktiv=False, wp_hk_aktiv=True))
    wp2 = {**WINTER, "ww_ist_c": 40.0}
    _ticks(hp2, wp2, 6000, minuten=11)
    assert hp2.ww_boost is False and wp2["ww_soll_c"] == 45.0
    assert hp2.hk_boost is True and wp2["raum_soll_c"] == 22.5   # WW-Vorrang greift nicht


def test_default_ist_warmwasser_an_heizkreis_aus():
    """Leos Festlegung (Issue #1): Warmwasser jetzt, Heizung später."""
    cfg = RegelConfig()
    assert cfg.wp_ww_aktiv is True and cfg.wp_hk_aktiv is False


def test_status_meldet_schalterstellung_auch_ohne_verbindung():
    """Das Dashboard zeigt die Schalter auch, wenn die WP gerade nicht antwortet."""
    hp = HeatPumpController(RegelConfig(wp_ww_aktiv=True, wp_hk_aktiv=False))
    st = hp.status(SOMMER)
    assert st["warmwasser"]["aktiv"] is True and st["heizkreis"]["aktiv"] is False
    ohne = hp.status(None)
    assert ohne["warmwasser"]["aktiv"] is True and ohne["heizkreis"]["aktiv"] is False


# --- Cloud-Ratenlimit + Vorrang Auto ---------------------------------------
def test_cloud_gap_bremst_wiederholungen():
    """REQ-014: Bestätigt die Cloud den Sollwert nicht, wird höchstens alle 15 min neu geschrieben."""
    hp = HeatPumpController(RegelConfig())
    wp = dict(SOMMER)
    versuche = 0
    for i in range(6 * 60):              # 60 min à 10 s
        now = T0 + timedelta(seconds=i * 10)
        cmd = hp.update(now, frei_w=3000, wp=wp)
        if cmd.ww_soll_c is not None:    # senden, aber die Cloud übernimmt nie
            versuche += 1
            hp.schreiben_bestaetigt(now)
    assert hp.ww_boost is True
    assert versuche <= 4                 # ~1 Versuch je 15-min-Fenster


def test_bestaetigter_sollwert_wird_nicht_nachgeschrieben():
    """Keine Dauer-Übersteuerung: nach der Bestätigung schweigt das EMS."""
    hp = HeatPumpController(RegelConfig())
    wp = dict(SOMMER)
    _ticks(hp, wp, 3000, minuten=11)
    assert wp["ww_soll_c"] == 57.0
    wp["ww_soll_c"] = 52.0               # Leo stellt in der MyVaillant-App von Hand nach
    letzte = _ticks(hp, wp, 3000, minuten=30, start=T0 + timedelta(minutes=11))
    assert letzte.ww_soll_c is None and wp["ww_soll_c"] == 52.0


def test_ohne_verbindung_keine_befehle():
    """Fail-Safe E6: WP/HA weg → nichts entscheiden, nichts zurücksetzen."""
    hp = HeatPumpController(RegelConfig())
    wp = dict(SOMMER)
    _ticks(hp, wp, 3000, minuten=11)
    assert hp.ww_boost is True
    cmd = hp.update(T0 + timedelta(minutes=12), frei_w=0, wp=None)
    assert cmd.ww_soll_c is None and cmd.raum_soll_c is None
    assert hp.ww_boost is True
    assert "keine Verbindung" in cmd.grund


def test_status_ist_zweigeteilt():
    """Issue #1: Dashboard bekommt Warmwasser und Heizkreis getrennt."""
    hp = HeatPumpController(RegelConfig())
    st = hp.status(SOMMER)
    assert st["warmwasser"]["ist_c"] == 40.0 and st["warmwasser"]["soll_c"] == 45.0
    assert st["heizkreis"]["vorlauf_c"] == 27.5 and st["heizkreis"]["raum_ist_c"] == 26.0
    assert st["verbunden"] is True
    assert hp.status(None)["verbunden"] is False


def test_status_laeuft_erkennt_betrieb():
    """Dashboard dreht den WP-Lüfter nur, wenn die Anlage wirklich läuft."""
    hp = HeatPumpController(RegelConfig())
    assert hp.status(SOMMER)["laeuft"] is False                    # Heizkreis STANDBY, keine Sonderfunktion
    assert hp.status(WINTER)["laeuft"] is True                     # Heizkreis HEATING
    assert hp.status({**SOMMER, "ww_sonderfunktion": "Cylinder boost"})["laeuft"] is True
    assert hp.status({**SOMMER, "ww_sonderfunktion": "regular"})["laeuft"] is False
    assert hp.status(None)["laeuft"] is False


def test_status_laeuft_nicht_aus_gewuenschtem_boost():
    """Im Beobachtungsmodus wird nichts gesendet — der Lüfter darf nicht drehen."""
    hp = HeatPumpController(RegelConfig())
    wp = dict(SOMMER)
    _ticks(hp, wp, 3000, minuten=11, senden=False)
    assert hp.ww_boost is True                                     # das EMS *möchte* boosten
    assert hp.status(wp)["laeuft"] is False                        # die Anlage meldet aber Standby


# --- Adapter ----------------------------------------------------------------
def test_zahl_wandelt_ha_leerzustaende():
    assert _zahl("40.0") == 40.0
    assert _zahl("unavailable") is None and _zahl("unknown") is None and _zahl(None) is None


def test_vaillant_simulator_schreibt_sollwerte():
    sim = VaillantSimulator()
    assert asyncio.run(sim.read())["ww_soll_c"] == 45.0
    asyncio.run(sim.set_ww_soll(60))
    assert sim.commands == [("ww_soll", 60.0)] and sim.werte["ww_soll_c"] == 60.0
