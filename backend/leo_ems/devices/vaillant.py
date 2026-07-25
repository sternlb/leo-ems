"""Vaillant aroTHERM über Home Assistant (REQ-013/014, ADR-004).

Das Vaillant-Internetmodul hängt am eBUS — es gibt keinen SG-Ready-Kontakt und
keinen lokalen Steuerweg (docs/systems/vaillant.md). Steuerweg ist die
MyVaillant-Cloud, und die hängt über die MyVaillant-Integration bereits in Home
Assistant. Statt einen zweiten Cloud-Client zu bauen (zweiter Login, zweites
Anfrage-Budget) geht Leo-EMS über die HA-REST-API: lesen aus den Sensoren,
schreiben über die Services `water_heater` / `climate`.

Zugang: als Add-on über den Supervisor-Proxy `http://172.30.32.2/core/api` mit
dem `SUPERVISOR_TOKEN` — dafür braucht das Add-on `homeassistant_api: true`
(config.yaml). Basis-URL und Token sind über die Add-on-Optionen überschreibbar
(Entwicklung am PC, Zugriff über einen Long-Lived Token).

Ratenlimit (REQ-014): LESEN geht gegen die lokale HA-Instanz und ist billig —
deshalb der eigene Poll-Takt von 60 s statt der 10 s der Regelschleife.
SCHREIBEN geht über die MyVaillant-Cloud; gedrosselt wird das im
HeatPumpController (`wp_cloud_min_gap_s`), hier wird nur mitgezählt.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta

from .base import DeviceAdapter

try:  # aiohttp nur im echten Betrieb nötig, nicht für Tests/Simulator
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None

# Feste Adresse des Supervisor-Proxys. Im Host-Network-Modus (config.yaml) gibt
# es keine Docker-DNS für den Namen „supervisor“ — die IP funktioniert immer.
SUPERVISOR_CORE_URL = "http://172.30.32.2/core/api"

# Steuer-Entities der MyVaillant-Integration (über die Add-on-Optionen änderbar).
WW_ENTITY = "water_heater.home_domestic_hot_water_0"
ZONE_ENTITY = "climate.home_zone_zone_1_circuit_0_climate"

# Lese-Entities, abgelesen an Leos HA-Instanz am 2026-07-25.
# Feld -> (entity_id, numerisch?)
SENSOREN: dict[str, tuple[str, bool]] = {
    # Warmwasser
    "ww_ist_c": ("sensor.home_domestic_hot_water_0_tank_temperature", True),
    "ww_soll_c": ("sensor.home_domestic_hot_water_0_setpoint", True),
    "ww_modus": ("sensor.home_domestic_hot_water_0_operation_mode", False),
    "ww_sonderfunktion": ("sensor.home_domestic_hot_water_0_current_special_function", False),
    # Heizkreis
    "hk_vorlauf_c": ("sensor.home_circuit_0_current_flow_temperature", True),
    "hk_vorlauf_soll_c": ("sensor.heizungskeller_home_circuit_0_flow_temperature_setpoint", True),
    "hk_zustand": ("sensor.home_circuit_0_state", False),
    "hk_modus": ("sensor.home_zone_zone_1_circuit_0_heating_operating_mode", False),
    "raum_ist_c": ("sensor.home_zone_zone_1_circuit_0_current_temperature", True),
    "raum_soll_c": ("sensor.home_zone_zone_1_circuit_0_desired_temperature", True),
    # Umfeld
    "aussen_c": ("sensor.home_outdoor_temperature", True),
    "cop": ("sensor.home_heating_energy_efficiency", True),
    "api_anfragen": ("sensor.vaillant_api_request_count", True),
}

# HA liefert für nicht gelieferte Werte diese Zustände statt einer Zahl
LEER = ("unknown", "unavailable", "none", "None", "")


def _zahl(state: str | None) -> float | None:
    if state is None or state in LEER:
        return None
    try:
        return float(state)
    except (TypeError, ValueError):
        return None


class VaillantAdapter(DeviceAdapter):
    """Liest die WP-Sensoren aus HA und schreibt Sollwerte über HA-Services."""

    name = "vaillant"

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        ww_entity: str = WW_ENTITY,
        zone_entity: str = ZONE_ENTITY,
        poll_s: float = 60.0,
        timeout_s: float = 10.0,
    ):
        self.base_url = (base_url or SUPERVISOR_CORE_URL).rstrip("/")
        self.token = token or os.environ.get("SUPERVISOR_TOKEN", "")
        self.ww_entity = ww_entity
        self.zone_entity = zone_entity
        self.schreibzugriffe = 0          # Zähler fürs Protokoll (REQ-014)
        self._poll_s = poll_s
        self._timeout_s = timeout_s
        self._last: datetime | None = None
        self._cache: dict | None = None
        self._session = None

    # --- HTTP ---------------------------------------------------------------
    async def _session_holen(self):
        if aiohttp is None:  # pragma: no cover
            raise RuntimeError("aiohttp nicht installiert")
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout_s),
                headers={"Authorization": f"Bearer {self.token}"},
            )
        return self._session

    async def _state(self, entity_id: str) -> str | None:
        """Rohzustand einer Entity; None, wenn HA sie nicht (mehr) kennt."""
        sess = await self._session_holen()
        async with sess.get(f"{self.base_url}/states/{entity_id}") as resp:
            if resp.status == 404:
                return None
            resp.raise_for_status()
            return (await resp.json()).get("state")

    async def _service(self, domain: str, service: str, daten: dict) -> None:
        sess = await self._session_holen()
        async with sess.post(f"{self.base_url}/services/{domain}/{service}", json=daten) as resp:
            resp.raise_for_status()
        self.schreibzugriffe += 1

    # --- DeviceAdapter ------------------------------------------------------
    async def read(self) -> dict:
        """Alle WP-Werte auf einmal. Eigener Poll-Takt: zwischen zwei Abfragen
        liefert der Cache — die Cloud aktualisiert ohnehin nur minütlich."""
        if self._cache is not None and self._last is not None:
            if datetime.now() - self._last < timedelta(seconds=self._poll_s):
                return self._cache

        felder = list(SENSOREN)
        roh = await asyncio.gather(
            *(self._state(SENSOREN[f][0]) for f in felder), return_exceptions=True
        )
        if all(isinstance(r, Exception) for r in roh):
            # Home Assistant nicht erreichbar → Fail-Safe E6 in der Regelschleife
            raise ConnectionError("Home Assistant nicht erreichbar (Vaillant-Adapter)")

        daten: dict = {}
        for feld, wert in zip(felder, roh):
            if isinstance(wert, Exception):
                daten[feld] = None
                continue
            numerisch = SENSOREN[feld][1]
            daten[feld] = _zahl(wert) if numerisch else (None if wert in LEER else wert)

        self._last = datetime.now()
        self._cache = daten
        return daten

    @property
    def last_update(self) -> datetime | None:
        return self._last

    # --- Stellgrößen (gehen über die MyVaillant-Cloud!) ---------------------
    async def set_ww_soll(self, temperatur_c: float) -> None:
        """Warmwasser-Sollwert (35–70 °C laut Entity-Attributen)."""
        await self._service(
            "water_heater", "set_temperature",
            {"entity_id": self.ww_entity, "temperature": round(float(temperatur_c), 1)},
        )
        self._cache = None  # nächster read() holt frisch, damit die Bestätigung ankommt

    async def set_raum_soll(self, temperatur_c: float) -> None:
        """Raum-Solltemperatur der Zone (MyVaillant setzt das als Quick-Veto)."""
        await self._service(
            "climate", "set_temperature",
            {"entity_id": self.zone_entity, "temperature": round(float(temperatur_c), 1)},
        )
        self._cache = None

    async def close(self) -> None:  # pragma: no cover
        if self._session is not None:
            await self._session.close()


class VaillantSimulator(DeviceAdapter):
    """Simulator für Tests/Entwicklung (kein Netz). Zeichnet Sollwerte auf."""

    name = "vaillant"

    def __init__(self, ww_ist_c: float = 40.0, ww_soll_c: float = 45.0,
                 raum_ist_c: float = 21.0, raum_soll_c: float = 0.0,
                 aussen_c: float = 12.0):
        self.werte = {
            "ww_ist_c": ww_ist_c, "ww_soll_c": ww_soll_c,
            "ww_modus": "Auto", "ww_sonderfunktion": None,
            "hk_vorlauf_c": 27.5, "hk_vorlauf_soll_c": 0.0,
            "hk_zustand": "STANDBY", "hk_modus": "Auto",
            "raum_ist_c": raum_ist_c, "raum_soll_c": raum_soll_c,
            "aussen_c": aussen_c, "cop": 3.4, "api_anfragen": 277.0,
        }
        self.available = True
        self.commands: list[tuple] = []
        self.schreibzugriffe = 0
        self._last: datetime | None = None

    async def read(self) -> dict:
        if not self.available:
            raise ConnectionError("Vaillant-Simulator: nicht erreichbar")
        self._last = datetime.now()
        return dict(self.werte)

    @property
    def last_update(self) -> datetime | None:
        return self._last

    async def set_ww_soll(self, temperatur_c: float) -> None:
        self.werte["ww_soll_c"] = float(temperatur_c)
        self.schreibzugriffe += 1
        self.commands.append(("ww_soll", float(temperatur_c)))

    async def set_raum_soll(self, temperatur_c: float) -> None:
        self.werte["raum_soll_c"] = float(temperatur_c)
        self.schreibzugriffe += 1
        self.commands.append(("raum_soll", float(temperatur_c)))
