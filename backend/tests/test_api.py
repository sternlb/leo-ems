"""API: Token-Pflicht, Ingress-Ausnahme, Modus-Endpunkt, Dashboard-Auslieferung."""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from leo_ems.api import create_app
from leo_ems.config import RegelConfig
from leo_ems.store import Store

TOKEN = "test-token"


class FakeLoop:
    def __init__(self):
        self.mode = "Nur-PV"
        self.vehicle_limit_soc = 80


def make_client(**kw) -> TestClient:
    store = Store(Path(tempfile.mkdtemp()) / "api.db")
    return TestClient(create_app(store, RegelConfig(), TOKEN, control=FakeLoop(), **kw))


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
    c = make_client(ingress_host="testclient")
    r = c.put("/api/v1/mode", json={"modus": "Schnell", "fahrzeug_limit_soc": 90})
    assert r.status_code == 200
    assert r.json() == {"modus": "Schnell", "fahrzeug_limit_soc": 90}


def test_mode_ungueltig_422():
    c = make_client(ingress_host="testclient")
    assert c.put("/api/v1/mode", json={"modus": "Turbo"}).status_code == 422


def test_dashboard_wird_ausgeliefert():
    """GET / liefert das Web-Dashboard (ohne Auth — reine Statik ohne Geheimnisse)."""
    r = make_client().get("/")
    assert r.status_code == 200 and "Leo-EMS" in r.text
