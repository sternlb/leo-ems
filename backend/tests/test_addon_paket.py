"""Regressionsschutz für die Add-on-Verpackung (v0.6.5).

Diese Tests prüfen keine Logik, sondern **Verpackungs-Zusagen**, an denen die
Wärmepumpe schon einmal lautlos gescheitert ist: das Add-on startete direkt
`python -m leo_ems.main`, s6-overlay hat die Umgebung bereinigt, und damit fehlten
sowohl der `SUPERVISOR_TOKEN` (WP kam nicht an die HA-API) als auch
`LEO_EMS_DATA_DIR` (Token, Konfiguration und Beobachtungsdaten waren nach jedem
Update weg). Am Code hätte man das nicht gesehen — deshalb hier.

Begründung im Detail: `run.sh` und `docs/waermepumpe.md`.
"""

from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
DOCKERFILE = (WURZEL / "Dockerfile").read_text(encoding="utf-8")
RUN_SH_BYTES = (WURZEL / "run.sh").read_bytes()
RUN_SH = RUN_SH_BYTES.decode("utf-8")
CONFIG_YAML = (WURZEL / "config.yaml").read_text(encoding="utf-8")
CHANGELOG = WURZEL / "CHANGELOG.md"


def test_start_geht_ueber_run_sh():
    """Kein direktes `CMD ["python", …]` — s6 würde die Umgebung bereinigen."""
    assert 'CMD ["/run.sh"]' in DOCKERFILE
    assert "COPY run.sh /run.sh" in DOCKERFILE


def test_run_sh_holt_die_container_umgebung():
    """Ohne with-contenv im Shebang sieht der Prozess keine Umgebungs-Variablen."""
    assert RUN_SH.startswith("#!/usr/bin/with-contenv")
    assert "exec python -m leo_ems.main" in RUN_SH


def test_run_sh_hat_unix_zeilenenden():
    """CRLF im Shebang („/usr/bin/with-contenv\\r") lässt den Container scheitern."""
    assert b"\r\n" not in RUN_SH_BYTES


def test_run_sh_setzt_das_persistente_datenverzeichnis():
    """Ohne /data liegen Token, Konfiguration und Messdaten im Container-Layer
    und sind nach jedem Add-on-Update weg."""
    assert 'LEO_EMS_DATA_DIR="${LEO_EMS_DATA_DIR:-/data}"' in RUN_SH


def test_addon_darf_die_ha_api_benutzen():
    """Beide Rechte nötig: Core-API (Entities lesen/stellen) und Supervisor-Proxy."""
    assert "homeassistant_api: true" in CONFIG_YAML
    assert "hassio_api: true" in CONFIG_YAML


def test_waermepumpen_entities_sind_vorbelegt():
    """Leeres `vaillant_ww_entity` heißt „WP nicht angebunden" — das darf kein
    Versehen sein, sondern nur eine bewusste Einstellung von Leo."""
    assert 'vaillant_ww_entity: "water_heater.' in CONFIG_YAML
    assert 'vaillant_zone_entity: "climate.' in CONFIG_YAML


def test_versionen_laufen_synchron():
    """config.yaml, pyproject.toml und __version__ müssen dieselbe Version nennen —
    sonst meldet das Dashboard eine andere Version als der Supervisor installiert."""
    from leo_ems import __version__

    assert f'version: "{__version__}"' in CONFIG_YAML
    pyproject = (WURZEL / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{__version__}"' in pyproject


def test_changelog_liegt_neben_der_config():
    """Der Supervisor sucht CHANGELOG.md im Add-on-Verzeichnis — hier die
    Repo-Wurzel, weil dort auch die config.yaml liegt. Fehlt sie, steht im
    Update-Dialog „No changelog found for app ed35676c_leo_ems!"."""
    assert CHANGELOG.is_file()


def test_changelog_kennt_die_aktuelle_version():
    """Ein Update ohne Eintrag zeigt dem Nutzer die Änderungen der Vorversion —
    schlimmer als gar kein Changelog, weil es plausibel aussieht."""
    from leo_ems import __version__

    assert f"## {__version__}" in CHANGELOG.read_text(encoding="utf-8")
