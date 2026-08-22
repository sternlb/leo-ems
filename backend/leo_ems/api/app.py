"""Lokale API v1 (Spec §9.1, REQ-050/070–074) + Web-Dashboard (HA-Ingress).

Auth: statischer Bearer-Token für alle Endpunkte außer /health —
Konzept und Begründung in docs/api-token-auth.md. Requests über das
HA-Ingress kommen immer vom Supervisor-Proxy (172.30.32.2) und sind
bereits durch die Home-Assistant-Anmeldung geschützt → kein Token nötig.
"""

from __future__ import annotations

import asyncio
import hmac
import os
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..config import DATA_DIR, TOKEN_FILE, RegelConfig, save_config
from ..energy import KANAELE, ImportBericht, importiere_e3dc_historie
from ..planner.rules import ChargingRule
from ..store import Store

# Feste Quell-IP des HA-Ingress-Proxys (Supervisor-Doku, „Ingress“)
INGRESS_PROXY_HOST = "172.30.32.2"
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class RuleIn(BaseModel):
    """Regel-Schema Spec §4.3: {wochentage[], abfahrtszeit, soc_min, aktiv}."""

    wochentage: list[int] = Field(..., description="0=Mo … 6=So")
    abfahrtszeit: str = Field(..., examples=["07:30"])
    soc_min: int = Field(..., ge=0, le=100)
    aktiv: bool = True

    def to_rule(self) -> ChargingRule:
        return ChargingRule(
            weekdays=frozenset(self.wochentage),
            departure=time.fromisoformat(self.abfahrtszeit),
            soc_min_pct=self.soc_min,
            active=self.aktiv,
        )


class ModeIn(BaseModel):
    """Lademodus-Wechsel (Spec §3); Fahrzeug-Limit optional gleich mit."""

    modus: Literal["Nur-PV", "PV+Min", "PV+Batterie", "Schnell", "Aus"]
    fahrzeug_limit_soc: int | None = Field(None, ge=0, le=100)


def create_app(
    store: Store,
    cfg: RegelConfig,
    token: str,
    status_provider=None,
    control=None,
    ingress_host: str = INGRESS_PROXY_HOST,
) -> FastAPI:
    app = FastAPI(title="Leo-EMS API", version=__version__)

    async def require_token(request: Request) -> None:
        """Bearer-Token-Prüfung mit konstantzeitigem Vergleich (docs/api-token-auth.md).

        Ausnahme: HA-Ingress. Der Supervisor-Proxy ist die einzige Quelle mit
        dieser IP, und Home Assistant hat den Nutzer dort bereits angemeldet.
        """
        client = request.client
        if client is not None and client.host == ingress_host:
            return
        header = request.headers.get("authorization", "")
        expected = f"Bearer {token}"
        if not hmac.compare_digest(header.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="Ungültiger oder fehlender API-Token")

    auth = Depends(require_token)

    def _pruefe_ev_limit(neu: int, grenze: int | None = ...) -> None:
        """Fahrzeug-Ladelimit gegen die harte Obergrenze (Issue #9).

        Bewusst eine Ablehnung mit Klartext statt einer stillen Deckelung: wer
        90 % eingibt und danach 80 % im Feld sieht, hält das für einen Bug. Wer
        wirklich höher laden will, hebt erst `hard_limit_ev_max_soc` — ein
        zweiter, sichtbarer Schritt (REQ-072).
        """
        if grenze is ...:
            grenze = cfg.hard_limit_ev_max_soc
        if grenze is not None and neu > grenze:
            raise HTTPException(
                status_code=400,
                detail=(f"Fahrzeug-Ladelimit {neu} % über der harten Obergrenze {grenze} %. "
                        f"Zum Anheben zuerst 'hard_limit_ev_max_soc' ändern."),
            )

    # --- Web-Dashboard (HA-Sidebar via Ingress; auch direkt im LAN aufrufbar) ----
    @app.get("/", include_in_schema=False)
    async def index() -> HTMLResponse:
        """Statische Seite ohne Auth — enthält keine Geheimnisse; alle Daten
        holt sie über die (Token-/Ingress-geschützte) API."""
        return HTMLResponse((WEB_DIR / "index.html").read_text(encoding="utf-8"))

    # Produktfotos fürs Dashboard (Leo hat sie 2026-07-14 aus den vorgeschlagenen
    # Kandidaten ausgewählt: E3DC S10E, Enyaq iV80, Vaillant aroTHERM plus).
    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")

    @app.get("/api/v1/health")
    async def health():
        """Ohne Auth — für den Supervisor-Watchdog (addon/config.yaml)."""
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/status", dependencies=[auth])
    async def status():
        """Live-Zustand inkl. Klartext-Begründung (REQ-050). Stub bis core/loop steht."""
        if status_provider is not None:
            return status_provider()
        return {"hinweis": "Regelschleife noch nicht aktiv (Phase 4 in Arbeit)", "version": __version__}

    # --- Geräte-Diagnose ---------------------------------------------------------
    @app.get("/api/v1/diag/devices", dependencies=[auth])
    async def diag_devices():
        """Jeden Adapter einmal aktiv lesen und im Klartext berichten, was passiert.

        Für die Frage „warum zeigt Gerät XY keine Werte?": die Regelschleife muss
        Lesefehler schlucken (Fail-Safe-Matrix, Spec §7) — hier stehen sie im
        Klartext, inklusive der Wege, die der Vaillant-Adapter probiert hat.
        """
        if control is None:
            raise HTTPException(status_code=503, detail="Regelschleife nicht aktiv")
        proben: dict = {}
        for name, adapter in sorted(control.adapters.items()):
            try:
                proben[name] = {"ok": True, "werte": await adapter.read()}
            except Exception as exc:
                proben[name] = {"ok": False, "fehler": f"{type(exc).__name__}: {exc}"}
        return {"probe": proben, "laufend": control.geraete_status()}

    @app.get("/api/v1/diag/umgebung", dependencies=[auth])
    async def diag_umgebung():
        """Laufumgebung des Add-ons — Datenverzeichnis und Umgebungs-Variablen.

        Beantwortet die zwei Fragen, die sich beim WP-Zugang gestellt haben:
        liefert der Supervisor überhaupt einen Token, und ist `/data` wirklich
        das persistente Volume? Es werden nur **Namen** von Variablen
        zurückgegeben, nie Werte — dort stehen Zugangsdaten drin.
        """
        return {
            "version": __version__,
            "data_dir": str(DATA_DIR.resolve()),
            "data_dir_ist_mountpoint": os.path.ismount(str(DATA_DIR)),
            "data_dir_inhalt": sorted(p.name for p in DATA_DIR.glob("*")) if DATA_DIR.exists() else [],
            "token_datei": {
                "pfad": str(TOKEN_FILE),
                "vorhanden": TOKEN_FILE.exists(),
                # Gleiches Alter wie der Prozess = bei jedem Start neu → /data ist nicht persistent
                "geaendert": (
                    datetime.fromtimestamp(TOKEN_FILE.stat().st_mtime).isoformat(timespec="seconds")
                    if TOKEN_FILE.exists() else None
                ),
            },
            "umgebung": sorted(os.environ),
        }

    # --- Lademodus + Fahrzeug-Limit (REQ-071) -----------------------------------
    @app.put("/api/v1/mode", dependencies=[auth])
    async def mode_put(update: ModeIn):
        """Setzt den Lademodus (und optional das Fahrzeug-Ladelimit) live in der Regelschleife.

        Das Ladelimit landet in der Konfiguration und wird sofort persistiert —
        bis v0.9.0 schrieb es in eine Instanz-Variable der Regelschleife und war
        nach dem nächsten Add-on-Update wieder weg (Issue #9).
        """
        if control is None:
            raise HTTPException(status_code=503, detail="Regelschleife nicht aktiv")
        control.mode = update.modus
        if update.fahrzeug_limit_soc is not None:
            _pruefe_ev_limit(update.fahrzeug_limit_soc)
            cfg.ev_limit_soc = update.fahrzeug_limit_soc
            save_config(cfg)
        return {"modus": control.mode, "fahrzeug_limit_soc": cfg.ev_limit_soc}

    # --- Regeln (REQ-070/073) -------------------------------------------------
    @app.get("/api/v1/rules", dependencies=[auth])
    async def rules_list():
        return [
            {
                "id": r.rule_id,
                "wochentage": sorted(r.weekdays),
                "abfahrtszeit": r.departure.isoformat("minutes"),
                "soc_min": r.soc_min_pct,
                "aktiv": r.active,
            }
            for r in store.list_rules()
        ]

    @app.post("/api/v1/rules", dependencies=[auth], status_code=201)
    async def rules_add(rule: RuleIn):
        rule_id = store.add_rule(rule.to_rule())
        return {"id": rule_id}

    @app.put("/api/v1/rules/{rule_id}", dependencies=[auth])
    async def rules_update(rule_id: int, rule: RuleIn):
        if not store.update_rule(rule_id, rule.to_rule()):
            raise HTTPException(status_code=404, detail="Regel nicht gefunden")
        return {"ok": True}

    @app.delete("/api/v1/rules/{rule_id}", dependencies=[auth])
    async def rules_delete(rule_id: int):
        if not store.delete_rule(rule_id):
            raise HTTPException(status_code=404, detail="Regel nicht gefunden")
        return {"ok": True}

    # --- Konfiguration (REQ-071/072/073) ---------------------------------------
    @app.get("/api/v1/config", dependencies=[auth])
    async def config_get():
        return asdict(cfg)

    @app.put("/api/v1/config", dependencies=[auth])
    async def config_put(update: dict):
        for key in update:
            if key not in RegelConfig.__dataclass_fields__:
                raise HTTPException(status_code=400, detail=f"Unbekannter Parameter: {key}")
        # Vollständig prüfen, bevor irgendetwas gesetzt wird — sonst bliebe bei
        # einer Ablehnung ein halb geschriebener Stand stehen. Geprüft wird gegen
        # das ERGEBNIS, damit Grenze und Limit in einem Request gemeinsam
        # angehoben werden können (Issue #9).
        _pruefe_ev_limit(
            update.get("ev_limit_soc", cfg.ev_limit_soc),
            update.get("hard_limit_ev_max_soc", cfg.hard_limit_ev_max_soc),
        )
        for key, value in update.items():
            setattr(cfg, key, value)
        save_config(cfg)  # sofort persistent, kein Neustart (REQ-073)
        return asdict(cfg)

    # --- Protokoll (REQ-062) ----------------------------------------------------
    @app.get("/api/v1/history", dependencies=[auth])
    async def history(limit: int = 200):
        return store.recent_decisions(limit)

    # --- Beobachtungs-Auswertung (Cockpit, docs/cockpit.md) -----------------------
    @app.get("/api/v1/observation/summary", dependencies=[auth])
    async def observation_summary():
        """Aggregierte Kennzahlen: EMS-Entscheidung vs. real gemessene Wallbox."""
        return store.observation_summary(cfg.interval_s)

    @app.get("/api/v1/observation/snapshots", dependencies=[auth])
    async def observation_snapshots(limit: int = 1000):
        """Rohdaten (je Tick ein Messbild), chronologisch — für Verlaufscharts."""
        return store.snapshots_recent(limit)

    # --- Energiebilanz: Tag / Monat / Jahr (Issue #13) ---------------------------
    # Getrennt von /observation, obwohl beides „Historie" ist: Snapshots sind
    # Ticks für die Beobachtungsphase und werden irgendwann entsorgt, die
    # Energiebilanz ist der dauerhafte Bestand, aus dem Leo Jahre vergleicht.

    def _kwh(zeilen: list[dict]) -> list[dict]:
        """Wh → kWh direkt an der Schnittstelle.

        Intern wird in Wh gerechnet, weil die E3DC Wh liefert und Rundung auf
        kWh je Tag sich über ein Jahr zu spürbaren Beträgen summiert. Nach außen
        geht kWh — in dieser Einheit steht es auf der Rechnung und im Dashboard.
        """
        raus = []
        for z in zeilen:
            neu_z = {k: v for k, v in z.items() if k not in KANAELE}
            for k in KANAELE:
                neu_z[k[:-3] + "_kwh"] = round(float(z.get(k) or 0.0) / 1000.0, 3)
            raus.append(neu_z)
        return raus

    @app.get("/api/v1/energie/tage", dependencies=[auth])
    async def energie_tage(von: str | None = None, bis: str | None = None):
        return _kwh(store.energie_tage(von, bis))

    @app.get("/api/v1/energie/monate", dependencies=[auth])
    async def energie_monate(jahr: str | None = None):
        return _kwh(store.energie_gruppiert("monat", jahr))

    @app.get("/api/v1/energie/jahre", dependencies=[auth])
    async def energie_jahre():
        return _kwh(store.energie_gruppiert("jahr"))

    @app.get("/api/v1/energie/export.csv", dependencies=[auth])
    async def energie_export(ebene: Literal["tag", "monat", "jahr"] = "tag",
                             jahr: str | None = None):
        """CSV, weil es die Ablage ist, die überall aufgeht — Excel, LibreOffice,
        Python. Semikolon als Trenner und Komma als Dezimalzeichen: Excel in
        deutscher Ländereinstellung zerlegt eine Punkt-Komma-Datei sonst in eine
        einzige Spalte, und genau dort landet die Datei."""
        zeilen = _kwh(store.energie_tage() if ebene == "tag"
                      else store.energie_gruppiert(ebene, jahr))
        if not zeilen:
            return PlainTextResponse("", media_type="text/csv")
        spalten = list(zeilen[0].keys())

        def feld(w) -> str:
            return str(w).replace(".", ",") if isinstance(w, float) else str(w if w is not None else "")

        kopf = ";".join(spalten)
        koerper = "\n".join(";".join(feld(z.get(c)) for c in spalten) for z in zeilen)
        text = kopf + "\n" + koerper
        return PlainTextResponse(text, media_type="text/csv", headers={
            "Content-Disposition": f'attachment; filename="leo-ems-energie-{ebene}.csv"'})

    @app.post("/api/v1/energie/import", dependencies=[auth])
    async def energie_import(von: str | None = None, bis: str | None = None):
        """Historie aus der E3DC nachladen (Issue #13).

        Läuft als Hintergrund-Task und antwortet sofort: Drei Jahre sind über
        tausend RSCP-Abrufe, und ein HTTP-Request, der Minuten offen steht,
        läuft in jedem Proxy dazwischen in einen Timeout. Der Fortschritt steht
        unter GET /api/v1/energie/import.

        Nur ein Import gleichzeitig — zwei parallele Läufe würden sich dieselbe
        RSCP-Sitzung teilen und einander die Antworten wegnehmen.
        """
        if control is None:
            raise HTTPException(status_code=503, detail="Regelschleife nicht aktiv")
        adapter = getattr(control, "adapters", {}).get("e3dc")
        if adapter is None or not hasattr(adapter, "historie_tag"):
            raise HTTPException(status_code=503, detail="E3DC-Adapter kann keine Historie liefern")
        laufend = getattr(control, "energie_import", None)
        if laufend is not None and laufend.laeuft:
            raise HTTPException(status_code=409, detail="Es läuft bereits ein Import")

        # Default-Fenster: ab dem Tag nach der letzten bekannten Zeile zurück
        # bis maximal fünf Jahre. Ohne Angabe soll ein Klick genügen und der
        # zweite Klick darf nicht alles noch einmal holen.
        heute = date.today()
        d_von = date.fromisoformat(von) if von else heute - timedelta(days=5 * 365)
        d_bis = date.fromisoformat(bis) if bis else heute - timedelta(days=1)
        if d_von > d_bis:
            raise HTTPException(status_code=400, detail="'von' liegt nach 'bis'")

        bericht = ImportBericht(d_von.isoformat(), d_bis.isoformat())
        control.energie_import = bericht
        garage = getattr(cfg, "pv_garage_seit", None)
        asyncio.get_running_loop().create_task(importiere_e3dc_historie(
            adapter, store, d_von, d_bis, bericht,
            garage_seit=date.fromisoformat(garage) if garage else None,
        ))
        return bericht.as_dict()

    @app.get("/api/v1/energie/import", dependencies=[auth])
    async def energie_import_status():
        bericht = getattr(control, "energie_import", None) if control else None
        return bericht.as_dict() if bericht else {"laeuft": False, "hinweis": "noch kein Import gelaufen"}

    return app
