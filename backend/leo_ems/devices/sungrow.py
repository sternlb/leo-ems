"""Sungrow SG 6.0RT — Garagendach-Wechselrichter (Spec §1/§6, geplant Ende 2026).

Bis zur Installation liefert `SungrowStub` konstant 0 W. Die AC-gekoppelte
Erzeugung erscheint ohnehin am Netzpunkt der E3DC — der Sungrow-Wert dient
der Gesamterzeugungs-Anzeige (REQ-040/051), nicht der Überschussrechnung.
Bei Ausfall: Werte = 0 und weiterarbeiten (Fail-Safe E5, Leo 2026-07-12).
"""

from __future__ import annotations

from datetime import datetime

from .base import DeviceAdapter


class SungrowStub(DeviceAdapter):
    """Platzhalter bis zur Installation — immer 0 W."""

    name = "sungrow"

    def __init__(self):
        self._last: datetime | None = None

    async def read(self) -> dict:
        self._last = datetime.now()
        return {"power_w": 0.0, "installiert": False}

    @property
    def last_update(self) -> datetime | None:
        return self._last


class SungrowAdapter(DeviceAdapter):
    """Echter Adapter via Modbus TCP (pymodbus). Ab Installation aktivieren."""

    name = "sungrow"

    # Sungrow-Register (SunSpec/Modbus) — bei Inbetriebnahme gegen die Anlage verifizieren
    REG_AC_POWER = 5031  # Beispiel: aktuelle AC-Leistung (W)

    def __init__(self, host: str, port: int = 502, unit_id: int = 1):
        self._host = host
        self._port = port
        self._unit_id = unit_id
        self._client = None
        self._last: datetime | None = None

    async def read(self) -> dict:  # pragma: no cover — echte Hardware ab Ende 2026
        from pymodbus.client import AsyncModbusTcpClient  # type: ignore

        if self._client is None:
            self._client = AsyncModbusTcpClient(self._host, port=self._port)
            await self._client.connect()
        rr = await self._client.read_input_registers(self.REG_AC_POWER, count=1, slave=self._unit_id)
        power = float(rr.registers[0]) if not rr.isError() else 0.0
        self._last = datetime.now()
        return {"power_w": power, "installiert": True}

    @property
    def last_update(self) -> datetime | None:
        return self._last
