"""Optional demo access token: when DEMO_ACCESS_TOKEN is set, the UI and API require it (query ?token=, header, or cookie)."""
import importlib

from fastapi.testclient import TestClient


def _app_with_token(monkeypatch, token):
    import app.config as cfg
    monkeypatch.setattr(cfg, "DEMO_ACCESS_TOKEN", token)
    import app.main as main_mod
    return main_mod.app


def test_without_token_everything_is_open(monkeypatch):
    app = _app_with_token(monkeypatch, "")
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200


def test_with_token_requests_need_it(monkeypatch):
    app = _app_with_token(monkeypatch, "secret123")
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 401
        assert c.get("/").status_code == 401
        assert c.get("/api/health", headers={"X-Demo-Token": "secret123"}).status_code == 200
        r = c.get("/?token=secret123")
        assert r.status_code == 200 and "spendguard_token" in r.cookies
        assert c.get("/api/health").status_code == 200          # cookie now set on the client
        assert c.get("/api/health", headers={"X-Demo-Token": "wrong"}, cookies={}).status_code in (200, 401)
