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
# Ein dauerhaft ausgefallenes Gerät soll das Protokoll nicht zumüllen (6 Ticks/min),
# darin aber auch nicht verschwinden: melden bei Wechsel und danach stündlich.
GERAET_MELDE_INTERVALL = timedelta(minutes=60)


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
        self._geraete: dict[str, dict] = {}          # Lese-Gesundheit je Adapter (Diagnose)
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
        e_data = await self._safe_read(e3dc, "e3dc")
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
        goe_data = await self._safe_read(goe, "goe")

        # 3) Sungrow (E5): bei Ausfall Werte = 0 und weiter
        p_sungrow = 0.0
        sg = await self._safe_read(self.adapters.get("sungrow"), "sungrow")
        if sg is not None:
            p_sungrow = sg.get("power_w", 0.0)

        # 4) Fahrzeug-SoC (E3): bei Ausfall unverändert (letzter Wert / Schätzung)
        sk = await self._safe_read(self.adapters.get("skoda"), "skoda")
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
        wp_data = await self._safe_read(self.adapters.get("vaillant"), "vaillant")
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
            "wp": {
                **self.heatpump.status(wp_data),
                # „nicht verbunden" allein hilft bei der Suche nicht weiter (v0.6.2)
                "fehler": (self._geraete.get("vaillant") or {}).get("fehler"),
            },
            # Lese-Gesundheit aller Geräte (Diagnose, /api/v1/diag/devices)
            "geraete": self.geraete_status(),
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

    # --- Lese-Gesundheit der Geräte (Diagnose) ------------------------------
    def geraete_status(self) -> dict:
        """Pro Adapter: liest er, seit wann, und woran es sonst hakt.

        Die Fail-Safe-Matrix verlangt, dass ein Lesefehler den Betrieb nicht
        anhält — bis v0.6.1 war er deshalb aber auch nirgends sichtbar. Genau das
        hat die nicht angebundene Wärmepumpe so lange versteckt (v0.6.2).
        """
        return {
            name: {
                "ok": z["ok"],
                "fehler": z["fehler"],
                "seit": z["seit"].isoformat(timespec="seconds") if z["seit"] else None,
                "letzte_lesung": (
                    z["letzte_lesung"].isoformat(timespec="seconds") if z["letzte_lesung"] else None
                ),
            }
            for name, z in sorted(self._geraete.items())
        }

    def _geraet(self, name: str) -> dict:
        return self._geraete.setdefault(
            name, {"ok": True, "fehler": None, "seit": None, "letzte_lesung": None, "gemeldet": None}
        )

    def _melden(self, z: dict, now: datetime, name: str, text: str) -> None:
        """Nur bei Wechsel oder nach GERAET_MELDE_INTERVALL — sonst schweigen."""
        letzte = z["gemeldet"]
        if letzte is not None and now - letzte < GERAET_MELDE_INTERVALL:
            return
        z["gemeldet"] = now
        print(f"[leo-ems] {name}: {text}", flush=True)
        self.store.log_decision(now, f"gerät_{name}", {}, "-", text)

    async def _safe_read(self, adapter, name: str | None = None) -> dict | None:
        if adapter is None:
            return None
        name = name or getattr(adapter, "name", "gerät")
        z = self._geraet(name)
        now = datetime.now()
        try:
            daten = await adapter.read()
        except Exception as exc:
            text = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            if z["ok"] or z["fehler"] != text:
                z["seit"], z["gemeldet"] = now, None       # neuer Fehler → sofort melden
            z["ok"], z["fehler"] = False, text
            self._melden(z, now, name, f"liest nicht — {text}")
            return None

        if not z["ok"]:
            z["seit"], z["gemeldet"] = now, None
            z["ok"], z["fehler"] = True, None
            self._melden(z, now, name, "liest wieder")
        # Teil-Ausfälle meldet der Adapter selbst (z. B. einzelne HA-Entities)
        z["fehler"] = getattr(adapter, "letzter_fehler", None)
        z["letzte_lesung"] = now
        return daten

    async def _safe_cmd(self, coro_func, *args) -> None:
        try:
            await coro_func(*args)
        except Exception as exc:
            self.store.log_decision(datetime.now(), "cmd_fehler", {"args": str(args)}, "-", f"Fehler: {exc}")
