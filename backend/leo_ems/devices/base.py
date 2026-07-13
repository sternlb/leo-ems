"""Gemeinsames Geräte-Interface (Architektur: Komponentenschnitt).

Jeder Adapter liefert Messwerte MIT Frische-Zeitstempel — die Fail-Safe-Matrix
(Spec §7) wird zentral in der Regelschleife anhand dieser Zeitstempel
ausgewertet, nicht in den Adaptern.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Messbild:
    """Ein konsistenter Satz Messwerte für einen Regel-Tick (Spec §2)."""

    zeitstempel: datetime
    p_pv_e3dc_w: float = 0.0
    p_pv_sungrow_w: float = 0.0      # E5: bei Ausfall/vor Installation 0 (Leo, 2026-07-12)
    p_netz_w: float = 0.0            # > 0 = Bezug
    p_batterie_w: float = 0.0        # > 0 = lädt
    soc_batterie_pct: float = 0.0
    p_wallbox_w: float = 0.0
    soc_fahrzeug_pct: float | None = None
    soc_fahrzeug_geschaetzt: bool = False  # Kennzeichnung Schätzwert (Spec §4.4)
    fahrzeug_verbunden: bool = False


class DeviceAdapter(ABC):
    """Basisklasse aller Geräteadapter (e3dc, goe, skoda, forecast, sungrow)."""

    name: str = "device"

    @abstractmethod
    async def read(self) -> dict:
        """Aktuelle Werte lesen. Wirft bei Nichterreichbarkeit — die Regelschleife
        bewertet die Frische und wendet die Fail-Safe-Matrix an."""

    @property
    @abstractmethod
    def last_update(self) -> datetime | None:
        """Zeitstempel der letzten erfolgreichen Lesung (Frische-Bewertung, Spec §7)."""
