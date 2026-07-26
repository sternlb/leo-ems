"""Škoda Enyaq — Fahrzeug-SoC über die Škoda-Cloud (Spec §1/§4.4, E3).

Cloud-Adapter: SoC kann während der Ruhephase veralten; die Regelschleife
bewertet die Frische und schätzt bei Bedarf (Spec §4.4). Bei Ausfall bleibt
der Betrieb unverändert (Fail-Safe E3, Leo 2026-07-12).
"""

from __future__ import annotations

from datetime import datetime

from .base import DeviceAdapter


class SkodaAdapter(DeviceAdapter):
    """Echter Adapter via myskoda (async Cloud-API)."""

    name = "skoda"

    def __init__(self, user: str, password: str, vin: str | None = None):
        self._user = user
        self._password = password
        self._vin = vin
        self._client = None
        self._last: datetime | None = None

    async def _ensure(self):
        if self._client is None:  # pragma: no cover — echte Cloud
            from myskoda import MySkoda  # type: ignore
            import aiohttp

            self._session = aiohttp.ClientSession()
            self._client = MySkoda(self._session)
            await self._client.connect(self._user, self._password)
            if self._vin is None:
                self._vin = (await self._client.list_vehicle_vins())[0]

    # myskoda hat den Tippfehler im Feldnamen irgendwann korrigiert. Erst gefunden,
    # als die Lesefehler sichtbar wurden (v0.6.2): der Adapter lief seit dem
    # Go-live in eine AttributeError, deshalb war `soc_fahrzeug` immer null.
    SOC_FELDER = ("state_of_charge_in_percent", "state_of_charged_in_percent")

    @classmethod
    def _soc(cls, batterie) -> float:
        for feld in cls.SOC_FELDER:
            wert = getattr(batterie, feld, None)
            if wert is not None:
                return float(wert)
        raise ConnectionError(
            f"myskoda liefert keinen SoC — keines der Felder {cls.SOC_FELDER} vorhanden"
        )

    async def read(self) -> dict:  # pragma: no cover — echte Cloud
        await self._ensure()
        info = await self._client.get_charging(self._vin)
        status = getattr(info, "status", None)
        if status is None or getattr(status, "battery", None) is None:
            # Fahrzeug schläft → kein Batteriestatus. E3: Betrieb unverändert.
            raise ConnectionError("Škoda-Cloud ohne Batteriestatus (Fahrzeug schläft)")
        soc = self._soc(status.battery)
        self._last = datetime.now()
        return {"soc_pct": float(soc)}

    @property
    def last_update(self) -> datetime | None:
        return self._last


class SkodaSimulator(DeviceAdapter):
    """Simulator: fester/steuerbarer SoC; available=False erzwingt Ausfall (E3)."""

    name = "skoda"

    def __init__(self, soc_pct: float = 60.0):
        self.soc_pct = soc_pct
        self.available = True
        self._last: datetime | None = None

    async def read(self) -> dict:
        if not self.available:
            raise ConnectionError("Škoda-Cloud nicht erreichbar (Simulator)")
        self._last = datetime.now()
        return {"soc_pct": self.soc_pct}

    @property
    def last_update(self) -> datetime | None:
        return self._last
