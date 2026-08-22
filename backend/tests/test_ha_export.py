"""Sensor-Export nach Home Assistant (v0.12.0).

Der Export ist Anzeige, keine Regelung — die schärfste Anforderung ist deshalb
nicht Korrektheit der Werte, sondern dass er die Regelschleife unter keinen
Umständen anhält oder mitreißt.
"""

import asyncio
from datetime import datetime, timedelta

from leo_ems.ha_export import HaSensorExport, sensoren_aus_status

STATUS = {
    "p_pv_e3dc_w": 6995.0,
    "p_sungrow_w": 3229.0,
    "sungrow": {"installiert": True, "gesamtertrag_kwh": 1.0, "tagesertrag_kwh": 1.5},
}


# --- Abbildung Status → Sensoren --------------------------------------------

def test_beide_anlagen_und_die_summe_werden_exportiert():
    """Leos Anforderung: erste Anlage, zweite Anlage und ein gemeinsamer Wert."""
    s = sensoren_aus_status(STATUS)
    assert s["sensor.pv_haus_leistung"]["state"] == 6995
    assert s["sensor.pv_garage_leistung"]["state"] == 3229
    assert s["sensor.pv_gesamt_leistung"]["state"] == 10224   # 6995 + 3229


def test_sensoren_tragen_die_attribute_fuer_diagramm_und_statistik():
    """Ohne `state_class` zeichnet der Recorder nichts auf — dann bliebe jedes
    Diagramm leer, obwohl die Entity im Zustandsbild sichtbar ist."""
    leistung = sensoren_aus_status(STATUS)["sensor.pv_gesamt_leistung"]["attributes"]
    assert leistung["unit_of_measurement"] == "W"
    assert leistung["device_class"] == "power"
    assert leistung["state_class"] == "measurement"

    ertrag = sensoren_aus_status(STATUS)["sensor.pv_garage_ertrag_gesamt"]["attributes"]
    # Zählerstand, nicht Messwert: `total_increasing` ist die Bedingung dafür,
    # dass die Garagen-Anlage im HA-Energie-Dashboard auftauchen kann.
    assert ertrag["state_class"] == "total_increasing"
    assert ertrag["device_class"] == "energy"


def test_fehlender_sungrow_ergibt_null_statt_luecke():
    """Fail-Safe E5: Bei Ausfall steht die Erzeugung auf 0. Der Sensor muss
    diesen 0-Wert auch schreiben — eine Lücke im Diagramm sähe aus wie ein
    Ausfall des Exports, nicht wie ein Ausfall des Wechselrichters."""
    s = sensoren_aus_status({"p_pv_e3dc_w": 4000.0})
    assert s["sensor.pv_garage_leistung"]["state"] == 0
    assert s["sensor.pv_gesamt_leistung"]["state"] == 4000
    # Ohne Zählerstand kein Energie-Sensor — ein erfundener Wert würde die
    # Statistik dauerhaft verfälschen (total_increasing kennt keinen Rücksprung).
    assert "sensor.pv_garage_ertrag_gesamt" not in s


# --- Takt und Robustheit -----------------------------------------------------

def test_export_drosselt_sich_auf_das_intervall():
    """Die Regelschleife tickt alle 10 s; jeder Tick geschrieben würde die
    HA-Datenbank mit dem Dreifachen an Zustandswechseln füllen."""
    ex = HaSensorExport(base_url="http://x/api", token="t", intervall_s=30)
    t0 = datetime(2026, 8, 22, 12, 0, 0)
    assert ex.faellig(t0)
    ex._zuletzt = t0
    assert not ex.faellig(t0 + timedelta(seconds=10))
    assert not ex.faellig(t0 + timedelta(seconds=29))
    assert ex.faellig(t0 + timedelta(seconds=30))


def test_push_wirft_nie_und_merkt_sich_den_grund():
    """Der Kern der Sache: Ein HA-Ausfall darf die Regelschleife nicht
    abbrechen. Der Port ist tot — der Fehler muss als Text landen, nicht als
    Exception hochkommen."""
    async def lauf():
        ex = HaSensorExport(base_url="http://127.0.0.1:1/api", token="t", timeout_s=0.3)
        n = await ex.push(STATUS)
        fehler = ex.letzter_fehler
        await ex.schliessen()
        return n, fehler

    geschrieben, fehler = asyncio.run(lauf())
    assert geschrieben == 0
    assert fehler is not None


def test_ohne_token_wird_gar_nicht_erst_versucht():
    """Ohne `SUPERVISOR_TOKEN` gibt es kein Home Assistant, in das exportiert
    werden könnte — jeder Kandidat liefe in 401 oder Timeout. Vier vergebliche
    Verbindungsversuche je 30 s wären nur Last ohne jede Aussicht."""
    ex = HaSensorExport(token="")
    assert ex.aktiv is False
    assert asyncio.run(ex.push(STATUS)) == 0
    assert "kein HA-Token" in (ex.letzter_fehler or "")


def test_nebenlaeufiger_push_haelt_den_tick_nicht_auf():
    """Die eigentliche Anforderung: Der Aufruf kehrt sofort zurück, auch wenn
    das Ziel tot ist. Wartete die Regelschleife hier, stünde sie bei hängendem
    HA bis zu 12 s pro Tick — bei 10 s Tick-Intervall hielte die Anzeige die
    Regelung an."""
    async def lauf():
        ex = HaSensorExport(base_url="http://127.0.0.1:1/api", token="t", timeout_s=5)
        beginn = asyncio.get_running_loop().time()
        gestartet = ex.push_nebenlaeufig(STATUS)
        dauer = asyncio.get_running_loop().time() - beginn
        # Zweiter Anstoß darf keinen weiteren Task danebenstellen
        ex._zuletzt = None
        nochmal = ex.push_nebenlaeufig(STATUS)
        await ex.schliessen()
        return gestartet, dauer, nochmal

    gestartet, dauer, nochmal = asyncio.run(lauf())
    assert gestartet is True
    assert dauer < 0.1, f"Aufruf hat {dauer:.2f}s blockiert statt sofort zurückzukehren"
    assert nochmal is False, "zweiter Task wurde neben den laufenden gestellt"


def test_push_ueberspringt_wenn_nicht_faellig_ohne_netzzugriff():
    """Nicht fällig = gar kein HTTP. Sonst liefe der Verbindungsversuch alle
    10 s ins Leere, wenn HA nicht erreichbar ist."""
    ex = HaSensorExport(base_url="http://127.0.0.1:1/api", token="t", intervall_s=30)
    t0 = datetime(2026, 8, 22, 12, 0, 0)
    ex._zuletzt = t0
    assert asyncio.run(ex.push(STATUS, t0 + timedelta(seconds=5))) == 0
    assert ex.letzter_fehler is None   # kein Versuch, also auch kein Fehler
