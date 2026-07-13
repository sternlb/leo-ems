"""go-e Gemini flexibel — lokale HTTP-API v2 (Spec §1, ADR-004).

Steuerung ohne Cloud: Ladestrom (amp), Freigabe (frc), Phasen (psm).
Das Feld-Mapping der Status-Antwort (nrg/car/psm) ist gegen die echte Wallbox
zu verifizieren — analog zum E3DC-Spike (siehe docs/systems/goe-wallbox.md).
"""

from __future__ import annotations

from datetime import datetime

from .base import DeviceAdapter

try:  # aiohttp nur im echten Betrieb nötig, nicht für Tests/Simulator
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None


class GoeAdapter(DeviceAdapter):
    """Echter Adapter gegen die go-e-HTTP-API v2."""

    name = "goe"

    def __init__(self, host: str, timeout_s: float = 5.0):
        self.host = host
        self._timeout_s = timeout_s
        self._last: datetime | None = None
        self._session = None

    async def _get(self, path: str) -> dict:
        if aiohttp is None:  # pragma: no cover
            raise RuntimeError("aiohttp nicht installiert")
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout_s)
            )
        async with self._session.get(f"http://{self.host}{path}") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def read(self) -> dict:
        s = await self._get("/api/status")
        car = s.get("car")                 # 1=idle,2=lädt,3=wartet,4=fertig
        nrg = s.get("nrg", [])
        power_w = float(nrg[11]) if len(nrg) > 11 else 0.0  # total power, HW-verifizieren
        self._last = datetime.now()
        return {
            "connected": car in (2, 3, 4),
            "charging": car == 2,
            "power_w": power_w,
            "phases": 3 if s.get("psm") == 2 else 1,
            "current_a": s.get("amp", 0),
            "session_wh": s.get("wh", 0),
        }

    @property
    def last_update(self) -> datetime | None:
        return self._last

    async def set_current(self, ampere: int) -> None:
        await self._get(f"/api/set?amp={ampere}")

    async def set_phases(self, phases: int) -> None:
        await self._get(f"/api/set?psm={2 if phases == 3 else 1}")

    async def set_charging(self, on: bool) -> None:
        await self._get(f"/api/set?frc={2 if on else 1}")  # 2=on erzwungen, 1=off

    async def close(self) -> None:  # pragma: no cover
        if self._session is not None:
            await self._session.close()


class GoeSimulator(DeviceAdapter):
    """Simulator für Tests/Entwicklung (kein Netz). Zeichnet Befehle auf."""

    name = "goe"

    def __init__(self, connected: bool = False, power_w: float = 0.0):
        self._connected = connected
        self._power_w = power_w
        self.charging = False
        self.current_a = 0
        self.phases = 1
        self.commands: list[tuple] = []
        self._last: datetime | None = None

    async def read(self) -> dict:
        self._last = datetime.now()
        return {
            "connected": self._connected,
            "charging": self.charging,
            "power_w": self._power_w,
            "phases": self.phases,
            "current_a": self.current_a,
            "session_wh": 0,
        }

    @property
    def last_update(self) -> datetime | None:
        return self._last

    async def set_current(self, ampere: int) -> None:
        self.current_a = ampere
        self.commands.append(("current", ampere))

    async def set_phases(self, phases: int) -> None:
        self.phases = phases
        self.commands.append(("phases", phases))

    async def set_charging(self, on: bool) -> None:
        self.charging = on
        self.commands.append(("charging", on))
