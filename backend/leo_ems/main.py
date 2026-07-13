"""Einstiegspunkt: startet API (Port 8099) + Regelschleife im selben Prozess."""

from __future__ import annotations

import asyncio

import uvicorn

from .api import create_app
from .config import DATA_DIR, get_or_create_token, load_config
from .core.loop import ControlLoop
from .safety import SafetyGuard
from .store import Store

PORT = 8099  # festgelegt 2026-07-12 (Leo)


async def run() -> None:
    cfg = load_config()
    token = get_or_create_token()
    store = Store(DATA_DIR / "leo_ems.db")
    guard = SafetyGuard(cfg)
    loop = ControlLoop(cfg, guard, store, adapters={})

    # Token einmalig ins Add-on-Log — von dort in die Android-App übertragen
    # (docs/api-token-auth.md, Abschnitt "Token in die App bringen")
    print(f"[leo-ems] API-Token: {token}")
    print(f"[leo-ems] API: http://0.0.0.0:{PORT}/api/v1  (Docs: /docs)")

    app = create_app(store, cfg, token, status_provider=loop.status)
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info"))
    await asyncio.gather(server.serve(), loop.run())


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
