"""Adapter-Factory: baut die Geräteadapter aus Verbindungsdaten (ADR-004).

Verbindungsdaten kommen aus Umgebungsvariablen, die das HA-Add-on aus seinen
Optionen setzt (addon/config.yaml) — Zugangsdaten liegen NIE im Code/Repo.
Nur konfigurierte Geräte werden gebaut; Sungrow läuft bis zur Installation
als Stub (0 W).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

OPTIONS_FILE = Path("/data/options.json")  # vom HA-Supervisor aus den Add-on-Optionen geschrieben

_KEYS = (
    "e3dc_host", "e3dc_user", "e3dc_password", "e3dc_rscp_key",
    "goe_host", "skoda_user", "skoda_password", "sungrow_host", "lat", "lon",
    # Wärmepumpe über Home Assistant (Stufe 2, devices/vaillant.py).
    # ha_base_url/ha_token leer = Supervisor-Proxy + SUPERVISOR_TOKEN.
    "ha_base_url", "ha_token", "vaillant_ww_entity", "vaillant_zone_entity",
)


def load_device_connections() -> dict:
    """Verbindungsdaten aus den Add-on-Optionen (/data/options.json), Fallback Umgebung.

    Zugangsdaten kommen aus den Add-on-Optionen (addon/config.yaml) und liegen nie
    im Code/Repo. Für lokale Entwicklung greift der Fallback auf LEO_EMS_<KEY>.
    """
    opts: dict = {}
    if OPTIONS_FILE.exists():
        opts = json.loads(OPTIONS_FILE.read_text(encoding="utf-8"))

    def val(key: str):
        v = opts.get(key)
        if v in (None, ""):
            v = os.environ.get(f"LEO_EMS_{key.upper()}")
        return v or None

    return {k: val(k) for k in _KEYS}


# Rückwärtskompatibler Alias
def device_connections_from_env() -> dict:  # pragma: no cover
    return load_device_connections()


def build_adapters(conn: dict) -> dict:
    """Erzeugt die Adapter-Map. Fehlende Geräte werden übersprungen."""
    adapters: dict = {}

    if conn.get("e3dc_host"):
        from .e3dc import E3dcAdapter
        adapters["e3dc"] = E3dcAdapter(
            conn["e3dc_host"], conn["e3dc_user"], conn["e3dc_password"], conn["e3dc_rscp_key"]
        )

    if conn.get("goe_host"):
        from .goe import GoeAdapter
        adapters["goe"] = GoeAdapter(conn["goe_host"])

    if conn.get("skoda_user"):
        from .skoda import SkodaAdapter
        adapters["skoda"] = SkodaAdapter(conn["skoda_user"], conn["skoda_password"])

    # Sungrow: real ab Installation, sonst Stub 0 W (Fail-Safe/Übergang, Spec §6)
    if conn.get("sungrow_host"):
        from .sungrow import SungrowAdapter
        adapters["sungrow"] = SungrowAdapter(conn["sungrow_host"])
    else:
        from .sungrow import SungrowStub
        adapters["sungrow"] = SungrowStub()

    # Wärmepumpe: nur bauen, wenn eine Warmwasser-Entity konfiguriert ist.
    # Leeres Feld = WP nicht angebunden, das Dashboard zeigt dann „nicht verbunden".
    if conn.get("vaillant_ww_entity"):
        from .vaillant import ZONE_ENTITY, VaillantAdapter
        adapters["vaillant"] = VaillantAdapter(
            base_url=conn.get("ha_base_url"),
            token=conn.get("ha_token"),
            ww_entity=conn["vaillant_ww_entity"],
            zone_entity=conn.get("vaillant_zone_entity") or ZONE_ENTITY,
        )

    if conn.get("lat") and conn.get("lon"):
        from .forecast import ForecastAdapter
        adapters["forecast"] = ForecastAdapter(float(conn["lat"]), float(conn["lon"]))

    return adapters
