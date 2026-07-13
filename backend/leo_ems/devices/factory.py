"""Adapter-Factory: baut die Geräteadapter aus Verbindungsdaten (ADR-004).

Verbindungsdaten kommen aus Umgebungsvariablen, die das HA-Add-on aus seinen
Optionen setzt (addon/config.yaml) — Zugangsdaten liegen NIE im Code/Repo.
Nur konfigurierte Geräte werden gebaut; Sungrow läuft bis zur Installation
als Stub (0 W).
"""

from __future__ import annotations

import os


def device_connections_from_env() -> dict:
    """Liest optionale Verbindungsdaten aus der Umgebung."""
    g = os.environ.get
    return {
        "e3dc_host": g("LEO_EMS_E3DC_HOST"),
        "e3dc_user": g("LEO_EMS_E3DC_USER"),
        "e3dc_password": g("LEO_EMS_E3DC_PASSWORD"),
        "e3dc_rscp_key": g("LEO_EMS_E3DC_RSCP_KEY"),
        "goe_host": g("LEO_EMS_GOE_HOST"),
        "skoda_user": g("LEO_EMS_SKODA_USER"),
        "skoda_password": g("LEO_EMS_SKODA_PASSWORD"),
        "sungrow_host": g("LEO_EMS_SUNGROW_HOST"),  # leer bis Installation Ende 2026
        "lat": g("LEO_EMS_LAT"),
        "lon": g("LEO_EMS_LON"),
    }


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

    if conn.get("lat") and conn.get("lon"):
        from .forecast import ForecastAdapter
        adapters["forecast"] = ForecastAdapter(float(conn["lat"]), float(conn["lon"]))

    return adapters
