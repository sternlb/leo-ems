"""Regelschleife (Spec §2: 10-s-Tick) — Gerüst, wird in Phase 4 ausgebaut.

Datenfluss je Tick: devices → Messbild → planner → SafetyGuard → devices → store.
Die Fail-Safe-Matrix (Spec §7) wird HIER zentral ausgewertet:
  E1 E3DC weg (>60 s)   → Abschalten: Ladung stoppen, Steuerung einstellen
  E2 go-e weg (>60 s)   → keine Befehle mehr, Wallbox autonom
  E3 Škoda alt (>30 min)→ Betrieb unverändert, SoC-Schätzung (§4.4)
  E4 Forecast weg       → Betrieb unverändert, letzte Prognose
  E5 Sungrow weg        → Werte = 0, weiterarbeiten
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from ..config import RegelConfig
from ..planner import berechne_ueberschuss, plane_garantieladung
from ..safety import SafetyGuard
from ..store import Store

E3DC_MAX_ALTER = timedelta(seconds=60)


class ControlLoop:
    def __init__(self, cfg: RegelConfig, guard: SafetyGuard, store: Store, adapters: dict):
        self.cfg = cfg
        self.guard = guard
        self.store = store
        self.adapters = adapters
        self._letzte_ueberschuesse: list[float] = []  # gleitender Mittelwert über 3 (Spec §2)
        self.running = False

    async def run(self) -> None:
        self.running = True
        while self.running:
            try:
                await self.tick(datetime.now())
            except Exception as exc:  # Tick-Fehler dürfen die Schleife nie beenden
                self.store.log_decision(datetime.now(), "tick_fehler", {}, "-", f"Fehler: {exc}")
            await asyncio.sleep(self.cfg.interval_s)

    async def tick(self, now: datetime) -> None:
        # 1) Abgelaufene Leases wegräumen und loggen (ADR-005)
        for lease in self.guard.sweep(now):
            self.store.log_decision(now, "lease_abgelaufen", {"lease": lease.name}, "-", "ausgelaufen")

        # 2) Frische prüfen — E1: E3DC weg ⇒ Abschalten (Leo, 2026-07-12)
        e3dc = self.adapters.get("e3dc")
        if e3dc is None or e3dc.last_update is None or now - e3dc.last_update > E3DC_MAX_ALTER:
            # TODO Phase 4: aktive Ladung stoppen, dann Steuerung einstellen bis Daten zurück sind
            return

        # TODO Phase 4 (in dieser Reihenfolge):
        #  - Messbild aus Adaptern zusammensetzen (devices/base.Messbild)
        #  - berechne_ueberschuss() + gleitender Mittelwert (Spec §2)
        #  - Zustandsmaschine §4.1/§4.2 (Hysterese, Phasenumschaltung)
        #  - plane_garantieladung() gegen Regelliste (§4.3)
        #  - Entladesperre als Lease setzen/erneuern (§5.1)
        #  - jeden Befehl durch guard.validate_* und ins decision_log (REQ-062/063)
