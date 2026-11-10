"""Security gates: who may call the destructive and shared-configuration endpoints, the per-client source list, and /metrics.
A client_user gets 403 where the endpoint is admin-only; a super admin still works. In-memory SQLite; the app is a small FastAPI app that
wires the real routers exactly as main.py does (a test below fails if main.py's wiring drifts from it)."""
import asyncio
import os
import re
import sys
import uuid

os.environ["DATABASE_URL"] = "postgresql://x:x@127.0.0.1:1/x"
os.environ["DATABASE_URL_POOLED"] = "postgresql://x:x@127.0.0.1:1/x"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.endpoints import admin_users, clients, matching, sources
from app.core.auth import get_current_user, require_client_access, require_super_admin
from app.core.db import Base, get_db
from app.core.metrics_guard import MetricsGuardMiddleware, metrics_decision
from app.models.client import Client
from app.models.document import Document
from app.models.rss_feed import RSSFeed
from app.models.source import Source
from app.models.user import ROLE_SUPER_ADMIN, User, UserClientAccess


@compiles(PG_UUID, "sqlite")
def _uuid(element, compiler, **kw):
    return "CHAR(32)"


@compiles(JSONB, "sqlite")
def _jsonb(element, compiler, **kw):
    return "TEXT"


@pytest.fixture()
def world(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    app = FastAPI()
    auth = [Depends(get_current_user)]
    app.include_router(admin_users.router, prefix="/admin/users", dependencies=[Depends(require_super_admin)])
    app.include_router(clients.router, prefix="/clients", dependencies=auth)
    app.include_router(sources.router, prefix="/sources", dependencies=auth)
    app.include_router(matching.router, prefix="/matching", dependencies=auth)

    state = {"user": None}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: state["user"]

    def mk_user(role, email):
        u = User(id=uuid.uuid4(), email=email, password_hash="x", role=role, is_active=True)
        db.add(u)
        db.commit()
        return u

    admin = mk_user(ROLE_SUPER_ADMIN, "admin@example.invalid")
    viewer = mk_user("client_user", "viewer@example.invalid")
    ga = Client(id=uuid.uuid4(), name="Godrej Properties")
    gb = Client(id=uuid.uuid4(), name="EaseMyTrip")
    db.add_all([ga, gb])
    db.commit()
    db.add(UserClientAccess(user_id=viewer.id, client_id=ga.id))
    db.commit()

    # one source per client (url = the client's feed url) and one linked to nobody
    def mk_source(name, url, client=None, docs=0):
        s = Source(id=uuid.uuid4(), name=name, source_type="rss", url=url, schedule_cron="0 * * * *", is_active=True)
        db.add(s)
        if client is not None:
            db.add(RSSFeed(id=uuid.uuid4(), feed_name=name, feed_url=url, client_id=client.id, category="News"))
        db.commit()
        for i in range(docs):
            db.add(Document(id=uuid.uuid4(), url=f"http://doc/{uuid.uuid4()}", normalized_content="x", title=f"t{i}", source_id=s.id))
        db.commit()
        return s

    s_a = mk_source("Godrej Properties RSS Source", "https://news.example/rss?q=godrej", ga, docs=2)
    s_b = mk_source("EaseMyTrip RSS Source", "https://news.example/rss?q=easemytrip", gb, docs=3)
    s_x = mk_source("Shared wire feed", "https://wire.example/rss")

    class W:
        pass
    w = W()
    w.client = TestClient(app)
    w.db, w.state, w.admin, w.viewer, w.ga, w.gb, w.s_a, w.s_b, w.s_x = db, state, admin, viewer, ga, gb, s_a, s_b, s_x
    w.as_admin = lambda: state.update(user=admin)
    w.as_viewer = lambda: state.update(user=viewer)
    yield w
    db.close()


# ---- A.1 DELETE /clients/{id} ----------------------------------------------------------------------------------------------------
def test_delete_client_is_super_admin_only(world, monkeypatch):
    calls = []
    monkeypatch.setattr(clients, "delete_client", lambda db, cid: calls.append(str(cid)) or {"status": "deleted"})
    world.as_viewer()                                                    # granted this very client: still not allowed
    r = world.client.delete(f"/clients/{world.ga.id}")
    assert r.status_code == 403 and calls == []
    r = world.client.delete(f"/clients/{world.gb.id}")                   # not granted: 403 as before
    assert r.status_code == 403 and calls == []
    world.as_admin()
    r = world.client.delete(f"/clients/{world.ga.id}")
    assert r.status_code == 200 and calls == [str(world.ga.id)]


# ---- A.2 shared configuration writes ------------------------------------------------------------------------------------------------
BODY = {"name": "New feed", "source_type": "rss", "url": "https://new.example/rss", "schedule_cron": "0 * * * *"}


def test_create_source_is_super_admin_only(world):
    n = world.db.query(Source).count()
    world.as_viewer()
    assert world.client.post("/sources/", json=BODY).status_code == 403
    assert world.db.query(Source).count() == n
    world.as_admin()
    r = world.client.post("/sources/", json=BODY)
    assert r.status_code == 200 and r.json()["name"] == "New feed" and world.db.query(Source).count() == n + 1


def test_sources_has_no_put_or_delete_route(world):
    world.as_admin()
    sid = str(world.s_a.id)
    assert world.client.put(f"/sources/{sid}", json=BODY).status_code in (404, 405)
    assert world.client.delete(f"/sources/{sid}").status_code in (404, 405)
    assert world.db.query(Source).count() == 3


def test_refresh_engine_is_super_admin_only(world, monkeypatch):
    calls = []
    monkeypatch.setattr(matching.engine_instance, "refresh_processor", lambda db: calls.append(1) or 7)
    world.as_viewer()
    assert world.client.post("/matching/refresh-engine").status_code == 403 and calls == []
    world.as_admin()
    r = world.client.post("/matching/refresh-engine")
    assert r.status_code == 200 and r.json() == {"status": "success", "keywords_loaded": 7} and calls == [1]


def test_admin_user_endpoints_stay_super_admin_only(world):
    world.as_viewer()
    assert world.client.get("/admin/users/").status_code == 403
    assert world.client.post("/admin/users", json={"email": "x@example.invalid", "role": "client_user", "client_ids": []}).status_code == 403
    assert world.db.query(User).filter(User.email == "x@example.invalid").count() == 0
    world.as_admin()
    assert world.client.get("/admin/users/").status_code == 200


# ---- A.3 GET /sources/ is scoped ---------------------------------------------------------------------------------------------------------
def test_client_user_sees_only_sources_of_their_own_clients(world):
    world.as_viewer()
    r = world.client.get("/sources/")
    assert r.status_code == 200
    rows = r.json()["rss"]
    assert [x["name"] for x in rows] == ["Godrej Properties RSS Source"] and rows[0]["articles"] == 2
    body = r.text
    assert "EaseMyTrip" not in body and str(world.gb.id) not in body and "Shared wire feed" not in body and "easemytrip" not in body.lower()


def test_super_admin_sees_every_source(world):
    world.as_admin()
    rows = world.client.get("/sources/").json()["rss"]
    assert sorted(x["name"] for x in rows) == ["EaseMyTrip RSS Source", "Godrej Properties RSS Source", "Shared wire feed"]
    assert {x["name"]: x["articles"] for x in rows} == {"EaseMyTrip RSS Source": 3, "Godrej Properties RSS Source": 2, "Shared wire feed": 0}


def test_client_user_with_two_clients_sees_both_and_with_none_sees_nothing(world):
    world.as_viewer()
    world.db.add(UserClientAccess(user_id=world.viewer.id, client_id=world.gb.id))
    world.db.commit()
    assert sorted(x["name"] for x in world.client.get("/sources/").json()["rss"]) == ["EaseMyTrip RSS Source", "Godrej Properties RSS Source"]
    world.db.query(UserClientAccess).filter(UserClientAccess.user_id == world.viewer.id).delete()
    world.db.commit()
    assert world.client.get("/sources/").json() == {"rss": [], "reddit": [], "youtube": []}


# ---- A.4 /metrics ------------------------------------------------------------------------------------------------------------------------------
def H(**kw):
    return [(k.replace("_", "-").encode(), v.encode()) for k, v in kw.items()]


@pytest.mark.parametrize("headers,host,expected", [
    (H(), "127.0.0.1", True),                                  # a scraper on the host
    (H(), "172.18.0.5", True),                                 # a Prometheus container on the compose network
    (H(), "10.1.2.3", True),
    (H(), "::1", True),
    (H(x_forwarded_for="203.0.113.9"), "172.18.0.1", False),   # the public proxy reaches the API from a private docker address
    (H(x_real_ip="203.0.113.9"), "172.18.0.1", False),
    (H(forwarded="for=203.0.113.9"), "172.18.0.1", False),
    (H(x_forwarded_proto="https"), "172.18.0.1", False),
    (H(), "203.0.113.9", False),                               # straight from the internet
    (H(), None, False),
    (H(), "not-an-ip", False),
])
def test_metrics_without_a_token_is_internal_only(headers, host, expected):
    assert metrics_decision(headers, host, None)[0] is expected
    assert metrics_decision(headers, host, "  ")[0] is expected               # a blank token counts as unset


def test_metrics_with_a_token_needs_the_bearer_from_anywhere():
    ok = H(authorization="Bearer s3cret-token")
    assert metrics_decision(ok, "203.0.113.9", "s3cret-token") == (True, 200)
    assert metrics_decision(H(x_forwarded_for="1.2.3.4", authorization="bearer s3cret-token"), "172.18.0.1", " s3cret-token ") == (True, 200)
    assert metrics_decision(H(), "127.0.0.1", "s3cret-token") == (False, 401)                  # internal is not enough once a token is set
    for bad in ("Bearer wrong", "Bearer ", "Basic s3cret-token", "s3cret-token", "Bearer s3cret-token-x"):
        assert metrics_decision(H(authorization=bad), "127.0.0.1", "s3cret-token") == (False, 401), bad


def _call(path, headers, host, monkeypatch, token=None):
    if token is None:
        monkeypatch.delenv("METRICS_TOKEN", raising=False)
    else:
        monkeypatch.setenv("METRICS_TOKEN", token)
    sent = []
    inner = []

    async def app(scope, receive, send):
        inner.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"metrics"})

    async def send(m):
        sent.append(m)

    scope = {"type": "http", "path": path, "headers": headers, "client": (host, 5000) if host else None}
    asyncio.run(MetricsGuardMiddleware(app)(scope, None, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    hdrs = dict(next(m["headers"] for m in sent if m["type"] == "http.response.start"))
    return status, hdrs, inner


def test_middleware_blocks_the_public_path_and_leaves_other_paths_alone(monkeypatch):
    st, _, inner = _call("/metrics", H(x_forwarded_for="1.2.3.4"), "172.18.0.1", monkeypatch)
    assert st == 403 and inner == []                                                          # the app never saw the request
    st, _, inner = _call("/metrics", H(), "127.0.0.1", monkeypatch)
    assert st == 200 and inner == ["/metrics"]
    st, hdrs, inner = _call("/metrics", H(), "127.0.0.1", monkeypatch, token="tok")
    assert st == 401 and hdrs[b"www-authenticate"] == b"Bearer" and inner == []
    st, _, inner = _call("/metrics", H(authorization="Bearer tok"), "203.0.113.9", monkeypatch, token="tok")
    assert st == 200 and inner == ["/metrics"]
    for other in ("/health", "/client-intelligence/x/risks", "/metricsx", "/metrics/"):
        st, _, inner = _call(other, H(x_forwarded_for="1.2.3.4"), "203.0.113.9", monkeypatch, token="tok")
        assert st == 200 and inner == [other], other                                         # only /metrics itself is guarded


# ---- the test app really mirrors main.py ---------------------------------------------------------------------------------------------------
def test_main_wires_the_same_routers_and_the_guard():
    src = open(os.path.join(os.path.dirname(__file__), "..", "app", "main.py"), encoding="utf-8").read()
    assert 'app.include_router(clients.router, prefix="/clients", tags=["clients"], dependencies=_auth)' in src
    assert 'app.include_router(sources.router, prefix="/sources", tags=["sources"], dependencies=_auth)' in src
    assert 'app.include_router(matching.router, prefix="/matching", tags=["matching"], dependencies=_auth)' in src
    assert 'app.include_router(admin_users.router, prefix="/admin/users", tags=["admin_users"], dependencies=_super_admin_only)' in src
    assert "app.add_middleware(MetricsGuardMiddleware)" in src
    assert re.search(r"from app\.core\.metrics_guard import MetricsGuardMiddleware", src)
