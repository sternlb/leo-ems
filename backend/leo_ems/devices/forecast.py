"""Forecast.Solar — PV-Ertragsprognose (Spec §6, REQ-041).

Zwei Flächen: E3DC Ost 22° + Garagendach Ost/West 15°. Öffentlicher Tier,
Abruf max. 1×/h. Bei Ausfall: letzte Prognose weiterverwenden, Betrieb
unverändert (Fail-Safe E4, Leo 2026-07-12).

Azimut-Konvention Forecast.Solar: -90=Ost, 0=Süd, 90=West.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .base import DeviceAdapter

# Standort Röthenbach a.d. Pegnitz (aus PV-Projekt)
LAT_DEFAULT = 49.48
LON_DEFAULT = 11.25
# Flächen: (Neigung, Azimut, kWp)
FLAECHEN = [
    (22, -90, 9.23),   # E3DC-Anlage Ost
    (15, -90, 2.82),   # Garagendach Ost (halbe kWp)
    (15, 90, 2.82),    # Garagendach West
]


class ForecastAdapter(DeviceAdapter):
    """Echter Adapter gegen api.forecast.solar (mehrere Flächen summiert)."""

    name = "forecast"

    def __init__(self, lat: float = LAT_DEFAULT, lon: float = LON_DEFAULT, min_intervall_s: int = 3600):
        self._lat = lat
        self._lon = lon
        self._min_intervall = timedelta(seconds=min_intervall_s)
        self._cache: dict = {}
        self._last: datetime | None = None

    async def read(self) -> dict:  # pragma: no cover — externer Dienst
        import aiohttp

        # Rate-Limit: höchstens 1×/h abrufen, sonst Cache zurückgeben (E4)
        if self._last is not None and datetime.now() - self._last < self._min_intervall and self._cache:
            return self._cache

        watts: dict[str, float] = {}
        async with aiohttp.ClientSession() as s:
            for neigung, azimut, kwp in FLAECHEN:
                url = f"https://api.forecast.solar/estimate/{self._lat}/{self._lon}/{neigung}/{azimut}/{kwp}"
                async with s.get(url) as r:
                    r.raise_for_status()
                    data = (await r.json())["result"]["watts"]
                for ts, w in data.items():
                    watts[ts] = watts.get(ts, 0.0) + float(w)
        self._cache = {"watts": watts}
        self._last = datetime.now()
        return self._cache

    @property
    def last_update(self) -> datetime | None:
        return self._last

    def erwartete_wh_bis(self, jetzt: datetime, bis: datetime) -> float:
        """Erwartete Energie (Wh) zwischen jetzt und `bis` — für Zielladungs-Verschiebung (Spec §4.3)."""
        watts = self._cache.get("watts", {})
        summe = 0.0
        for ts, w in watts.items():
            t = datetime.fromisoformat(ts)
            if jetzt <= t <= bis:
                summe += w  # stündliche Punkte ≈ Wh
        return summe


class ForecastSimulator(DeviceAdapter):
    """Simulator mit vorgegebener Wattkurve."""

    name = "forecast"

    def __init__(self, watts: dict | None = None):
        self._watts = watts or {}
        self._last: datetime | None = None

    async def read(self) -> dict:
        self._last = datetime.now()
        return {"watts": self._watts}

    @property
    def last_update(self) -> datetime | None:
        return self._last

    def erwartete_wh_bis(self, jetzt: datetime, bis: datetime) -> float:
        return sum(
            w for ts, w in self._watts.items() if jetzt <= datetime.fromisoformat(ts) <= bis
        )
