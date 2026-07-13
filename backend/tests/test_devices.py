"""Adapter-Simulatoren + Factory (Fail-Safe-Verhalten, Sungrow-Stub)."""

import asyncio
from datetime import datetime, timedelta

import pytest

from leo_ems.devices.factory import build_adapters
from leo_ems.devices.forecast import ForecastSimulator
from leo_ems.devices.skoda import SkodaSimulator
from leo_ems.devices.sungrow import SungrowStub


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
