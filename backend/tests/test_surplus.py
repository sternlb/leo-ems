"""Abnahmekriterien Spec §2 (REQ-001)."""

from leo_ems.config import RegelConfig
from leo_ems.planner import berechne_ueberschuss

CFG = RegelConfig()  # Baseline-Defaults: residual 100 W, prioritySoc 25 %


def test_akzeptanz_spec_2():
    """Spec §2: P_netz=−3000 (Einspeisung), P_lade=0, SoC≥25 % ⇒ 2900 W."""
    assert berechne_ueberschuss(0, -3000, 0, 61, CFG) == 2900


def test_batterie_vorrang_unter_priority_soc():
    """Unter prioritySoc zählt Batterie-Ladeleistung NICHT als Überschuss."""
    mit_vorrang = berechne_ueberschuss(0, -1000, 2000, 20, CFG)
    ohne_vorrang = berechne_ueberschuss(0, -1000, 2000, 30, CFG)
    assert mit_vorrang == 900          # Batterie lädt weiter, EV bekommt nur Einspeisung
    assert ohne_vorrang == 2900        # EV darf der Batterie die 2 kW wegnehmen


def test_laufende_ladung_zaehlt_zum_ueberschuss():
    """P_lade_ist gehört zum verfügbaren Budget (sonst würde Laden sich selbst abwürgen)."""
    assert berechne_ueberschuss(4000, -100, 0, 50, CFG) == 4000


def test_bezug_ergibt_negativen_ueberschuss():
    assert berechne_ueberschuss(0, 500, 0, 50, CFG) == -600
