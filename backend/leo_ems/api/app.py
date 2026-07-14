"""Lokale API v1 (Spec §9.1, REQ-050/070–074) + Web-Dashboard (HA-Ingress).

Auth: statischer Bearer-Token für alle Endpunkte außer /health —
Konzept und Begründung in docs/api-token-auth.md. Requests über das
HA-Ingress kommen immer vom Supervisor-Proxy (172.30.32.2) und sind
bereits durch die Home-Assistant-Anmeldung geschützt → kein Token nötig.
"""

from __future__ import annotations

import hmac
from dataclasses import asdict
from datetime import datetime, time
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .. import __version__
from ..config import RegelConfig, save_config
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

    modus: Literal["Nur-PV", "PV+Min", "Schnell", "Aus"]
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

    # --- Web-Dashboard (HA-Sidebar via Ingress; auch direkt im LAN aufrufbar) ----
    @app.get("/", include_in_schema=False)
    async def index() -> HTMLResponse:
        """Statische Seite ohne Auth — enthält keine Geheimnisse; alle Daten
        holt sie über die (Token-/Ingress-geschützte) API."""
        return HTMLResponse((WEB_DIR / "index.html").read_text(encoding="utf-8"))

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

    # --- Lademodus + Fahrzeug-Limit (REQ-071) -----------------------------------
    @app.put("/api/v1/mode", dependencies=[auth])
    async def mode_put(update: ModeIn):
        """Setzt den Lademodus (und optional das Fahrzeug-Ladelimit) live in der Regelschleife."""
        if control is None:
            raise HTTPException(status_code=503, detail="Regelschleife nicht aktiv")
        control.mode = update.modus
        if update.fahrzeug_limit_soc is not None:
            control.vehicle_limit_soc = update.fahrzeug_limit_soc
        return {"modus": control.mode, "fahrzeug_limit_soc": control.vehicle_limit_soc}

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
        for key, value in update.items():
            if key not in RegelConfig.__dataclass_fields__:
                raise HTTPException(status_code=400, detail=f"Unbekannter Parameter: {key}")
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

    return app
