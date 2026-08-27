"""Energiebilanz: Tageszähler und E3DC-Nachimport (Issue #13).

Der schärfste Anspruch hier ist nicht Genauigkeit auf die Wattstunde, sondern
dass die Zahlen **nicht stillschweigend falsch** werden: keine erfundene Fläche
über einer Messlücke, keine Doppelzählung nach einem Neustart, keine vertauschte
Netzrichtung im Import.
"""

import asyncio
from datetime import date, datetime, timedelta

import pytest

from leo_ems.energy import (
    Energiezaehler,
    ImportBericht,
    e3dc_tag_umrechnen,
    importiere_e3dc_historie,
    leistungen_aus_status,
)
from leo_ems.store import Store

STATUS = {
    "p_pv_e3dc_w": 3000.0,
    "p_sungrow_w": 1000.0,
    "p_netz_w": -500.0,       # Einspeisung
    "p_batterie_w": 800.0,    # lädt
    "p_haus_w": 700.0,
    "p_wallbox_w": 2000.0,
}


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


# --- Vorzeichen -------------------------------------------------------------

def test_netz_und_batterie_werden_nach_richtung_getrennt():
    """Bezug und Einspeisung sind zwei Kanäle, nicht ein Wert mit Vorzeichen —
    sonst hebt sich in der Tagessumme auf, was Leo gerade unterscheiden will."""
    p = leistungen_aus_status(STATUS)
    assert p["netz_einspeisung_wh"] == 500.0
    assert p["netz_bezug_wh"] == 0.0
    assert p["batt_laden_wh"] == 800.0
    assert p["batt_entladen_wh"] == 0.0

    p2 = leistungen_aus_status({"p_netz_w": 1200.0, "p_batterie_w": -900.0})
    assert p2["netz_bezug_wh"] == 1200.0
    assert p2["netz_einspeisung_wh"] == 0.0
    assert p2["batt_entladen_wh"] == 900.0


# --- Integration ------------------------------------------------------------

def test_eine_stunde_konstante_leistung_ergibt_die_leistung_in_wh(store):
    z = Energiezaehler(store, schreib_intervall_s=0)
    t0 = datetime(2026, 8, 22, 10, 0, 0)
    # 60 Schritte à 60 s = 1 h. Der erste Tick setzt nur die Zeitbasis.
    for i in range(61):
        z.tick(STATUS, t0 + timedelta(seconds=60 * i))
    zeile = store.energie_tag_lesen("2026-08-22")
    assert zeile["pv_haus_wh"] == pytest.approx(3000.0, rel=1e-6)
    assert zeile["pv_garage_wh"] == pytest.approx(1000.0, rel=1e-6)
    assert zeile["haus_wh"] == pytest.approx(700.0, rel=1e-6)
    assert zeile["quelle"] == "ems"


def test_messluecke_wird_nicht_ueberbrueckt(store):
    """Nach einem Ausfall ist unbekannt, was in der Lücke passiert ist. Die
    letzte gemessene Leistung über Stunden fortzuschreiben würde eine Bilanz
    erfinden, die niemand geprüft hat — eine Lücke ist die ehrlichere Zahl."""
    z = Energiezaehler(store, schreib_intervall_s=0)
    t0 = datetime(2026, 8, 22, 10, 0, 0)
    z.tick(STATUS, t0)
    z.tick(STATUS, t0 + timedelta(hours=3))      # Lücke > MAX_LUECKE_S
    assert z.luecken == 1
    # Die Zeile darf entstehen — sie ist der Tag, an dem gemessen wird. Nur die
    # drei Stunden dürfen nicht darin auftauchen: 3000 W × 3 h wären 9 kWh
    # PV-Ertrag, den nie jemand gesehen hat.
    assert store.energie_tag_lesen("2026-08-22")["pv_haus_wh"] == 0.0


def test_neustart_zaehlt_den_tag_weiter_statt_neu(store):
    """Der Zähler hält den Tagesstand im Speicher. Ohne Rückladen begänne jeder
    Neustart bei null und überschriebe die schon gezählten Stunden mit einem
    kleineren Wert — der Tag würde nach jedem Add-on-Update kürzer."""
    t0 = datetime(2026, 8, 22, 10, 0, 0)
    z1 = Energiezaehler(store, schreib_intervall_s=0)
    for i in range(61):
        z1.tick(STATUS, t0 + timedelta(seconds=60 * i))

    z2 = Energiezaehler(store, schreib_intervall_s=0)      # „Neustart"
    t1 = t0 + timedelta(hours=2)
    for i in range(61):
        z2.tick(STATUS, t1 + timedelta(seconds=60 * i))
    assert store.energie_tag_lesen("2026-08-22")["pv_haus_wh"] == pytest.approx(6000.0, rel=1e-6)


def test_tageswechsel_schreibt_den_alten_tag_fest(store):
    """Die letzten Minuten vor Mitternacht dürfen nicht im Speicher verfallen."""
    z = Energiezaehler(store, schreib_intervall_s=3600)   # absichtlich träge
    t0 = datetime(2026, 8, 22, 23, 59, 0)
    z.tick(STATUS, t0)
    z.tick(STATUS, t0 + timedelta(seconds=60))            # 00:00 → neuer Tag
    zeile = store.energie_tag_lesen("2026-08-22")
    assert zeile is not None and zeile["pv_haus_wh"] > 0


def test_zaehler_wirft_nie(store):
    """Buchhaltung darf die Regelung nicht anhalten."""
    z = Energiezaehler(store)
    z.tick({"p_pv_e3dc_w": "kaputt"}, datetime(2026, 8, 22, 10, 0, 0))
    z.tick({"p_pv_e3dc_w": "kaputt"}, datetime(2026, 8, 22, 10, 0, 10))


# --- Aggregation ------------------------------------------------------------

def test_monats_und_jahressummen(store):
    for tag, wh in (("2026-07-30", 1000.0), ("2026-08-01", 2000.0), ("2026-08-02", 3000.0)):
        store.energie_tag_schreiben(tag, {"pv_haus_wh": wh}, "ems")
    monate = {m["periode"]: m for m in store.energie_gruppiert("monat")}
    assert monate["2026-08"]["pv_haus_wh"] == 5000.0
    assert monate["2026-08"]["tage"] == 2
    assert store.energie_gruppiert("jahr")[0]["pv_haus_wh"] == 6000.0


def test_wochen_gruppieren_auf_den_montag(store):
    """v0.14: Die Woche wird über ihren Montag identifiziert, nicht über eine
    Kalenderwochennummer — die ist zum Jahreswechsel mehrdeutig.

    2026-08-30 ist ein Sonntag, 2026-08-31 der Montag danach. Beide müssen in
    verschiedenen Wochen landen, obwohl sie im selben Monat liegen.
    """
    for tag, wh in (("2026-08-25", 1000.0), ("2026-08-30", 2000.0), ("2026-08-31", 4000.0)):
        store.energie_tag_schreiben(tag, {"pv_haus_wh": wh}, "ems")
    wochen = {w["periode"]: w for w in store.energie_gruppiert("woche")}
    assert sorted(wochen) == ["2026-08-24", "2026-08-31"]
    assert wochen["2026-08-24"]["pv_haus_wh"] == 3000.0   # Di + So derselben Woche
    assert wochen["2026-08-31"]["tage"] == 1


def test_fenster_grenzt_auf_tagesebene_ein(store):
    """`von`/`bis` schneiden Tage ab, nicht Perioden: Eine Randwoche erscheint
    mit den Tagen, die ins Fenster fallen — und `tage` sagt, wie viele das waren."""
    for tag in ("2026-08-30", "2026-08-31", "2026-09-01"):
        store.energie_tag_schreiben(tag, {"pv_haus_wh": 1000.0}, "ems")
    wochen = store.energie_gruppiert("woche", von="2026-08-31", bis="2026-12-31")
    assert [w["periode"] for w in wochen] == ["2026-08-31"]
    assert wochen[0]["tage"] == 2 and wochen[0]["pv_haus_wh"] == 2000.0


def test_tagesebene_liefert_dieselbe_zeilenform_wie_die_summen(store):
    """Das Diagramm soll seine Achse nicht von der Ebene abhängig machen müssen."""
    store.energie_tag_schreiben("2026-08-22", {"pv_haus_wh": 1000.0}, "ems")
    zeile = store.energie_gruppiert("tag")[0]
    assert zeile["periode"] == "2026-08-22" and zeile["tage"] == 1
    assert zeile["quellen"] == "ems"


# --- E3DC-Import ------------------------------------------------------------

# Ein plausibler Tag: 20 kWh PV, davon 8 eingespeist, 3 aus dem Netz geholt,
# 5 in die Batterie und 4 wieder heraus → Hausverbrauch 14 kWh.
E3DC_TAG = {
    "solarProduction": 20000.0, "consumption": 14000.0,
    "grid_power_in": 3000.0, "grid_power_out": 8000.0,
    "bat_power_in": 5000.0, "bat_power_out": 4000.0,
}


def test_import_erkennt_die_netzrichtung_aus_der_bilanz():
    """Aus `grid_power_in` allein ist nicht zu entscheiden, ob Bezug oder
    Einspeisung gemeint ist. Vertauscht fällt das in einer Jahresauswertung
    niemandem auf und macht sie wertlos — deshalb wird die Deutung gegen die
    mitgelieferte `consumption` geprüft statt geraten."""
    direkt = e3dc_tag_umrechnen(E3DC_TAG, getauscht=False)
    assert direkt["netz_bezug_wh"] == 3000.0
    assert direkt["netz_einspeisung_wh"] == 8000.0
    # Bilanz geht auf: 20000 + 3000 + 4000 − 8000 − 5000 = 14000
    assert direkt["haus_wh"] == 14000.0


def test_import_holt_tage_und_ueberschreibt_eigene_messung_nicht(store):
    from leo_ems.devices.e3dc import E3dcSimulator

    sim = E3dcSimulator()
    sim.historie = {"2026-08-20": E3DC_TAG, "2026-08-21": E3DC_TAG}
    store.energie_tag_schreiben("2026-08-21", {"pv_haus_wh": 111.0}, "ems")

    bericht = asyncio.run(importiere_e3dc_historie(
        sim, store, date(2026, 8, 20), date(2026, 8, 21),
        ImportBericht("2026-08-20", "2026-08-21"), pause_s=0,
    ))
    assert bericht.geschrieben == 1 and bericht.uebersprungen == 1
    assert bericht.richtung == "direkt"
    assert store.energie_tag_lesen("2026-08-20")["quelle"] == "e3dc"
    # Die eigene Messung kennt die Garagen-Anlage, die E3DC-Historie nicht.
    # Sie zu überschreiben würde den guten Wert durch den schlechteren ersetzen.
    assert store.energie_tag_lesen("2026-08-21")["pv_haus_wh"] == 111.0


def test_import_markiert_tage_ohne_garagen_kenntnis(store):
    """Nach der Inbetriebnahme der Garage ist der E3DC-Hausverbrauch zu klein.
    Diese Tage als vollwertig auszuweisen wäre die stillste Art, die Auswertung
    zu verfälschen — sie bekommen eine eigene Quellenkennung."""
    from leo_ems.devices.e3dc import E3dcSimulator

    sim = E3dcSimulator()
    sim.historie = {"2026-08-20": E3DC_TAG}
    asyncio.run(importiere_e3dc_historie(
        sim, store, date(2026, 8, 20), date(2026, 8, 20), pause_s=0,
        garage_seit=date(2026, 8, 13),
    ))
    assert store.energie_tag_lesen("2026-08-20")["quelle"] == "e3dc-ohne-garage"


def test_leere_tage_vor_der_inbetriebnahme_erzeugen_keine_nullzeilen(store):
    """Die Anlage antwortet für Tage vor ihrer Installation mit lauter Nullen.
    Als Zeile gespeichert sähen sie aus wie ein Tag ohne Sonne und ohne
    Verbrauch — und würden jeden Monatsschnitt nach unten ziehen."""
    from leo_ems.devices.e3dc import E3dcSimulator

    sim = E3dcSimulator()
    bericht = asyncio.run(importiere_e3dc_historie(
        sim, store, date(2020, 1, 1), date(2020, 1, 3), pause_s=0))
    assert bericht.leer == 3 and bericht.geschrieben == 0
    assert store.energie_tage() == []


# Der Tag, an dem der erste echte Import am 22.08.2026 falsch abbog: Bezug und
# Einspeisung liegen beide bei ~0,2 kWh, die Bilanz geht in beiden Deutungen
# gleich gut auf. Als Entscheidungsgrundlage ist er wertlos.
E3DC_TAG_MEHRDEUTIG = {
    "solarProduction": 12774.0, "consumption": 8924.0,
    "grid_power_in": 198.0, "grid_power_out": 196.0,
    "bat_power_in": 7228.0, "bat_power_out": 5662.0,
}
# Zwei Tage später: 35,7 kWh Einspeisung gegen 0,13 kWh Bezug. Hier ist die
# Richtung eindeutig — `grid_power_in` ist die EINSPEISUNG, also getauscht.
E3DC_TAG_EINDEUTIG = {
    "solarProduction": 50114.0, "consumption": 10050.0,
    "grid_power_in": 35665.0, "grid_power_out": 132.0,
    "bat_power_in": 8458.0, "bat_power_out": 7625.0,
}


def test_netzrichtung_entscheidet_der_ganze_zeitraum_nicht_der_erste_tag(store):
    """Regression zum ersten Live-Import (22.08.2026).

    Die Richtung wurde am ersten Tag festgelegt — und der war mehrdeutig
    (2,28 gegen 2,29 kWh Rest). Die Entscheidung fiel damit zufällig und stand
    für alle 1800 Tage. Ein vertauschter Netzbezug fällt in einer
    Jahresauswertung niemandem auf: 35 kWh Bezug an einem Tag mit 50 kWh
    Eigenerzeugung sieht nach einer Zahl aus, nicht nach einem Fehler.
    """
    from leo_ems.devices.e3dc import E3dcSimulator

    sim = E3dcSimulator()
    sim.historie = {"2021-08-23": E3DC_TAG_MEHRDEUTIG, "2021-08-25": E3DC_TAG_EINDEUTIG}
    bericht = asyncio.run(importiere_e3dc_historie(
        sim, store, date(2021, 8, 23), date(2021, 8, 25), pause_s=0))

    assert bericht.richtung == "getauscht"
    assert bericht.rest_getauscht_kwh < bericht.rest_direkt_kwh
    # Und der eindeutige Tag steht danach richtig herum in der Tabelle.
    z = store.energie_tag_lesen("2021-08-25")
    assert z["netz_einspeisung_wh"] == 35665.0
    assert z["netz_bezug_wh"] == 132.0


def test_bericht_weist_die_belastbarkeit_der_zuordnung_aus(store):
    """Der Rest beider Deutungen steht im Bericht. Liegen sie dicht beieinander,
    ist die Netzrichtung nicht belegt — das muss ablesbar sein und nicht in
    einem stillen `richtung`-Feld verschwinden."""
    from leo_ems.devices.e3dc import E3dcSimulator

    sim = E3dcSimulator()
    sim.historie = {"2021-08-25": E3DC_TAG_EINDEUTIG}
    b = asyncio.run(importiere_e3dc_historie(
        sim, store, date(2021, 8, 25), date(2021, 8, 25), pause_s=0))
    assert b.rest_direkt_kwh > 10 * b.rest_getauscht_kwh    # klar unterscheidbar
    assert b.phase == "fertig"
