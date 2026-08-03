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

    async def set_entladelimit(self, max_discharge_w: int | None) -> None:
        """Entladeleistung begrenzen (Spec §5.1).

        `None` hebt die Begrenzung auf, `0` ist die harte Sperre, alles dazwischen
        die dynamische Grenze (planner/batt_limit.py). pye3dc liefert -1 zurück,
        wenn die Anlage den Wert ablehnt — das lief bis v0.8.0 stumm durch und
        hätte eine wirkungslose Steuerung nicht von einer wirksamen unterschieden.
        1 heißt „angenommen, aber nicht optimal" und ist kein Fehler.
        """
        if max_discharge_w is None:
            res = self._e3dc.set_power_limits(enable=False)
        else:
            res = self._e3dc.set_power_limits(enable=True, max_discharge=int(max_discharge_w))
        if res == -1:
            raise RuntimeError(f"E3DC lehnt Entladegrenze {max_discharge_w} ab (RSCP -1)")


class E3dcSimulator(DeviceAdapter):
    """Simulator für Tests. `available=False` erzwingt einen Ausfall (Fail-Safe E1)."""

    name = "e3dc"

    def __init__(self, *, p_netz_w=0.0, p_batterie_w=0.0, soc_pct=50.0, p_pv_w=0.0):
        self.p_netz_w = p_netz_w
        self.p_batterie_w = p_batterie_w
        self.soc_pct = soc_pct
        self.p_pv_w = p_pv_w
        self.available = True
        self.entladelimit_w: int | None = None
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

    async def set_entladelimit(self, max_discharge_w: int | None) -> None:
        self.entladelimit_w = max_discharge_w
        self.commands.append(("entladelimit", max_discharge_w))

    @property
    def entladesperre(self) -> bool:
        """Harte Sperre = Grenze auf 0 (die Batterie gibt nichts mehr ab)."""
        return self.entladelimit_w == 0
