"""API responses are gzip-compressed for clients that ask for it. The app here is a small FastAPI app configured exactly as main.py
configures the middleware (a test below fails if main.py's line drifts from it); main.py itself is not imported because it loads the
NLP engines."""
import gzip
import json
import os

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.testclient import TestClient


def _app():
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.get("/big")
    def big():
        return [{"id": i, "title": "Godrej Properties fined by MahaRERA", "risk_explainability": {"decision_reason": "x" * 200}} for i in range(500)]

    @app.get("/small")
    def small():
        return {"status": "ok"}

    return app


def test_large_json_is_gzipped_when_the_client_accepts_it_and_decodes_to_the_same_payload():
    client = TestClient(_app())
    plain = client.get("/big", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers

    with client.stream("GET", "/big", headers={"Accept-Encoding": "gzip"}) as r:
        raw = b"".join(r.iter_raw())
        assert r.headers["content-encoding"] == "gzip"
        assert "accept-encoding" in r.headers["vary"].lower()
    assert len(raw) < len(plain.content) / 4
    assert json.loads(gzip.decompress(raw)) == plain.json()


def test_small_responses_and_clients_without_accept_encoding_are_left_alone():
    client = TestClient(_app())
    assert "content-encoding" not in client.get("/small", headers={"Accept-Encoding": "gzip"}).headers
    r = client.get("/big", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in r.headers and len(r.json()) == 500


def test_main_wires_the_same_middleware():
    src = open(os.path.join(os.path.dirname(__file__), "..", "app", "main.py"), encoding="utf-8").read()
    assert "from fastapi.middleware.gzip import GZipMiddleware" in src
    assert "app.add_middleware(GZipMiddleware, minimum_size=1024)" in src
