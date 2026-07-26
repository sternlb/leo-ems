"""Vaillant aroTHERM über Home Assistant (REQ-013/014, ADR-004).

Das Vaillant-Internetmodul hängt am eBUS — es gibt keinen SG-Ready-Kontakt und
keinen lokalen Steuerweg (docs/systems/vaillant.md). Steuerweg ist die
MyVaillant-Cloud, und die hängt über die MyVaillant-Integration bereits in Home
Assistant. Statt einen zweiten Cloud-Client zu bauen (zweiter Login, zweites
Anfrage-Budget) geht Leo-EMS über die HA-REST-API: lesen aus den Sensoren,
schreiben über die Services `water_heater` / `climate`.

Zugang: als Add-on mit dem `SUPERVISOR_TOKEN` — dafür braucht das Add-on
`homeassistant_api: true` (config.yaml). Welcher *Weg* zu Home Assistant führt,
hängt vom Netzmodus ab, deshalb probiert der Adapter beim ersten Lesen die
bekannten Wege durch (`HA_KANDIDATEN`) und merkt sich den, der antwortet — im
`host_network`-Modus gibt es keine Docker-DNS, im Bridge-Netz keinen Host-Port.
Basis-URL und Token sind über die Add-on-Optionen überschreibbar (Entwicklung am
PC, Zugriff über einen Long-Lived Token); dann wird nichts durchprobiert.

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

# Wege zur HA-Core-API, in der Reihenfolge, in der sie probiert werden. Alle vier
# akzeptieren den `SUPERVISOR_TOKEN` — was sie unterscheidet, ist die Erreichbarkeit:
#
#   1. Supervisor-Proxy über Docker-DNS — der dokumentierte Weg, aber der Name
#      „supervisor“ löst nur im Bridge-Netz auf.
#   2. derselbe Proxy per IP — für `host_network: true` (kein Docker-DNS).
#   3. Core direkt auf dem Host: im Host-Netz liegt der veröffentlichte Port 8123
#      auf dem Loopback. Unabhängig vom Supervisor.
#   4. Core über Docker-DNS — Rückfall fürs Bridge-Netz.
#
# Kein Weg ist überall verfügbar, deshalb wird gesucht statt geraten (v0.6.2).
HA_KANDIDATEN = (
    "http://supervisor/core/api",
    "http://172.30.32.2/core/api",
    "http://127.0.0.1:8123/api",
    "http://homeassistant:8123/api",
)

# Rückwärtskompatibel: bisher fest verdrahtete Adresse
SUPERVISOR_CORE_URL = HA_KANDIDATEN[1]

# Nach einem gescheiterten Zugangs-Versuch so lange nicht erneut suchen. Sonst
# würde jeder 10-s-Tick vier Kandidaten durchprobieren und die Schleife bremsen.
ZUGANG_BACKOFF_S = 60.0
PROBE_TIMEOUT_S = 3.0

# Der Supervisor legt seinen Add-on-Token in die Umgebung. `SUPERVISOR_TOKEN` ist
# der aktuelle Name, `HASSIO_TOKEN` der alte — beide werden gesetzt, aber nicht in
# jeder HAOS-Generation beide. Reihenfolge = Vorrang.
TOKEN_ENV = ("SUPERVISOR_TOKEN", "HASSIO_TOKEN")


def _token_aus_umgebung() -> str:
    for name in TOKEN_ENV:
        wert = os.environ.get(name)
        if wert:
            return wert
    return ""

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
        # Explizit konfiguriert (Entwicklung am PC) → genau diese Adresse, sonst suchen
        self._kandidaten = (base_url.rstrip("/"),) if base_url else HA_KANDIDATEN
        self.base_url: str | None = self._kandidaten[0] if base_url else None
        self.token = token or _token_aus_umgebung()
        self.ww_entity = ww_entity
        self.zone_entity = zone_entity
        self.schreibzugriffe = 0          # Zähler fürs Protokoll (REQ-014)
        self.letzter_fehler: str | None = None   # Klartext für Status/Diagnose
        self._poll_s = poll_s
        self._timeout_s = timeout_s
        self._last: datetime | None = None
        self._cache: dict | None = None
        self._session = None
        self._suche_bis: datetime | None = None  # Backoff nach fehlgeschlagener Suche

    def token_herkunft(self) -> str:
        """Woher der Token kommt — für Fehlermeldung und Diagnose, nie der Token selbst."""
        if not self.token:
            vorhanden = [n for n in TOKEN_ENV if os.environ.get(n)]
            return f"kein Token (Umgebung: {vorhanden or 'keine der ' + str(TOKEN_ENV)})"
        quelle = next((n for n in TOKEN_ENV if os.environ.get(n) == self.token), "Option ha_token")
        return f"Token aus {quelle}, {len(self.token)} Zeichen"

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

    async def _erreichbar(self, basis: str) -> int:
        """HTTP-Status der API-Wurzel (`{"message": "API running."}`) — 200 = Zugang steht.

        Trennt die beiden Fehlerbilder, die sonst gleich aussehen: 401 heißt „Weg
        richtig, Token abgelehnt", ein Verbindungsfehler heißt „Weg gibt es hier nicht".
        """
        sess = await self._session_holen()
        async with sess.get(f"{basis}/", timeout=aiohttp.ClientTimeout(total=PROBE_TIMEOUT_S)) as resp:
            return resp.status

    async def _basis(self) -> str:
        """Adresse der HA-API — beim ersten Mal gesucht, danach gemerkt."""
        if self.base_url is not None:
            return self.base_url
        if self._suche_bis is not None and datetime.now() < self._suche_bis:
            raise ConnectionError(self.letzter_fehler or "kein Zugang zu Home Assistant")

        wege = []
        for kandidat in self._kandidaten:
            try:
                status = await self._erreichbar(kandidat)
            except Exception as exc:
                wege.append(f"{kandidat} → {type(exc).__name__}")
                continue
            if status == 200:
                self.base_url = kandidat
                self.letzter_fehler = None
                self._suche_bis = None
                print(f"[leo-ems] Wärmepumpe: HA-API über {kandidat}", flush=True)
                return kandidat
            wege.append(f"{kandidat} → HTTP {status}")

        # Ohne Token sieht jeder Weg wie „401" aus — das ist die häufigere Ursache
        # als eine falsche Adresse, deshalb steht sie zuerst im Klartext. Welche
        # Token-Quellen es überhaupt gab, gehört dazu: sonst ist nicht zu
        # unterscheiden, ob der Supervisor keinen Token liefert oder ob er
        # abgelehnt wird.
        self.letzter_fehler = (
            f"kein Zugang zu Home Assistant ({self.token_herkunft()}): " + ", ".join(wege)
        )
        self._suche_bis = datetime.now() + timedelta(seconds=ZUGANG_BACKOFF_S)
        print(f"[leo-ems] Wärmepumpe: {self.letzter_fehler}", flush=True)
        raise ConnectionError(self.letzter_fehler)

    async def _state(self, entity_id: str) -> str | None:
        """Rohzustand einer Entity; None, wenn HA sie nicht (mehr) kennt."""
        sess = await self._session_holen()
        basis = await self._basis()
        async with sess.get(f"{basis}/states/{entity_id}") as resp:
            if resp.status == 404:
                return None
            resp.raise_for_status()
            return (await resp.json()).get("state")

    async def _service(self, domain: str, service: str, daten: dict) -> None:
        sess = await self._session_holen()
        basis = await self._basis()
        async with sess.post(f"{basis}/services/{domain}/{service}", json=daten) as resp:
            resp.raise_for_status()
        self.schreibzugriffe += 1

    # --- DeviceAdapter ------------------------------------------------------
    async def read(self) -> dict:
        """Alle WP-Werte auf einmal. Eigener Poll-Takt: zwischen zwei Abfragen
        liefert der Cache — die Cloud aktualisiert ohnehin nur minütlich."""
        if self._cache is not None and self._last is not None:
            if datetime.now() - self._last < timedelta(seconds=self._poll_s):
                return self._cache

        # Zugang zuerst klären — sonst scheitern 15 Abfragen an derselben Ursache
        # und die eigentliche Fehlermeldung geht in der Sammel-Ausnahme unter.
        await self._basis()

        felder = list(SENSOREN)
        roh = await asyncio.gather(
            *(self._state(SENSOREN[f][0]) for f in felder), return_exceptions=True
        )
        if all(isinstance(r, Exception) for r in roh):
            # Home Assistant nicht erreichbar → Fail-Safe E7 in der Regelschleife
            self.letzter_fehler = (
                f"Home Assistant antwortet nicht auf {self.base_url}: "
                f"{type(roh[0]).__name__}: {roh[0]}"
            )
            raise ConnectionError(self.letzter_fehler)

        daten: dict = {}
        fehlend: list[str] = []
        for feld, wert in zip(felder, roh):
            if isinstance(wert, Exception):
                daten[feld] = None
                fehlend.append(SENSOREN[feld][0])
                continue
            numerisch = SENSOREN[feld][1]
            daten[feld] = _zahl(wert) if numerisch else (None if wert in LEER else wert)

        # Teil-Ausfall: gelesen wird trotzdem, aber der Grund steht im Status.
        # Häufigste Ursache sind umbenannte Entities (MyVaillant-Neuanbindung).
        self.letzter_fehler = (
            f"{len(fehlend)} von {len(felder)} Sensoren nicht lesbar: {', '.join(fehlend)}"
            if fehlend else None
        )
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
        self.letzter_fehler: str | None = None
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
