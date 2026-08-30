"""Reihenfolge der Überschussverwertung (Issue #16, docs/priorisierung.md).

Der schärfste Anspruch ist nicht, dass jede Reihenfolge funktioniert, sondern
dass die **Vorgabe nichts ändert**: Ein Update darf das Verhalten von v0.17
nicht verschieben, solange niemand umstellt. Alles Weitere ist die Wirkung
einer bewussten Einstellung.
"""

import asyncio
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest

from leo_ems.config import RegelConfig
from leo_ems.core.loop import ControlLoop
from leo_ems.devices.e3dc import E3dcSimulator
from leo_ems.devices.goe import GoeSimulator
from leo_ems.devices.skoda import SkodaSimulator
from leo_ems.devices.vaillant import VaillantSimulator
from leo_ems.planner.prioritaet import (
    STANDARD, normalisiere, pruefe, verbraucher_reihenfolge,
)
from leo_ems.planner import ChargingRule
from leo_ems.safety import SafetyGuard
from leo_ems.store import Store

T0 = datetime(2026, 8, 30, 12, 0)


# --- Die reine Rechnung ------------------------------------------------------

def test_standardliste_ergibt_das_verhalten_bis_v017():
    cfg = RegelConfig()
    assert verbraucher_reihenfolge(list(STANDARD), cfg) == [("wallbox", 25), ("warmwasser", 25)]


def test_batterie_voll_nach_oben_gilt_fuer_alles_darunter():
    """Ein Tor wirkt auf alles, was unter ihm steht — und die höchste Schwelle
    gewinnt, wenn mehrere übereinander liegen."""
    cfg = RegelConfig()
    liste = ["batterie_vorrang", "wallbox", "batterie_voll", "warmwasser"]
    assert verbraucher_reihenfolge(liste, cfg) == [("wallbox", 25), ("warmwasser", 100)]


def test_verbraucher_ueber_jedem_tor_sieht_die_batterieleistung_sofort():
    """Steht kein Tor über einem Verbraucher, darf er der Batterie ihre
    Ladeleistung von der ersten Kilowattstunde an wegnehmen."""
    cfg = RegelConfig()
    liste = ["wallbox", "batterie_vorrang", "warmwasser", "batterie_voll"]
    assert verbraucher_reihenfolge(liste, cfg) == [("wallbox", 0), ("warmwasser", 25)]


def test_torschwelle_folgt_der_konfiguration():
    assert verbraucher_reihenfolge(list(STANDARD), RegelConfig(priority_soc_pct=60))[0] == ("wallbox", 60)


@pytest.mark.parametrize("kaputt, wort", [
    (["wallbox", "wallbox", "warmwasser", "batterie_voll"], "doppelt"),
    (["wallbox", "warmwasser", "batterie_voll"], "fehlende"),
    (["wallbox", "warmwasser", "batterie_voll", "batterie_vorrang", "keller"], "unbekannt"),
    ("wallbox", "Liste"),
])
def test_unsinn_wird_benannt_nicht_repariert(kaputt, wort):
    """Eine unvollständige Liste stillschweigend zu ergänzen wäre schlimmer als
    eine Fehlermeldung: Der fehlende Eintrag landete an einer Stelle, die
    niemand gewählt hat."""
    with pytest.raises(ValueError, match=wort):
        pruefe(kaputt)


def test_lesepfad_faellt_auf_die_vorgabe_zurueck():
    """Eine Konfiguration aus einer älteren Version kennt das Feld nicht — das
    darf die Regelschleife nicht anhalten."""
    assert normalisiere(None) == list(STANDARD)
    assert normalisiere(["wallbox"]) == list(STANDARD)


# --- Wirkung in der Regelschleife -------------------------------------------

EINSPEISUNG_W = 3000.0


def _loop(prioritaet=None, soc_fahrzeug=60.0, **kw):
    cfg = RegelConfig(read_only=False, wp_ww_aktiv=True, **kw)
    if prioritaet is not None:
        cfg.prioritaet = prioritaet
    store = Store(Path(tempfile.mkdtemp()) / "prio.db")
    # 3 kW Einspeisung, Batterie über der Torschwelle (25 %), Speicher kalt
    # genug für einen Boost, Auto angesteckt.
    e3dc = E3dcSimulator(p_netz_w=-EINSPEISUNG_W, p_batterie_w=0, soc_pct=80)
    goe = GoeSimulator(connected=True)
    wp = VaillantSimulator(ww_ist_c=40.0, ww_soll_c=45.0, aussen_c=25.0)
    return ControlLoop(cfg, SafetyGuard(cfg), store,
                       {"e3dc": e3dc, "goe": goe, "vaillant": wp,
                        "skoda": SkodaSimulator(soc_pct=soc_fahrzeug)})


def _ticks(loop, n=80):
    """80 Ticks à 10 s = 13 Minuten.

    Nötig, weil beide Verbraucher entprellt sind: die Wallbox 60 s (Spec §4.1),
    der WW-Boost 600 s (`wp_entprellung_s`). Mit weniger Ticks prüft man die
    Entprellung statt der Reihenfolge.

    Die Anlage bildet dabei den WP-Verbrauch nach: Ein laufender Boost zieht
    rund 2 kW und drückt **genau den Überschuss, den das EMS misst**. Ohne das
    bliebe der Simulator bei 3 kW stehen, das Budget wäre in beiden
    Reihenfolgen gleich groß — und der Test bewiese nichts.
    """
    e3dc = loop.adapters["e3dc"]
    for i in range(n):
        laeuft = loop.heatpump.ww_boost or loop.heatpump.hk_boost
        e3dc.p_netz_w = -EINSPEISUNG_W + (loop.cfg.wp_leistung_w if laeuft else 0)
        asyncio.run(loop.tick(T0 + timedelta(seconds=10 * i)))
    return loop._last_status


def test_status_weist_reihenfolge_und_zuteilung_aus():
    """Ohne die Zuteilung daneben wäre die Liste eine Behauptung: Man sähe, was
    gelten soll, aber nicht, was daraus geworden ist."""
    st = _ticks(_loop())
    assert st["prioritaet"] == list(STANDARD)
    assert set(st["zuteilung_w"]) == {"wallbox", "warmwasser"}


def test_vorgabe_das_auto_zuerst():
    """Abnahmekriterium 3: Bei 3 kW lädt das Auto, der Boost startet nicht —
    das ist die Entscheidung aus Issue #6 und bleibt die Vorgabe."""
    st = _ticks(_loop())
    assert st["laedt"] is True
    assert st["zuteilung_w"]["wallbox"] > 2000
    assert st["zuteilung_w"]["warmwasser"] == 0


def test_warmwasser_oben_kehrt_die_entscheidung_um():
    """Abnahmekriterium 2: Dieselbe Lage, Warmwasser über Wallbox. Der Boost
    läuft, und für das Auto bleibt zu wenig für den Mindestladestrom."""
    st = _ticks(_loop(["batterie_vorrang", "warmwasser", "wallbox", "batterie_voll"]))
    assert st["zuteilung_w"]["warmwasser"] > 0
    assert st["laedt"] is False


def test_garantieladung_schlaegt_die_liste():
    """Abnahmekriterium 5: Eine Zusage auf eine Uhrzeit ist keine Optimierung.
    Auch mit Warmwasser oben lädt das Auto, wenn die Garantie greift."""
    loop = _loop(["batterie_vorrang", "warmwasser", "wallbox", "batterie_voll"],
                 soc_fahrzeug=20.0)
    loop.store.add_rule(ChargingRule(weekdays=frozenset(range(7)),
                                 departure=time(13, 0), soc_min_pct=90))
    st = _ticks(loop)
    assert st["garantieladung"] is True and st["laedt"] is True
