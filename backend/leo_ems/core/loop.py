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
    EntladeLimitRegler,
    HeatPumpController,
    berechne_ueberschuss,
    plane_garantieladung,
)
from ..safety import SafetyGuard
from ..store import Store

E3DC_MAX_ALTER = timedelta(seconds=60)   # Fail-Safe E1 (Spec §7)
# Ein dauerhaft ausgefallenes Gerät soll das Protokoll nicht zumüllen (6 Ticks/min),
# darin aber auch nicht verschwinden: melden bei Wechsel und danach stündlich.
GERAET_MELDE_INTERVALL = timedelta(minutes=60)
# Prozentpunkte über soc_reserve_pct, bevor die Batterie wieder ans Auto darf
# (Issue #11). Gleiche Größenordnung wie die Hysterese am Vorrang-SoC.
BATT_RESERVE_HYSTERESE = 2


class ControlLoop:
    def __init__(self, cfg: RegelConfig, guard: SafetyGuard, store: Store, adapters: dict):
        self.cfg = cfg
        self.guard = guard
        self.store = store
        self.adapters = adapters
        self.controller = ChargeController(cfg)
        self.heatpump = HeatPumpController(cfg)   # Stufe 2 (REQ-010/011)
        self.batt_limit = EntladeLimitRegler(cfg, guard)  # Entladegrenze Hausbatterie (Spec §5.1)
        self.mode = "Nur-PV"                 # Default-Modus (Spec §3)
        # gleitender Mittelwert über 3 (Spec §2), je Budget-Reihe ein eigenes
        # Fenster: "pv" ist der Überschuss ohne Batterie, "batt" das Budget für
        # den Modus PV+Batterie. Ein gemeinsames Fenster würde nach einem
        # Moduswechsel drei Ticks lang zwei Größen mischen.
        self._fenster: dict[str, list[float]] = {}
        self._batt_reserve_erreicht = False   # Hysterese an soc_reserve_pct (Issue #11)
        self._last_read: dict[str, datetime] = {}    # letzte erfolgreiche Lesung je Adapter (Tick-Zeit)
        self._geraete: dict[str, dict] = {}          # Lese-Gesundheit je Adapter (Diagnose)
        self._limit_hw_w: int | None = None   # zuletzt an die E3DC geschriebene Grenze
        self._last_status: dict = {"state": "start", "grund": "Regelschleife initialisiert"}
        self.running = False

    # --- öffentlich --------------------------------------------------------
    @property
    def vehicle_limit_soc(self) -> int:
        """Fahrzeug-Ladelimit (Issue #9).

        Bewusst nur lesend: bis v0.9.0 war das eine setzbare Instanz-Variable und
        damit nach jedem Add-on-Update wieder auf dem Startwert. Geschrieben wird
        jetzt ausschließlich `cfg.ev_limit_soc` — das persistiert `save_config()`.
        """
        return self.cfg.ev_limit_soc

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
        surplus = self._glätten(surplus_raw, "pv")
        # Zweites Budget für den Modus PV+Batterie (Issue #11): dasselbe Messbild,
        # nur ohne den Batterie-Term — also PV und Batterie zusammen.
        budget_batt = self._glätten(
            berechne_ueberschuss(
                p_lade, e_data["p_netz_w"], e_data["p_batterie_w"],
                e_data["soc_batterie_pct"], self.cfg, mit_batterie=True,
            ),
            "batt",
        )

        # 6) Garantieladung gegen die Regelliste (Spec §4.3)
        plan = plane_garantieladung(self.store.list_rules(), soc_v if soc_v is not None else 100, now, self.cfg)
        garantie = bool(plan and soc_v is not None and plan.garantie_aktiv(now, soc_v))

        # 7) Zuteilung des Überschusses — Reihenfolge = Priorität (Issue #6).
        #
        #    Ein laufender WP-Boost hat keinen Leistungsmesswert: sein Verbrauch
        #    steckt im Hausverbrauch und drückt `surplus` um rund 2 kW. Entschied
        #    die Wallbox gegen diesen gedrückten Wert, gewann faktisch, wer
        #    zuerst angelaufen war — läuft die WP auf Warmwasser, kam das Auto
        #    gar nicht mehr über die Einschaltschwelle (Leos Fehlerbild vom
        #    31.07.). Deshalb wird der Anteil erst zurückgerechnet, dann
        #    zugeteilt: Auto zuerst, die WP bekommt den Rest.
        wp_data = await self._safe_read(self.adapters.get("vaillant"), "vaillant")
        wp_boost_w = self.heatpump.leistung_w(wp_data)
        verteilbar = surplus + wp_boost_w

        # In PV+Batterie regelt die Ladesteuerung gegen das größere Budget
        # (Issue #11). `batt_verfuegbar` schneidet die Freigabe an der Reserve ab;
        # der Modus fällt dann auf reines PV-Laden zurück.
        batt_verfuegbar = self._batt_verfuegbar(e_data["soc_batterie_pct"])
        ev_budget = verteilbar
        if self.mode == "PV+Batterie" and batt_verfuegbar:
            ev_budget = budget_batt + wp_boost_w

        connected = goe_data.get("connected", False) if goe_data else False
        cmd = self.controller.update(
            now, surplus_w=ev_budget, connected=connected, mode=self.mode,
            guarantee_active=garantie, soc_fahrzeug=soc_v,
            vehicle_limit_soc=self.vehicle_limit_soc, batt_verfuegbar=batt_verfuegbar,
        )

        # 7b) Wärmepumpe (Stufe 2, REQ-010/011): sieht, was nach der Wallbox übrig
        #     bleibt. `ev_zuteilung_w` unterscheidet dabei „Sonne weg" von
        #     „das Auto hat es bekommen" — nur im zweiten Fall weicht ein
        #     laufender Boost sofort, ohne Mindestlaufzeit (Issue #6).
        ev_zuteilung_w = cmd.current_a * VOLT * cmd.phases if cmd.charging else 0
        wp_cmd = self.heatpump.update(
            now, frei_w=verteilbar - ev_zuteilung_w, wp=wp_data, ev_zuteilung_w=ev_zuteilung_w
        )
        await self._sende_wp(now, wp_cmd)

        # 8) Entladegrenze der Hausbatterie als Lease abgleichen (Spec §5.1)
        entscheid = self.batt_limit.update(
            charging=cmd.charging, netz_gewollt=cmd.netz_gewollt,
            batt_freigabe=cmd.batt_freigabe,
            soc_batt=e_data["soc_batterie_pct"],
            p_netz_w=e_data["p_netz_w"], p_batterie_w=e_data["p_batterie_w"],
        )
        await self._abgleich_entladegrenze(now, e3dc, entscheid)

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
            # `ueberschuss_w` bleibt der GEMESSENE Wert (so steht er auch in den
            # Snapshots und damit in der Historie). `verteilbar_w` ist das, was
            # tatsächlich zugeteilt wurde — die Differenz ist ein laufender
            # WP-Boost, der sich selbst aus der Rechnung genommen hat (Issue #6).
            "ueberschuss_w": round(surplus), "soc_fahrzeug": soc_v,
            "verteilbar_w": round(verteilbar), "wp_boost_w": round(wp_boost_w),
            "ev_zuteilung_w": round(ev_zuteilung_w),
            # Wogegen die Ladesteuerung wirklich geregelt hat. Weicht in
            # PV+Batterie von `verteilbar_w` ab — die Differenz ist die
            # freigegebene Batterieleistung (Issue #11).
            "ev_budget_w": round(ev_budget),
            "fahrzeug_limit_soc": self.vehicle_limit_soc,
            "soc_batterie": e_data["soc_batterie_pct"], "p_netz_w": e_data["p_netz_w"],
            "p_batterie_w": e_data["p_batterie_w"], "p_wallbox_w": p_lade,
            "p_pv_w": round(p_pv), "p_pv_e3dc_w": p_pv_e3dc, "p_sungrow_w": p_sungrow,
            "p_haus_w": round(max(0.0, p_haus)),
            "garantieladung": garantie,
            # Entladegrenze: `entladesperre` bleibt das grobe Ja/Nein für die
            # Anzeige, `entladelimit_*` zeigt, wie viel die Batterie decken darf.
            "entladesperre": self.guard.active("e3dc_entladesperre", now),
            "entladelimit_w": entscheid.limit_w,
            "entladelimit_art": entscheid.art,
            "entladelimit_grund": entscheid.grund,
            # Entprellungs-/Sperr-Transparenz der 1p/3p-Umschaltung (Spec §4.2)
            "phasen_info": self.controller.phase_diagnose(now, ev_budget),
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
            entladelimit_w=entscheid.limit_w,
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
        # Entladegrenze nicht erneuern → Lease läuft per TTL aus (ADR-005).
        # Was zuletzt in der Anlage stand, gilt nach dem Ausfall als unbekannt:
        # kommt die E3DC zurück, wird die Grenze frisch geschrieben.
        self._limit_hw_w = None
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

    async def _abgleich_entladegrenze(self, now, e3dc, entscheid) -> None:
        """Entladegrenze als Lease abgleichen (Spec §5.1, ADR-005).

        Der Lease heißt weiterhin `e3dc_entladesperre` — er trägt die
        Fail-Safe-Semantik, nicht den Zahlenwert: wird er nicht mehr erneuert,
        läuft er nach `lease_ttl_s` aus und die E3DC regelt wieder autonom.
        """
        if entscheid.limit_w is None:
            if self.guard.active("e3dc_entladesperre", now):
                self.guard.release("e3dc_entladesperre")
            if self._limit_hw_w is not None and e3dc is not None:
                await self._safe_cmd(e3dc.set_entladelimit, None)
                self._limit_hw_w = None
            return

        self.guard.acquire("e3dc_entladesperre", now, entscheid.grund)   # = TTL-Renew
        # read_only: Lease dient nur der Anzeige („würde begrenzen"), HW bleibt unberührt
        if self.cfg.read_only or e3dc is None or not self._schreiben_noetig(entscheid.limit_w):
            return
        await self._safe_cmd(e3dc.set_entladelimit, entscheid.limit_w)
        self._limit_hw_w = entscheid.limit_w
        self.store.log_decision(
            now, entscheid.grund, {"limit_w": entscheid.limit_w},
            "set_power_limits", f"entladegrenze_{entscheid.art}",
        )

    def _schreiben_noetig(self, limit_w: int) -> bool:
        """Schreibdrossel für den RSCP-Weg.

        `set_power_limits` schreibt eine persistente Anlagen-Einstellung — sie
        alle 10 s mit einem um 20 W verschobenen Wert zu beschicken wäre
        unnötiger Verschleiß. Ein Wechsel von oder auf die harte Sperre (0) geht
        dagegen immer sofort raus, denn er ändert die Betriebsart.
        """
        if self._limit_hw_w is None:
            return True
        if limit_w == 0 or self._limit_hw_w == 0:
            return limit_w != self._limit_hw_w
        return abs(limit_w - self._limit_hw_w) > self.cfg.batt_dyn_schreibschwelle_w

    def _batt_verfuegbar(self, soc_batt: float) -> bool:
        """Darf die Hausbatterie gerade ans Auto abgeben (REQ-021, Issue #11)?

        Die Reserve-Schwelle selbst steht in der zentralen Validierung (Spec
        §8.3); hier kommt die **Hysterese** dazu, und zwar genau einmal für das
        ganze System. Ohne sie pendelt es an der Reserve: die Freigabe endet, die
        PV hebt den SoC um einen Punkt, die Freigabe kommt zurück, das Auto zieht
        ihn wieder weg. Das ist nicht nur ein Schreibzugriff je Wechsel — an
        diesem Flag hängt auch das Ladebudget, der Ladestrom würde also
        mitspringen.
        """
        if self._batt_reserve_erreicht:
            frei = soc_batt >= self.cfg.soc_reserve_pct + BATT_RESERVE_HYSTERESE
        else:
            frei = self.guard.validate_battery_discharge(soc_batt)
        self._batt_reserve_erreicht = not frei
        return frei

    def _glätten(self, wert: float, reihe: str = "pv") -> float:
        fenster = self._fenster.setdefault(reihe, [])
        fenster.append(wert)
        del fenster[:-3]
        return sum(fenster) / len(fenster)

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
