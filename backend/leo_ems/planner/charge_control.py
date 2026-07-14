"""Ladesteuerungs-Zustandsmaschine — Spec §3, §4.1, §4.2 (REQ-002/005/064).

Reine Logik, testbar ohne Geräte: bekommt je Tick (now, Überschuss, Modus,
Garantie-Flag, Fahrzeug-SoC) und liefert einen ChargeCommand + Klartext-Grund
(REQ-050). Hysterese und Phasenumschaltung werden über festgehaltene
Bedingungszeiten realisiert; die Zeit kommt von außen (Tests simulieren sie).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from ..config import RegelConfig

VOLT = 230


def _mmss(sekunden: int) -> str:
    return f"{sekunden // 60}:{sekunden % 60:02d} min"


class ChargeState(str, Enum):
    FREI = "frei"            # kein Fahrzeug
    VERBUNDEN = "verbunden"  # verbunden, wartet auf Freigabe
    LADEN_1P = "laden_1p"
    LADEN_3P = "laden_3p"
    PAUSIERT = "pausiert"    # Hysterese / kein Überschuss
    BEENDET = "beendet"      # Ziel/Limit erreicht


@dataclass
class ChargeCommand:
    charging: bool
    current_a: int
    phases: int
    state: ChargeState
    reason: str


class ChargeController:
    def __init__(self, cfg: RegelConfig):
        self.cfg = cfg
        self.state = ChargeState.FREI
        self.phases = 1
        self._since: dict[str, datetime] = {}
        self._last_phase_switch: datetime | None = None

    # --- Hilfen ------------------------------------------------------------
    def _held(self, key: str, condition: bool, now: datetime) -> timedelta:
        """Wie lange ist `condition` ununterbrochen wahr (über die Ticks)?"""
        if condition:
            self._since.setdefault(key, now)
            return now - self._since[key]
        self._since.pop(key, None)
        return timedelta(0)

    def _enable_w(self) -> float:
        return self.cfg.min_current_a * VOLT  # 6 A × 230 V ≈ 1380 W (Spec §4.1)

    def _current_for(self, surplus_w: float, phases: int) -> int:
        raw = int(surplus_w // (VOLT * phases))
        return max(self.cfg.min_current_a, min(self.cfg.max_current_a, raw))

    def _decide_phases(self, surplus_w: float, now: datetime) -> int:
        """1↔3-Phasen-Umschaltung mit Hysterese + Mindestabstand (Spec §4.2)."""
        gap_ok = self._last_phase_switch is None or (
            now - self._last_phase_switch >= timedelta(seconds=self.cfg.phase_min_gap_s)
        )
        up = self._held("phase_up", surplus_w >= self.cfg.phase_up_w, now) >= timedelta(
            seconds=self.cfg.enable_delay_s
        )
        down = self._held("phase_down", surplus_w < self.cfg.phase_down_w, now) >= timedelta(
            seconds=self.cfg.disable_delay_s
        )
        if self.phases == 1 and up and gap_ok:
            self.phases = 3
            self._last_phase_switch = now
        elif self.phases == 3 and down and gap_ok:
            self.phases = 1
            self._last_phase_switch = now
        return self.phases

    def phase_diagnose(self, now: datetime, surplus_w: float) -> dict:
        """Transparenz-Sicht auf die Phasenumschaltung (REQ-050): Warum (noch) 1p/3p?

        Beantwortet Leos Kernfrage "Überschuss ist da, warum lädt er nur 1p?":
        Entprellung (Bedingung muss 60/180 s stabil anliegen) und die
        10-min-Umschaltsperre werden mit Restzeiten ausgewiesen.
        Reine Lesesicht auf die Timer aus _decide_phases — verändert nichts.
        """
        gap_rest_s = 0
        if self._last_phase_switch is not None:
            gap_rest_s = max(0, int(self.cfg.phase_min_gap_s
                                    - (now - self._last_phase_switch).total_seconds()))
        if self.phases == 1:
            ziel, key, noetig_s = 3, "phase_up", self.cfg.enable_delay_s
            bedingung = surplus_w >= self.cfg.phase_up_w
            lage = (f"Überschuss {surplus_w / 1000:.1f} kW "
                    f"{'≥' if bedingung else '<'} 3p-Schwelle {self.cfg.phase_up_w / 1000:.1f} kW")
        else:
            ziel, key, noetig_s = 1, "phase_down", self.cfg.disable_delay_s
            bedingung = surplus_w < self.cfg.phase_down_w
            lage = (f"Überschuss {surplus_w / 1000:.1f} kW "
                    f"{'<' if bedingung else '≥'} 1p-Schwelle {self.cfg.phase_down_w / 1000:.1f} kW")

        seit_s = 0
        if bedingung and key in self._since:
            seit_s = int((now - self._since[key]).total_seconds())
        entprellung = bedingung and seit_s < noetig_s
        sperre_blockt = bedingung and gap_rest_s > 0

        if not bedingung:
            grund = f"bleibt {self.phases}p: {lage}"
        elif entprellung and sperre_blockt:
            grund = (f"{lage} — Entprellung läuft ({seit_s}/{noetig_s} s), "
                     f"zusätzlich Umschaltsperre (noch {_mmss(gap_rest_s)})")
        elif entprellung:
            grund = f"{lage} — Entprellung läuft ({seit_s}/{noetig_s} s bis {ziel}p)"
        elif sperre_blockt:
            grund = f"{lage} — {ziel}p wartet auf Umschaltsperre (noch {_mmss(gap_rest_s)})"
        else:
            grund = f"{lage} — Umschaltung auf {ziel}p steht an"

        return {
            "phasen": self.phases,
            "wechsel_ziel": ziel if bedingung else None,
            "bedingung_erfuellt": bedingung,
            "entprellung_aktiv": entprellung,
            "entprellung_seit_s": seit_s,
            "entprellung_noetig_s": noetig_s,
            "umschaltsperre_aktiv": gap_rest_s > 0,
            "umschaltsperre_rest_s": gap_rest_s,
            "grund": grund,
        }

    def _charge(self, current_a: int, phases: int, reason: str) -> ChargeCommand:
        self.state = ChargeState.LADEN_3P if phases == 3 else ChargeState.LADEN_1P
        return ChargeCommand(True, current_a, phases, self.state, reason)

    # --- Hauptentscheidung -------------------------------------------------
    def update(
        self,
        now: datetime,
        *,
        surplus_w: float,
        connected: bool,
        mode: str,
        guarantee_active: bool,
        soc_fahrzeug: float | None = None,
        vehicle_limit_soc: float = 100,
    ) -> ChargeCommand:
        if not connected:
            self.state = ChargeState.FREI
            self._since.clear()
            return ChargeCommand(False, 0, self.phases, self.state, "kein Fahrzeug verbunden")

        # Fahrzeug am Limit → beenden (Spec §4.3 Punkt 3)
        if soc_fahrzeug is not None and soc_fahrzeug >= vehicle_limit_soc:
            self.state = ChargeState.BEENDET
            return ChargeCommand(False, 0, self.phases, self.state,
                                 f"Fahrzeug-Ladelimit {vehicle_limit_soc:.0f}% erreicht")

        # Garantieladung übersteuert ALLES inkl. Modus "Aus" (Spec §3/§4.3, Festlegung 5)
        if guarantee_active:
            self.phases = 3
            return self._charge(self.cfg.max_current_a, 3, "Garantieladung: Zielzeit/Mindest-SoC gefährdet")

        if mode == "Aus":
            self.state = ChargeState.VERBUNDEN
            return ChargeCommand(False, 0, self.phases, self.state, "Modus Aus")

        if mode == "Schnell":
            self.phases = 3
            return self._charge(self.cfg.max_current_a, 3, "Modus Schnell (max. Leistung, Herkunft egal)")

        if mode == "PV+Min":
            phases = self._decide_phases(surplus_w, now)
            current = self._current_for(surplus_w, phases)
            reicht_pv = surplus_w >= self.cfg.min_current_a * VOLT * phases
            zusatz = "" if reicht_pv else " (Minimum aus Netz/Batterie)"
            return self._charge(current, phases, f"PV+Min: {current} A {phases}p{zusatz}")

        # Nur-PV (Default): mit Ein-/Ausschalt-Hysterese (Spec §4.1)
        was_charging = self.state in (ChargeState.LADEN_1P, ChargeState.LADEN_3P)
        if was_charging:
            if self._held("disable", surplus_w < self._enable_w(), now) >= timedelta(
                seconds=self.cfg.disable_delay_s
            ):
                self.state = ChargeState.PAUSIERT
                self._since.pop("enable", None)
                return ChargeCommand(False, 0, self.phases, self.state,
                                     "Nur-PV: kein Überschuss mehr (pausiert)")
            phases = self._decide_phases(surplus_w, now)
            current = self._current_for(surplus_w, phases)
            return self._charge(current, phases, f"Nur-PV: {current} A {phases}p")

        # nicht ladend → Einschalt-Hysterese prüfen
        if self._held("enable", surplus_w >= self._enable_w(), now) >= timedelta(
            seconds=self.cfg.enable_delay_s
        ):
            phases = self._decide_phases(surplus_w, now)
            current = self._current_for(surplus_w, phases)
            return self._charge(current, phases, f"Nur-PV: {current} A {phases}p (Start)")
        self.state = ChargeState.VERBUNDEN
        return ChargeCommand(False, 0, self.phases, self.state, "Nur-PV: warte auf ausreichenden Überschuss")
