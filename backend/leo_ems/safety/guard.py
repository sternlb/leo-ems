"""Fail-Safe-Kern: Leases statt Zustände (ADR-005, Spec §5.1/§8.3).

Jede Übersteuerung (Entladesperre, Garantieladung, Override) existiert nur als
Lease mit Ablaufzeit. Stirbt das EMS, laufen alle Leases aus und die Geräte
regeln autonom weiter (REQ-024/060). Es gibt bewusst KEINE API, die einen
Gerätezustand ohne TTL setzt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..config import RegelConfig


@dataclass
class Lease:
    name: str                 # z.B. "e3dc_entladesperre", "override_modus"
    expires_at: datetime
    reason: str = ""

    def expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def renew(self, now: datetime, ttl_s: int) -> None:
        self.expires_at = now + timedelta(seconds=ttl_s)


class SafetyGuard:
    """Zentrale Befehls-Validierung (REQ-063) + Lease-Verwaltung.

    Jeder Steuerbefehl läuft hier durch; Verstöße werden verworfen und geloggt.
    """

    def __init__(self, cfg: RegelConfig):
        self.cfg = cfg
        self._leases: dict[str, Lease] = {}

    # --- Leases -----------------------------------------------------------
    def acquire(self, name: str, now: datetime, reason: str = "") -> Lease:
        lease = Lease(name=name, expires_at=now + timedelta(seconds=self.cfg.lease_ttl_s), reason=reason)
        self._leases[name] = lease
        return lease

    def active(self, name: str, now: datetime) -> bool:
        lease = self._leases.get(name)
        return lease is not None and not lease.expired(now)

    def release(self, name: str) -> None:
        self._leases.pop(name, None)

    def sweep(self, now: datetime) -> list[Lease]:
        """Entfernt abgelaufene Leases; Rückgabe fürs Entscheidungs-Log (REQ-062)."""
        abgelaufen = [l for l in self._leases.values() if l.expired(now)]
        for lease in abgelaufen:
            del self._leases[lease.name]
        return abgelaufen

    # --- Befehls-Validierung ------------------------------------------------
    def validate_current(self, ampere: int) -> int | None:
        """Ladestrom nur innerhalb 6–16 A (Spec §8.3). None = Befehl verwerfen."""
        if self.cfg.min_current_a <= ampere <= self.cfg.max_current_a:
            return ampere
        return None

    def validate_battery_discharge(self, soc_pct: float) -> bool:
        """Kein aktives Entladen unter die Reserve (REQ-021).

        Wird von `planner/batt_limit.py` vor jeder bewussten Batterie-Freigabe
        ans Auto gefragt (Issue #11).
        """
        return soc_pct > self.cfg.soc_reserve_pct

    def validate_ev_ziel_soc(self, soc: float) -> float:
        """Kein Ladeziel über der harten Obergrenze (REQ-072, Issue #9).

        Anders als `validate_current` verwirft diese Prüfung den Wert nicht,
        sondern **deckelt** ihn: ein zu hohes Ladeziel soll nicht dazu führen,
        dass gar nicht geladen wird, sondern dass bis zur Schutzgrenze geladen
        wird. Greift für das Fahrzeug-Ladelimit selbst wie auch für den
        Mindest-SoC einer Laderegel, der sonst per Garantieladung darüber
        hinweggehen würde.
        """
        grenze = self.cfg.hard_limit_ev_max_soc
        return soc if grenze is None else min(soc, float(grenze))
