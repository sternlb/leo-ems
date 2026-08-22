"""Messwerte als Home-Assistant-Sensoren veröffentlichen (v0.12.0).

**Warum das EMS pusht und HA nicht selbst liest:** Der WiNet-S-Dongle des
Sungrow nimmt nur **eine** Modbus-Verbindung an. Bindet man den Wechselrichter
zusätzlich über die HA-Modbus-Integration ein, streiten sich zwei Clients um
dieselbe Verbindung und beide bekommen Aussetzer. Es gibt also genau einen
Modbus-Leser — das EMS — und der reicht die Werte an HA weiter.

Geschrieben wird über `POST /api/states/<entity_id>` der HA-Core-API. Solche
Entities stehen nicht in der Entity-Registry: Sie erscheinen nach dem ersten
Push, überleben einen HA-Neustart nicht und sind nach spätestens einem
Push-Intervall wieder da. Für Diagramme und das Energie-Dashboard genügt das,
weil `state_class` gesetzt ist und der Recorder sie damit aufzeichnet.

Zugang wie beim Vaillant-Adapter: `SUPERVISOR_TOKEN`, Weg aus `HA_KANDIDATEN`.
Die Suche steht hier bewusst noch einmal in kurzer Form statt in einer
gemeinsamen Basisklasse — der Export braucht weder Cache noch Poll-Takt noch
Schreibzähler, und ein Refactor am laufenden WP-Adapter wäre für diesen
Zugewinn das größere Risiko. Geteilt sind die Dinge, die wirklich identisch
sein müssen: Kandidatenliste und Token-Herkunft.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from .devices.vaillant import HA_KANDIDATEN, PROBE_TIMEOUT_S, _token_aus_umgebung

try:  # aiohttp nur im echten Betrieb nötig, nicht für Tests
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None

ZUGANG_BACKOFF_S = 300
PUSH_INTERVALL_S = 30.0   # Die Regelschleife tickt alle 10 s; für Diagramme
                          # reichen 30 s und sie halten die HA-Datenbank klein.


def sensoren_aus_status(st: dict) -> dict[str, dict]:
    """Statusbild → Entity-Definitionen. Reine Funktion, ohne I/O.

    Haus- und Garagenanlage werden **beide** exportiert, obwohl es für die
    Hausanlage schon `sensor.s10e_solar_production` gibt: In einem gemeinsamen
    Diagramm müssen die Linien denselben Zeitraster haben, sonst treppen sie
    gegeneinander. Aus einer Quelle gepusht haben sie exakt denselben Stempel.
    """
    sg = st.get("sungrow") or {}
    p_haus_pv = float(st.get("p_pv_e3dc_w") or 0)
    p_garage = float(st.get("p_sungrow_w") or 0)

    def leistung(name: str, wert: float, icon: str) -> dict:
        return {
            "state": round(wert),
            "attributes": {
                "friendly_name": name,
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
                "icon": icon,
            },
        }

    sensoren = {
        "sensor.pv_haus_leistung": leistung("PV Haus (E3DC)", p_haus_pv, "mdi:solar-power"),
        "sensor.pv_garage_leistung": leistung("PV Garage (Sungrow)", p_garage, "mdi:solar-power-variant"),
        "sensor.pv_gesamt_leistung": leistung("PV gesamt", p_haus_pv + p_garage, "mdi:solar-power"),
    }

    # Hausverbrauch (v0.13.0). `sensor.s10e_house_consumption` der E3DC-
    # Integration ist seit der Garagen-Anlage falsch: Der Sungrow speist hinter
    # dem Zähler ein, die E3DC kennt ihn nicht und rechnet ihren Hausverbrauch
    # deshalb um dessen Erzeugung zu klein — bei genug Sonne wird die Bilanz
    # negativ und die Anlage meldet 0 W. Das EMS kennt beide Anlagen und ist
    # damit die einzige Stelle, die den Wert richtig bilden kann.
    #
    # Zwei Sensoren, weil zwei verschiedene Fragen dahinterstehen: Das
    # Dashboard zeichnet die Wallbox als eigenen Verbraucher und braucht den
    # Hausverbrauch OHNE sie (sonst steht ihre Leistung zweimal im Bild); der
    # kWh-Zähler und das HA-Energie-Dashboard wollen den Gesamtverbrauch.
    if "p_haus_w" in st:
        sensoren["sensor.hausverbrauch_leistung"] = leistung(
            "Hausverbrauch (ohne Wallbox)", float(st["p_haus_w"]), "mdi:home-lightning-bolt")
    if "p_haus_gesamt_w" in st:
        sensoren["sensor.hausverbrauch_gesamt_leistung"] = leistung(
            "Hausverbrauch gesamt", float(st["p_haus_gesamt_w"]), "mdi:home-lightning-bolt-outline")

    # Zählerstand der Garagen-Anlage — damit sie im HA-Energie-Dashboard
    # auftauchen kann. `total_increasing` ist richtig: der Zähler im
    # Wechselrichter läuft monoton und wird nie zurückgesetzt.
    gesamt = sg.get("gesamtertrag_kwh")
    if gesamt is not None:
        sensoren["sensor.pv_garage_ertrag_gesamt"] = {
            "state": round(float(gesamt), 1),
            "attributes": {
                "friendly_name": "PV Garage Ertrag gesamt",
                "unit_of_measurement": "kWh",
                "device_class": "energy",
                "state_class": "total_increasing",
                "icon": "mdi:counter",
            },
        }
    return sensoren


class HaSensorExport:
    """Schreibt die Sensoren im Takt von `PUSH_INTERVALL_S` nach Home Assistant."""

    def __init__(self, base_url: str | None = None, token: str | None = None,
                 intervall_s: float = PUSH_INTERVALL_S, timeout_s: float = 10.0):
        self._kandidaten = (base_url.rstrip("/"),) if base_url else HA_KANDIDATEN
        self.base_url: str | None = self._kandidaten[0] if base_url else None
        self.token = token or _token_aus_umgebung()
        # Ohne Token gibt es keinen Zugang — alle Kandidaten antworten dann mit
        # 401. Das gar nicht erst zu versuchen ist nicht nur schneller, es ist
        # auch die ehrlichere Aussage: Außerhalb des Add-ons (Entwicklung am PC,
        # Tests) gibt es kein Home Assistant, in das exportiert werden könnte.
        self.aktiv = bool(self.token)
        self.letzter_fehler: str | None = None if self.aktiv else "kein HA-Token — Export inaktiv"
        self.geschrieben = 0
        self._intervall = timedelta(seconds=intervall_s)
        self._timeout_s = timeout_s
        self._session = None
        self._zuletzt: datetime | None = None
        self._suche_bis: datetime | None = None
        self._task = None

    def faellig(self, jetzt: datetime) -> bool:
        return self._zuletzt is None or (jetzt - self._zuletzt) >= self._intervall

    def push_nebenlaeufig(self, st: dict, jetzt: datetime | None = None) -> bool:
        """Push anstoßen, **ohne auf das Netz zu warten**. True = gestartet.

        Der Aufrufer ist die Regelschleife. Würde sie den Push abwarten, stünde
        ein Tick bei hängendem Home Assistant bis zu 12 s (vier Kandidaten ×
        Probe-Timeout) — bei 10 s Tick-Intervall hielte der Export damit die
        Regelung an. Anzeige darf Steuerung nie ausbremsen, deshalb läuft der
        Push als eigener Task und der Tick ist sofort fertig.

        Höchstens ein Task gleichzeitig: Ein hängender Push darf sich nicht
        alle 30 s einen weiteren danebenstellen.
        """
        if not self.aktiv:
            return False
        jetzt = jetzt or datetime.now()
        if not self.faellig(jetzt):
            return False
        if self._task is not None and not self._task.done():
            return False
        self._zuletzt = jetzt      # sofort stempeln, sonst startet der nächste Tick erneut
        self._task = asyncio.get_running_loop().create_task(self._schreiben(st))
        return True

    async def _session_holen(self):
        if aiohttp is None:  # pragma: no cover
            raise RuntimeError("aiohttp nicht installiert")
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout_s),
                headers={"Authorization": f"Bearer {self.token}"},
            )
        return self._session

    async def _basis(self) -> str:
        if self.base_url is not None:
            return self.base_url
        if self._suche_bis is not None and datetime.now() < self._suche_bis:
            raise ConnectionError(self.letzter_fehler or "kein Zugang zu Home Assistant")

        wege = []
        sess = await self._session_holen()
        for kandidat in self._kandidaten:
            try:
                async with sess.get(
                    f"{kandidat}/", timeout=aiohttp.ClientTimeout(total=PROBE_TIMEOUT_S)
                ) as resp:
                    status = resp.status
            except Exception as exc:
                wege.append(f"{kandidat} → {type(exc).__name__}")
                continue
            if status == 200:
                self.base_url = kandidat
                self.letzter_fehler = None
                self._suche_bis = None
                print(f"[leo-ems] Sensor-Export: HA-API über {kandidat}", flush=True)
                return kandidat
            wege.append(f"{kandidat} → HTTP {status}")

        self.letzter_fehler = "kein Zugang zu Home Assistant: " + ", ".join(wege)
        self._suche_bis = datetime.now() + timedelta(seconds=ZUGANG_BACKOFF_S)
        print(f"[leo-ems] Sensor-Export: {self.letzter_fehler}", flush=True)
        raise ConnectionError(self.letzter_fehler)

    async def push(self, st: dict, jetzt: datetime | None = None) -> int:
        """Wie `push_nebenlaeufig`, aber abwartend — für Tests und Diagnose."""
        jetzt = jetzt or datetime.now()
        if not self.aktiv or not self.faellig(jetzt):
            return 0
        self._zuletzt = jetzt
        return await self._schreiben(st)

    async def _schreiben(self, st: dict) -> int:
        """Sensoren schreiben. Gibt die Zahl geschriebener Entities zurück.

        Wirft nie: Der Export ist Anzeige, keine Regelung. Ein HA-Ausfall wird
        in `letzter_fehler` vermerkt und beim nächsten Takt neu versucht — er
        darf weder die Schleife abbrechen noch als unbeachtete Task-Exception
        im Log auftauchen.
        """
        try:
            sess = await self._session_holen()
            basis = await self._basis()
            n = 0
            for entity_id, koerper in sensoren_aus_status(st).items():
                async with sess.post(f"{basis}/states/{entity_id}", json=koerper) as resp:
                    if resp.status in (200, 201):
                        n += 1
                    else:
                        self.letzter_fehler = f"{entity_id}: HTTP {resp.status}"
            self.geschrieben += n
            if n:
                self.letzter_fehler = None
            return n
        except Exception as exc:
            self.letzter_fehler = f"{type(exc).__name__}: {exc}"
            return 0

    async def schliessen(self) -> None:  # pragma: no cover — Aufräumen beim Herunterfahren
        if self._task is not None and not self._task.done():
            self._task.cancel()
        if self._session is not None:
            await self._session.close()
            self._session = None
