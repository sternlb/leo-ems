"""E3DC S10E — RSCP-Adapter (Spec §1/§5, ADR-004).

Mess-Mapping und Schreibbefehl (Entladesperre) sind mit dem Spike verifiziert
(docs/systems/e3dc.md, Spike-Ergebnis 2026-07-12). Vorzeichen laut Spike:
  production.grid  < 0 = Einspeisung → passt zu p_netz_w (>0 = Bezug)
  consumption.battery > 0 = lädt      → passt zu p_batterie_w (>0 = lädt)
"""

from __future__ import annotations

from datetime import datetime

from .base import DeviceAdapter


class E3dcAdapter(DeviceAdapter):
    """Echter Adapter via pye3dc (lokal, RSCP)."""

    name = "e3dc"

    def __init__(self, host: str, user: str, password: str, rscp_key: str):
        from e3dc import E3DC  # pye3dc, nur im echten Betrieb

        self._e3dc = E3DC(
            E3DC.CONNECT_LOCAL, username=user, password=password,
            ipAddress=host, key=rscp_key,
        )
        self._last: datetime | None = None

    async def read(self) -> dict:
        data = self._e3dc.poll()  # synchron; RSCP ist schnell (~10 ms)
        self._last = datetime.now()
        return {
            "p_pv_e3dc_w": float(data["production"]["solar"]),
            "p_netz_w": float(data["production"]["grid"]),
            "p_batterie_w": float(data["consumption"]["battery"]),
            "soc_batterie_pct": float(data["stateOfCharge"]),
        }

    @property
    def last_update(self) -> datetime | None:
        return self._last

    async def set_entladesperre(self, on: bool) -> None:
        """Entladesperre = Entladeleistung auf 0 begrenzen (Spec §5.1)."""
        if on:
            self._e3dc.set_power_limits(enable=True, max_discharge=0)
        else:
            self._e3dc.set_power_limits(enable=False)


class E3dcSimulator(DeviceAdapter):
    """Simulator für Tests. `available=False` erzwingt einen Ausfall (Fail-Safe E1)."""

    name = "e3dc"

    def __init__(self, *, p_netz_w=0.0, p_batterie_w=0.0, soc_pct=50.0, p_pv_w=0.0):
        self.p_netz_w = p_netz_w
        self.p_batterie_w = p_batterie_w
        self.soc_pct = soc_pct
        self.p_pv_w = p_pv_w
        self.available = True
        self.entladesperre = False
        self.commands: list[tuple] = []
        self._last: datetime | None = None

    async def read(self) -> dict:
        if not self.available:
            raise ConnectionError("E3DC nicht erreichbar (Simulator)")
        self._last = datetime.now()
        return {
            "p_pv_e3dc_w": self.p_pv_w,
            "p_netz_w": self.p_netz_w,
            "p_batterie_w": self.p_batterie_w,
            "soc_batterie_pct": self.soc_pct,
        }

    @property
    def last_update(self) -> datetime | None:
        return self._last

    async def set_entladesperre(self, on: bool) -> None:
        self.entladesperre = on
        self.commands.append(("entladesperre", on))
