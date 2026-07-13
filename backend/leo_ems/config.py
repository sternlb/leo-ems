"""Konfiguration und API-Token-Verwaltung.

Regelparameter mit den Baseline-Defaults aus docs/evcc-baseline.md.
Der API-Token wird beim ersten Start erzeugt und persistiert —
Details in docs/api-token-auth.md.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path

DATA_DIR = Path(os.environ.get("LEO_EMS_DATA_DIR", "./data"))
TOKEN_FILE = DATA_DIR / "api_token"
CONFIG_FILE = DATA_DIR / "config.json"


@dataclass
class RegelConfig:
    """Regelparameter (Spec §2–§5). Alle Werte über die API/App änderbar (REQ-071/072/073)."""

    # Beobachtungsmodus: True = KEINE Steuerbefehle an Geräte, nur messen/loggen.
    # Default True — die erste Installation auf dem Pi läuft gefahrlos parallel
    # zu EVCC (Migrationsstrategie specs/03-architecture.md). Scharfschalten ist
    # ein bewusster Akt über die API/App (PUT /api/v1/config {"read_only": false}).
    read_only: bool = True
    residual_power_w: int = 100        # Ziel-Netzbezug (Spec §2)
    priority_soc_pct: int = 25         # Batterie-Vorrang unterhalb (Spec §2)
    soc_reserve_pct: int = 0           # Batterie-Reserve, Default 0 % (REQ-021)
    interval_s: int = 10               # Regelintervall (Spec §2)
    enable_delay_s: int = 60           # Einschalt-Hysterese (Spec §4.1)
    disable_delay_s: int = 180         # Ausschalt-Hysterese (Spec §4.1)
    min_current_a: int = 6
    max_current_a: int = 16
    phase_up_w: int = 4200             # 1p→3p (Spec §4.2)
    phase_down_w: int = 4000           # 3p→1p (Spec §4.2)
    phase_min_gap_s: int = 600         # Mindestabstand Umschaltungen (Spec §4.2, ⚙1)
    charge_efficiency: float = 0.90    # η Zielladung (Spec §4.3, ⚙2)
    plan_buffer_min: int = 15          # Puffer Zielladung (Spec §4.3, ⚙2)
    lease_ttl_s: int = 900             # TTL für Übersteuerungen, 15 min (Spec §5.1)
    battery_capacity_kwh: float = 77.0 # Enyaq iV80
    # Harte Grenzen: Default KEINE aktiv (REQ-072); None = Grenze inaktiv
    hard_limit_ev_min_soc: int | None = None
    hard_limit_ww_min_temp: float | None = None


def load_config() -> RegelConfig:
    if CONFIG_FILE.exists():
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return RegelConfig(**{k: v for k, v in data.items() if k in RegelConfig.__dataclass_fields__})
    return RegelConfig()


def save_config(cfg: RegelConfig) -> None:
    """Persistiert sofort — Änderungen wirken ohne Neustart (REQ-073)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")


def get_or_create_token() -> str:
    """Statischer API-Token, erzeugt beim ersten Start (docs/api-token-auth.md).

    256 Bit Zufall, URL-safe kodiert. Steht danach in /data/api_token und wird
    beim Add-on-Start ins Log geschrieben, damit er in die App übertragen werden kann.
    """
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    TOKEN_FILE.write_text(token, encoding="utf-8")
    return token
