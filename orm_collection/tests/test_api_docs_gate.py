"""/docs, /redoc and /openapi.json are hidden unless ENABLE_API_DOCS is true (default false).

main.py is not imported here (it loads the whole app); a test checks it is wired to the same helper and setting."""
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.api_docs import docs_kwargs
from app.core.config import Settings


def _client(enabled: bool) -> TestClient:
    app = FastAPI(**docs_kwargs(enabled))

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return TestClient(app)


def test_docs_schema_and_redoc_are_404_when_disabled_but_routes_still_work():
    c = _client(False)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(path).status_code == 404, path
    assert c.get("/ping").json() == {"ok": True}


def test_docs_are_served_when_enabled():
    c = _client(True)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(path).status_code == 200, path


def test_default_setting_is_off(monkeypatch):
    monkeypatch.delenv("ENABLE_API_DOCS", raising=False)
    assert Settings.model_fields["ENABLE_API_DOCS"].default is False


def test_main_is_wired_to_the_setting():
    src = open(os.path.join(os.path.dirname(__file__), "..", "app", "main.py"), encoding="utf-8").read()
    assert "from app.core.api_docs import docs_kwargs" in src
    assert "**docs_kwargs(settings.ENABLE_API_DOCS)" in src
