"""Adapter-Simulatoren + Factory (Fail-Safe-Verhalten, Sungrow-Stub)."""

import asyncio
from datetime import datetime, timedelta

import pytest

from leo_ems.devices.factory import build_adapters
from leo_ems.devices.forecast import ForecastSimulator
from leo_ems.devices.skoda import SkodaAdapter, SkodaSimulator
from leo_ems.devices.sungrow import SungrowStub
from leo_ems.devices.vaillant import HA_KANDIDATEN, VaillantAdapter


def test_skoda_simulator_liest_soc():
    sim = SkodaSimulator(soc_pct=72)
    assert asyncio.run(sim.read())["soc_pct"] == 72


def test_skoda_simulator_ausfall_wirft():
    """E3: Ausfall wird als Exception signalisiert → Loop hält Betrieb unverändert."""
    sim = SkodaSimulator()
    sim.available = False
    with pytest.raises(ConnectionError):
        asyncio.run(sim.read())


def test_sungrow_stub_liefert_null():
    """Spec §6: bis zur Installation konstant 0 W."""
    stub = SungrowStub()
    data = asyncio.run(stub.read())
    assert data["power_w"] == 0.0 and data["installiert"] is False


def test_forecast_erwartete_wh_zwischen():
    watts = {
        "2026-07-16T08:00:00": 1000,
        "2026-07-16T09:00:00": 2000,
        "2026-07-16T10:00:00": 3000,
    }
    sim = ForecastSimulator(watts)
    von = datetime(2026, 7, 16, 8, 30)
    bis = datetime(2026, 7, 16, 10, 0)
    assert sim.erwartete_wh_bis(von, bis) == 5000  # 09:00 + 10:00


def test_factory_leere_config_nur_sungrow_stub():
    """Ohne Verbindungsdaten werden keine echten Adapter gebaut — nur der Sungrow-Stub."""
    adapters = build_adapters({})
    assert set(adapters) == {"sungrow"}
    assert isinstance(adapters["sungrow"], SungrowStub)


def test_factory_goe_wird_gebaut():
    adapters = build_adapters({"goe_host": "192.168.178.50"})
    assert "goe" in adapters and adapters["goe"].host == "192.168.178.50"


# --- Vaillant: Zugangssuche zur HA-API (v0.6.2) --------------------------------
# Welcher Weg zu Home Assistant führt, hängt vom Netzmodus des Add-ons ab
# (host_network hat keine Docker-DNS). Deshalb wird gesucht statt geraten.


def _adapter_mit_antworten(antworten: dict):
    """Vaillant-Adapter, dessen Erreichbarkeitsprobe aus einer Tabelle antwortet.

    Wert = HTTP-Status; eine Exception-Klasse steht für „Adresse gibt es hier nicht".
    """
    adapter = VaillantAdapter(token="tok")
    async def erreichbar(basis: str) -> int:
        antwort = antworten.get(basis, OSError)
        if isinstance(antwort, type) and issubclass(antwort, Exception):
            raise antwort("nicht erreichbar")
        return antwort
    adapter._erreichbar = erreichbar
    return adapter


def test_vaillant_nimmt_den_ersten_weg_der_antwortet():
    # Supervisor-DNS scheitert (host_network), der Proxy per IP antwortet
    adapter = _adapter_mit_antworten({HA_KANDIDATEN[1]: 200})
    assert asyncio.run(adapter._basis()) == HA_KANDIDATEN[1]
    assert adapter.letzter_fehler is None


def test_vaillant_ueberspringt_abgelehnte_wege():
    """401 heißt „Weg richtig, Token abgelehnt" — dann zählt der nächste Kandidat."""
    adapter = _adapter_mit_antworten({HA_KANDIDATEN[1]: 401, HA_KANDIDATEN[2]: 200})
    assert asyncio.run(adapter._basis()) == HA_KANDIDATEN[2]


def test_vaillant_meldet_alle_versuchten_wege_im_klartext():
    """Kein Weg da → der Fehler nennt jeden Versuch, sonst ist er nicht suchbar."""
    adapter = _adapter_mit_antworten({HA_KANDIDATEN[1]: 401})
    with pytest.raises(ConnectionError) as fehler:
        asyncio.run(adapter._basis())
    text = str(fehler.value)
    assert "HTTP 401" in text
    assert all(k in text for k in HA_KANDIDATEN)
    # Backoff: der nächste Tick sucht nicht erneut, sondern meldet denselben Grund
    assert adapter._suche_bis is not None
    with pytest.raises(ConnectionError):
        asyncio.run(adapter._basis())


def test_vaillant_explizite_basis_url_wird_nicht_gesucht():
    """Mit gesetzter ha_base_url (Entwicklung am PC) wird nichts durchprobiert."""
    adapter = VaillantAdapter(base_url="http://192.168.178.150:8123/api/", token="tok")
    assert asyncio.run(adapter._basis()) == "http://192.168.178.150:8123/api"


def test_vaillant_token_herkunft_nennt_quelle_ohne_geheimnis(monkeypatch):
    """Die Diagnose muss sagen, WOHER der Token kommt — aber nie, wie er lautet."""
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setenv("HASSIO_TOKEN", "alter-name-123")
    adapter = VaillantAdapter()
    assert adapter.token == "alter-name-123"          # alter Name wird noch akzeptiert
    herkunft = adapter.token_herkunft()
    assert "HASSIO_TOKEN" in herkunft and "alter-name-123" not in herkunft

    monkeypatch.delenv("HASSIO_TOKEN")
    leer = VaillantAdapter()
    assert leer.token == "" and "kein Token" in leer.token_herkunft()


# --- Škoda: myskoda hat das SoC-Feld umbenannt (v0.6.2) -------------------------


class _Batterie:
    def __init__(self, **felder):
        for name, wert in felder.items():
            setattr(self, name, wert)


def test_skoda_liest_soc_unter_beiden_feldnamen():
    """Neuer und alter (vertippter) myskoda-Feldname — beide müssen gehen."""
    assert SkodaAdapter._soc(_Batterie(state_of_charge_in_percent=63)) == 63.0
    assert SkodaAdapter._soc(_Batterie(state_of_charged_in_percent=41)) == 41.0


def test_skoda_unbekanntes_soc_feld_wird_als_ausfall_gemeldet():
    """Kein bekanntes Feld → E3 (Betrieb unverändert), aber mit Klartext-Grund.

    Bis v0.6.1 flog hier eine AttributeError, die die Regelschleife stumm
    geschluckt hat — deshalb war `soc_fahrzeug` seit dem Go-live immer null.
    """
    with pytest.raises(ConnectionError) as fehler:
        SkodaAdapter._soc(_Batterie(irgendwas=1))
    assert "keinen SoC" in str(fehler.value)
