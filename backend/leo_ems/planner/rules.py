"""Laderegeln und Zielladungs-Planung — Spec §4.3 (REQ-003/004/070).

Regel = {Wochentage, Abfahrtszeit, Mindest-SoC, aktiv}. Beliebig viele Regeln,
das EMS plant auf die nächste zukünftige Abfahrt; bei Zeitgleichheit gilt der
höchste Mindest-SoC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from ..config import RegelConfig

MAX_CHARGE_POWER_W = 11_000  # go-e Gemini an 11 kW (Baseline)


@dataclass
class ChargingRule:
    """Wochentage: 0=Mo … 6=So (wie datetime.weekday())."""

    weekdays: frozenset[int]
    departure: time
    soc_min_pct: int
    active: bool = True
    rule_id: int | None = None

    def next_occurrence(self, now: datetime) -> datetime | None:
        if not self.active or not self.weekdays:
            return None
        for tage in range(8):
            kandidat = (now + timedelta(days=tage)).replace(
                hour=self.departure.hour, minute=self.departure.minute, second=0, microsecond=0
            )
            if kandidat.weekday() in self.weekdays and kandidat > now:
                return kandidat
        return None


def default_rule() -> ChargingRule:
    """Default bei Erstinstallation: Mo–Fr, 07:30, 50 % (Spec §4.3)."""
    return ChargingRule(weekdays=frozenset(range(5)), departure=time(7, 30), soc_min_pct=50)


def naechste_abfahrt(rules: list[ChargingRule], now: datetime) -> tuple[datetime, int] | None:
    """Nächste zukünftige Abfahrt über alle aktiven Regeln.

    Rückgabe (Zeitpunkt, Mindest-SoC) — bei Zeitgleichheit der höchste SoC.
    None, wenn keine aktive Regel greift (dann reines PV-Laden ohne Garantie).
    """
    kandidaten = [(occ, r.soc_min_pct) for r in rules if (occ := r.next_occurrence(now))]
    if not kandidaten:
        return None
    frueheste = min(occ for occ, _ in kandidaten)
    soc = max(soc for occ, soc in kandidaten if occ == frueheste)
    return frueheste, soc


@dataclass
class Garantieplan:
    abfahrt: datetime
    soc_min_pct: int
    e_fehlt_kwh: float
    t_start: datetime  # spätester Start der Garantieladung

    def garantie_aktiv(self, now: datetime, soc_ist_pct: float) -> bool:
        """Ab t_start wird netzunabhängig geladen, bis soc_min erreicht ist.

        Übersteuert auch den Modus "Aus" (Spec §3, Festlegung 5).
        """
        return now >= self.t_start and soc_ist_pct < self.soc_min_pct


def ev_ziel_grenze(cfg: RegelConfig) -> int:
    """Höchster SoC, auf den überhaupt geladen werden darf (Issue #9).

    `ev_limit_soc` ist der eingestellte Wert, `hard_limit_ev_max_soc` die
    Schutzgrenze darüber. Normalerweise hält die API die beiden schon in der
    richtigen Reihenfolge — hier wird trotzdem das Minimum genommen, damit eine
    von Hand editierte `/data/config.json` den Schutz nicht aushebelt.
    """
    if cfg.hard_limit_ev_max_soc is None:
        return cfg.ev_limit_soc
    return min(cfg.ev_limit_soc, cfg.hard_limit_ev_max_soc)


def plane_garantieladung(
    rules: list[ChargingRule], soc_ist_pct: float, now: datetime, cfg: RegelConfig
) -> Garantieplan | None:
    """Planungsrechnung Spec §4.3: E_fehlt, T_dauer, T_start."""
    ziel = naechste_abfahrt(rules, now)
    if ziel is None:
        return None
    abfahrt, soc_min = ziel
    # Die Garantieladung übersteuert laut Spec §3 Festlegung 5 alles — auch den
    # Modus „Aus". Ohne diese Deckelung wäre sie damit auch der Weg, auf dem eine
    # Regel mit `soc_min = 90` das Auto per Netzstrom über die Schutzgrenze zieht
    # (Issue #9). Hier gedeckelt und nicht erst im Controller, damit schon
    # `E_fehlt` und `T_start` gegen den erreichbaren Wert rechnen.
    soc_min = min(soc_min, ev_ziel_grenze(cfg))
    e_fehlt_kwh = max(0.0, soc_min - soc_ist_pct) / 100.0 * cfg.battery_capacity_kwh / cfg.charge_efficiency
    t_dauer = timedelta(hours=e_fehlt_kwh / (MAX_CHARGE_POWER_W / 1000.0))
    t_start = abfahrt - t_dauer - timedelta(minutes=cfg.plan_buffer_min)
    return Garantieplan(abfahrt=abfahrt, soc_min_pct=soc_min, e_fehlt_kwh=e_fehlt_kwh, t_start=t_start)
