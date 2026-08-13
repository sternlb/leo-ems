"""API: Token-Pflicht, Ingress-Ausnahme, Modus-Endpunkt, Dashboard-Auslieferung."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from leo_ems import config as config_modul
from leo_ems.api import create_app
from leo_ems.config import RegelConfig
from leo_ems.store import Store

TOKEN = "test-token"


class FakeLoop:
    def __init__(self, cfg: RegelConfig):
        self.cfg = cfg
        self.mode = "Nur-PV"

    @property
    def vehicle_limit_soc(self) -> int:
        return self.cfg.ev_limit_soc


@pytest.fixture(autouse=True)
def datenverzeichnis(tmp_path, monkeypatch):
    """`save_config()` schreibt echt — ohne Umlenkung landete `config.json` im
    Arbeitsverzeichnis des Testlaufs."""
    monkeypatch.setattr(config_modul, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config_modul, "CONFIG_FILE", tmp_path / "config.json")


def make_client(cfg: RegelConfig | None = None, **kw) -> TestClient:
    cfg = cfg or RegelConfig()
    store = Store(Path(tempfile.mkdtemp()) / "api.db")
    return TestClient(create_app(store, cfg, TOKEN, control=FakeLoop(cfg), **kw))


def test_ohne_token_401():
    assert make_client().get("/api/v1/status").status_code == 401


def test_mit_token_ok():
    r = make_client().get("/api/v1/status", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200


def test_ingress_ohne_token_ok():
    """HA-Ingress-Requests (Quelle = Supervisor-Proxy) brauchen keinen Token.
    Der TestClient sendet als Host "testclient" — den deklarieren wir als Ingress-Quelle."""
    c = make_client(ingress_host="testclient")
    assert c.get("/api/v1/status").status_code == 200


def test_mode_put():
    """Angepasst in v0.10.0 (Issue #9): der alte Test setzte das Ladelimit auf
    **90** und schrieb damit genau das Verhalten fest, das die Fahrzeugbatterie
    ungeschützt ließ. 90 % wird jetzt abgelehnt (eigener Test unten); geprüft
    wird hier ein Wert innerhalb der Schutzgrenze."""
    c = make_client(ingress_host="testclient")
    r = c.put("/api/v1/mode", json={"modus": "Schnell", "fahrzeug_limit_soc": 70})
    assert r.status_code == 200
    assert r.json() == {"modus": "Schnell", "fahrzeug_limit_soc": 70}


def test_mode_ungueltig_422():
    c = make_client(ingress_host="testclient")
    assert c.put("/api/v1/mode", json={"modus": "Turbo"}).status_code == 422


def test_modus_pv_batterie_wird_akzeptiert():
    """Neuer Modus aus Issue #11 — steht im Literal von ModeIn."""
    c = make_client(ingress_host="testclient")
    assert c.put("/api/v1/mode", json={"modus": "PV+Batterie"}).status_code == 200


# --- Fahrzeug-Ladelimit: persistent und gedeckelt (Issue #9/#10) --------------
def test_mode_put_persistiert_das_ladelimit():
    """Der eigentliche Fehler aus Issue #9: das Limit lag in einer Instanz-
    Variablen der Regelschleife und war nach jedem Add-on-Update wieder weg."""
    cfg = RegelConfig()
    c = make_client(cfg, ingress_host="testclient")
    c.put("/api/v1/mode", json={"modus": "Nur-PV", "fahrzeug_limit_soc": 65})
    assert cfg.ev_limit_soc == 65
    assert config_modul.load_config().ev_limit_soc == 65


def test_ladelimit_ueber_der_harten_grenze_wird_abgelehnt():
    c = make_client(ingress_host="testclient")
    for pfad, körper in (
        ("/api/v1/mode", {"modus": "Nur-PV", "fahrzeug_limit_soc": 100}),
        ("/api/v1/config", {"ev_limit_soc": 100}),
    ):
        r = c.put(pfad, json=körper)
        assert r.status_code == 400, pfad
        assert "80" in r.json()["detail"]


def test_abgelehnte_konfiguration_wird_nicht_halb_geschrieben():
    """Die Prüfung läuft vor dem ersten setattr — sonst bliebe nach einer
    Ablehnung ein halb übernommener Stand stehen."""
    cfg = RegelConfig()
    c = make_client(cfg, ingress_host="testclient")
    r = c.put("/api/v1/config", json={"soc_reserve_pct": 15, "ev_limit_soc": 95})
    assert r.status_code == 400
    assert cfg.soc_reserve_pct == 0 and cfg.ev_limit_soc == 80


def test_grenze_und_limit_gemeinsam_anheben():
    """Wer wirklich höher laden will, hebt beides — in einem Request erlaubt."""
    cfg = RegelConfig()
    c = make_client(cfg, ingress_host="testclient")
    r = c.put("/api/v1/config", json={"hard_limit_ev_max_soc": 100, "ev_limit_soc": 95})
    assert r.status_code == 200
    assert cfg.ev_limit_soc == 95


def test_dashboard_wird_ausgeliefert():
    """GET / liefert das Web-Dashboard (ohne Auth — reine Statik ohne Geheimnisse)."""
    r = make_client().get("/")
    assert r.status_code == 200 and "Leo-EMS" in r.text
