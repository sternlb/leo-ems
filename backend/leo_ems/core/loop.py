"""Regelschleife (Spec §2: 10-s-Tick).

Datenfluss je Tick: devices → Messbild → planner → SafetyGuard → devices → store.
Die Fail-Safe-Matrix (Spec §7) wird HIER zentral ausgewertet:
  E1 E3DC weg          → Abschalten: Ladung stoppen, Steuerung einstellen
  E2 go-e weg          → keine Befehle mehr, Wallbox autonom
  E3 Škoda alt/weg     → Betrieb unverändert, SoC-Schätzung/letzter Wert
  E4 Forecast weg      → Betrieb unverändert, letzte Prognose
  E5 Sungrow weg       → Werte = 0, weiterarbeiten
  E7 Vaillant/HA weg   → keine WP-Befehle, Ladebetrieb unverändert
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from ..config import RegelConfig
from ..planner import (
    VOLT,
    ChargeController,
    HeatPumpController,
    berechne_ueberschuss,
    plane_garantieladung,
)
from ..safety import SafetyGuard
from ..store import Store

E3DC_MAX_ALTER = timedelta(seconds=60)   # Fail-Safe E1 (Spec §7)
BATT_ENTLADE_SCHWELLE_W = -200           # Entladung Richtung Haus (Spec §5.1)


class ControlLoop:
    def __init__(self, cfg: RegelConfig, guard: SafetyGuard, store: Store, adapters: dict):
        self.cfg = cfg
        self.guard = guard
        self.store = store
        self.adapters = adapters
        self.controller = ChargeController(cfg)
        self.heatpump = HeatPumpController(cfg)   # Stufe 2 (REQ-010/011)
        self.mode = "Nur-PV"                 # Default-Modus (Spec §3)
        self.vehicle_limit_soc = 80          # fahrzeugseitiges Limit (Baseline)
        self._ueberschuss_fenster: list[float] = []  # gleitender Mittelwert über 3 (Spec §2)
        self._last_read: dict[str, datetime] = {}    # letzte erfolgreiche Lesung je Adapter (Tick-Zeit)
        self._sperre_hw_gesetzt = False
        self._last_status: dict = {"state": "start", "grund": "Regelschleife initialisiert"}
        self.running = False

    # --- öffentlich --------------------------------------------------------
    def status(self) -> dict:
        """Live-Zustand für die API (REQ-050)."""
        return self._last_status

    async def run(self) -> None:
        self.running = True
        while self.running:
            try:
                await self.tick(datetime.now())
            except Exception as exc:  # ein Tick-Fehler darf die Schleife nie beenden
                self.store.log_decision(datetime.now(), "tick_fehler", {}, "-", f"Fehler: {exc}")
            await asyncio.sleep(self.cfg.interval_s)

    # --- ein Regelzyklus ---------------------------------------------------
    async def tick(self, now: datetime) -> None:
        # 1) Abgelaufene Leases wegräumen und loggen (ADR-005)
        for lease in self.guard.sweep(now):
            self.store.log_decision(now, "lease_abgelaufen", {"lease": lease.name}, "-", "ausgelaufen")

        # 2) Fail-Safe E1: E3DC frisch? Frische an der Tick-Zeit gemessen (Leo, 2026-07-12)
        e3dc = self.adapters.get("e3dc")
        e_data = await self._safe_read(e3dc)
        if e_data is not None:
            self._last_read["e3dc"] = now
        letzter = self._last_read.get("e3dc")
        if letzter is None or (now - letzter) > E3DC_MAX_ALTER:
            await self._failsafe_e1(now)            # >60 s ohne Daten → abschalten (Spec §7/E1)
            return
        if e_data is None:
            # innerhalb der 60-s-Grace: kein frisches Bild → nichts verändern, Wallbox behält Zustand
            self._last_status = {**self._last_status, "grund": "E3DC-Wert fehlt (Grace <60 s)"}
            return

        goe = self.adapters.get("goe")
        goe_data = await self._safe_read(goe)

        # 3) Sungrow (E5): bei Ausfall Werte = 0 und weiter
        p_sungrow = 0.0
        sg = await self._safe_read(self.adapters.get("sungrow"))
        if sg is not None:
            p_sungrow = sg.get("power_w", 0.0)

        # 4) Fahrzeug-SoC (E3): bei Ausfall unverändert (letzter Wert / Schätzung)
        sk = await self._safe_read(self.adapters.get("skoda"))
        soc_v = sk.get("soc_pct") if sk else (goe_data.get("soc_pct") if goe_data else None)

        # 5) Überschuss (Spec §2) mit gleitendem Mittelwert über 3 Messungen
        p_lade = goe_data.get("power_w", 0.0) if goe_data else 0.0
        surplus_raw = berechne_ueberschuss(
            p_lade, e_data["p_netz_w"], e_data["p_batterie_w"], e_data["soc_batterie_pct"], self.cfg
        )
        surplus = self._glätten(surplus_raw)

        # 6) Garantieladung gegen die Regelliste (Spec §4.3)
        plan = plane_garantieladung(self.store.list_rules(), soc_v if soc_v is not None else 100, now, self.cfg)
        garantie = bool(plan and soc_v is not None and plan.garantie_aktiv(now, soc_v))

        # 7) Zustandsmaschine (Spec §3/§4.1/§4.2)
        connected = goe_data.get("connected", False) if goe_data else False
        cmd = self.controller.update(
            now, surplus_w=surplus, connected=connected, mode=self.mode,
            guarantee_active=garantie, soc_fahrzeug=soc_v, vehicle_limit_soc=self.vehicle_limit_soc,
        )

        # 7b) Wärmepumpe (Stufe 2, REQ-010/011). Vorrang Auto (Leo, 2026-07-25):
        #     die WP sieht nur, was nach der Wallbox-Zuteilung übrig bleibt.
        wp_data = await self._safe_read(self.adapters.get("vaillant"))
        ev_zuteilung_w = cmd.current_a * VOLT * cmd.phases if cmd.charging else 0
        wp_cmd = self.heatpump.update(now, frei_w=surplus - ev_zuteilung_w, wp=wp_data)
        await self._sende_wp(now, wp_cmd)

        # 8) Batterie-Entladesperre als Lease abgleichen (Spec §5.1)
        await self._abgleich_entladesperre(now, e3dc, cmd.charging, e_data["p_batterie_w"])

        # 9) Befehle an die Wallbox — durch die Grenzen-Validierung (Spec §8.3).
        #    Beobachtungsmodus (read_only): Entscheidung nur protokollieren, NICHTS senden.
        if goe is not None and not self.cfg.read_only:
            if cmd.charging:
                amp = self.guard.validate_current(cmd.current_a)
                if amp is not None:
                    await self._safe_cmd(goe.set_phases, cmd.phases)
                    await self._safe_cmd(goe.set_current, amp)
                    await self._safe_cmd(goe.set_charging, True)
            else:
                await self._safe_cmd(goe.set_charging, False)

        # 10) Status + Entscheidungs-Log (REQ-050/062) + Snapshot (Cockpit)
        grund = ("[Beobachtung] " if self.cfg.read_only else "") + cmd.reason
        p_pv_e3dc = e_data.get("p_pv_e3dc_w", 0.0)
        p_pv = p_pv_e3dc + p_sungrow
        # Hausverbrauch aus der Bilanz: PV + Netzbezug − Batterieladung − Wallbox
        p_haus = p_pv + e_data["p_netz_w"] - e_data["p_batterie_w"] - p_lade
        self._last_status = {
            "modus": self.mode, "state": cmd.state.value, "grund": grund,
            "read_only": self.cfg.read_only,
            "laedt": cmd.charging, "strom_a": cmd.current_a, "phasen": cmd.phases,
            "ueberschuss_w": round(surplus), "soc_fahrzeug": soc_v,
            "fahrzeug_limit_soc": self.vehicle_limit_soc,
            "soc_batterie": e_data["soc_batterie_pct"], "p_netz_w": e_data["p_netz_w"],
            "p_batterie_w": e_data["p_batterie_w"], "p_wallbox_w": p_lade,
            "p_pv_w": round(p_pv), "p_pv_e3dc_w": p_pv_e3dc, "p_sungrow_w": p_sungrow,
            "p_haus_w": round(max(0.0, p_haus)),
            "garantieladung": garantie,
            "entladesperre": self.guard.active("e3dc_entladesperre", now),
            # Entprellungs-/Sperr-Transparenz der 1p/3p-Umschaltung (Spec §4.2)
            "phasen_info": self.controller.phase_diagnose(now, surplus),
            # Wärmepumpe, zweigeteilt Warmwasser/Heizkreis (REQ-051, Issue #1)
            "wp": self.heatpump.status(wp_data),
        }
        self.store.log_decision(
            now, grund,
            {"ueberschuss_w": round(surplus), "soc_v": soc_v, "soc_batt": e_data["soc_batterie_pct"]},
            f"{cmd.current_a} A {cmd.phases}p charging={cmd.charging}", cmd.state.value,
        )
        self.store.log_snapshot(
            now,
            ueberschuss_w=round(surplus), p_netz_w=e_data["p_netz_w"],
            p_batterie_w=e_data["p_batterie_w"], soc_batt=e_data["soc_batterie_pct"],
            soc_v=soc_v, p_wallbox_w=p_lade, p_sungrow_w=p_sungrow,
            wuerde_laden=cmd.charging, strom_a=cmd.current_a, phasen=cmd.phases,
            garantie=garantie, read_only=self.cfg.read_only,
        )

    # --- Fail-Safe / Helfer ------------------------------------------------
    async def _failsafe_e1(self, now: datetime) -> None:
        """E3DC weg → laufende Ladung stoppen, Steuerung einstellen (Spec §7/E1).

        Im Beobachtungsmodus wird auch hier NICHTS gesendet — sonst würde die
        Beobachtung das parallel laufende EVCC-Laden abwürgen.
        """
        goe = self.adapters.get("goe")
        if goe is not None and not self.cfg.read_only:
            await self._safe_cmd(goe.set_charging, False)
        # Entladesperre nicht erneuern → läuft per TTL aus (ADR-005)
        self._last_status = {
            "state": "abgeschaltet", "grund": "E3DC nicht erreichbar (Fail-Safe E1)", "laedt": False,
        }
        self.store.log_decision(now, "failsafe_e1", {}, "ladung_stop", "E3DC weg → abgeschaltet")

    async def _sende_wp(self, now: datetime, wp_cmd) -> None:
        """WP-Sollwerte an die MyVaillant-Cloud (REQ-013/014).

        Jeder Aufruf kostet Cloud-Budget — der HeatPumpController hat schon
        entschieden, dass genau jetzt geschrieben werden darf. Im
        Beobachtungsmodus geht NICHTS raus; die Entscheidung steht trotzdem im
        Status ("würde …") und wird nicht als geschrieben bestätigt.
        """
        vaillant = self.adapters.get("vaillant")
        if vaillant is None or self.cfg.read_only:
            return
        if wp_cmd.ww_soll_c is None and wp_cmd.raum_soll_c is None:
            return
        if wp_cmd.ww_soll_c is not None:
            await self._safe_cmd(vaillant.set_ww_soll, wp_cmd.ww_soll_c)
        if wp_cmd.raum_soll_c is not None:
            await self._safe_cmd(vaillant.set_raum_soll, wp_cmd.raum_soll_c)
        self.heatpump.schreiben_bestaetigt(now)
        self.store.log_decision(
            now, wp_cmd.grund,
            {"ww_soll_c": wp_cmd.ww_soll_c, "raum_soll_c": wp_cmd.raum_soll_c},
            "wp_sollwert", "waermepumpe",
        )

    async def _abgleich_entladesperre(self, now, e3dc, charging: bool, p_batterie_w: float) -> None:
        """Sperre setzen, solange geladen wird UND Batterie entlädt; per Lease/TTL (Spec §5.1)."""
        soll = charging and (self.guard.active("e3dc_entladesperre", now) or p_batterie_w < BATT_ENTLADE_SCHWELLE_W)
        if soll:
            self.guard.acquire("e3dc_entladesperre", now, "EV lädt — Batterie-Entladesperre")  # = TTL-Renew
            # read_only: Lease dient nur der Anzeige ("würde sperren"), HW bleibt unberührt
            if not self._sperre_hw_gesetzt and e3dc is not None and not self.cfg.read_only:
                await self._safe_cmd(e3dc.set_entladesperre, True)
                self._sperre_hw_gesetzt = True
        else:
            if self.guard.active("e3dc_entladesperre", now):
                self.guard.release("e3dc_entladesperre")
            if self._sperre_hw_gesetzt and e3dc is not None:
                await self._safe_cmd(e3dc.set_entladesperre, False)
                self._sperre_hw_gesetzt = False

    def _glätten(self, wert: float) -> float:
        self._ueberschuss_fenster.append(wert)
        self._ueberschuss_fenster = self._ueberschuss_fenster[-3:]
        return sum(self._ueberschuss_fenster) / len(self._ueberschuss_fenster)

    async def _safe_read(self, adapter) -> dict | None:
        if adapter is None:
            return None
        try:
            return await adapter.read()
        except Exception:
            return None

    async def _safe_cmd(self, coro_func, *args) -> None:
        try:
            await coro_func(*args)
        except Exception as exc:
            self.store.log_decision(datetime.now(), "cmd_fehler", {"args": str(args)}, "-", f"Fehler: {exc}")
