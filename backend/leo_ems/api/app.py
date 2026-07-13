"""Lokale API v1 (Spec §9.1, REQ-050/070–074).

Auth: statischer Bearer-Token für alle Endpunkte außer /health —
Konzept und Begründung in docs/api-token-auth.md.
"""

from __future__ import annotations

import hmac
from dataclasses import asdict
from datetime import datetime, time

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .. import __version__
from ..config import RegelConfig, save_config
from ..planner.rules import ChargingRule
from ..store import Store


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


def create_app(store: Store, cfg: RegelConfig, token: str, status_provider=None) -> FastAPI:
    app = FastAPI(title="Leo-EMS API", version=__version__)

    async def require_token(request: Request) -> None:
        """Bearer-Token-Prüfung mit konstantzeitigem Vergleich (docs/api-token-auth.md)."""
        header = request.headers.get("authorization", "")
        expected = f"Bearer {token}"
        if not hmac.compare_digest(header.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="Ungültiger oder fehlender API-Token")

    auth = Depends(require_token)

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

    return app
