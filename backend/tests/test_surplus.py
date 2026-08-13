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


def test_batterieentladung_ist_kein_ueberschuss():
    """Sonst speist sich die Ladung selbst aus der Hausbatterie (Spec §5.1).

    Deckt die Batterie beim Laden den Netzbezug (dynamische Entladegrenze), steht
    das Netz auf 0 — ohne diesen Abzug sähe die Wallbox die Deckung als PV und
    hielte die Ladung am Laufen, bis die Batterie leer ins Auto gelaufen wäre.
    """
    # 1380 W Wallbox, Netz auf 0, weil die Batterie 800 W beisteuert
    assert berechne_ueberschuss(1380, 0, -800, 60, CFG) == 480
    # ohne Deckung stünden dieselben 800 W im Netzbezug — gleiches Ergebnis
    assert berechne_ueberschuss(1380, 800, 0, 60, CFG) == 480


# --- Budget für den Modus PV+Batterie (Issue #11) ----------------------------
def test_mit_batterie_ignoriert_den_batterie_term_in_beiden_vorzeichen():
    """Genau umgekehrt zum Test darüber: hier IST die Entladung Budget."""
    # Entladung: 1380 W Wallbox, davon 800 W aus der Batterie
    assert berechne_ueberschuss(1380, 0, -800, 60, CFG, mit_batterie=True) == 1280
    # Ladung: der Zuschlag ab prioritySoc entfällt ebenfalls, er steckt schon
    # im Netz-Term — 2000 W wandern in die Batterie, das Netz zeigt sie an
    assert berechne_ueberschuss(0, -3000, 2000, 61, CFG, mit_batterie=True) == 2900


def test_mit_batterie_ist_stationaer_selbstkonsistent():
    """Das Budget darf sich nicht selbst wegregeln (der Ratchet aus v0.9.0).

    Auto zieht 5 kW, davon 2 kW PV und 3 kW Batterie → Netz ≈ 0. Rechnet man das
    Ergebnis zurück in denselben Zustand, muss dasselbe Budget herauskommen.
    """
    budget = berechne_ueberschuss(5000, 0, -3000, 60, CFG, mit_batterie=True)
    assert budget == 4900
    assert berechne_ueberschuss(4900, 0, -2900, 60, CFG, mit_batterie=True) == 4800


def test_mit_batterie_faellt_wenn_die_batterie_am_deckel_ist():
    """Selbstbegrenzung: stößt die Batterie an ihre Grenze, wird Netzbezug
    sichtbar und das Budget sinkt — ohne Sonderfall im Code."""
    assert berechne_ueberschuss(5000, 1200, -3000, 60, CFG, mit_batterie=True) == 3700
