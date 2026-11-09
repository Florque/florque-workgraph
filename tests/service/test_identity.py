"""Accounts end to end: invite -> register -> login -> tokens, email delivery, rate limits,
and tenant isolation over HTTP."""

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from florque_client import build_app
from florque_graph_core.errors import GraphError
from florque_graph_core.store.memory import MemoryStore
from florque_service import ConsoleSender, IdentityStore, ResendSender, create_app
from florque_service.email import EmailError, sender_from_env
from florque_signal_hub import SQLiteHubStore


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class Svc:
    def __init__(self, tc: TestClient, identity: IdentityStore, mail: ConsoleSender) -> None:
        self.tc, self.identity, self.mail = tc, identity, mail

    def last_code(self, pattern: str) -> str:
        m = re.search(pattern, self.mail.outbox[-1]["text"])
        assert m, self.mail.outbox[-1]
        return m.group(1)

    def signup(self, email: str, tenant: str) -> dict[str, Any]:
        code = self.identity.create_invite(email, "operator")["code"]
        r = self.tc.post(
            "/v1/auth/register",
            json={"invite_code": code, "email": email, "name": email[0], "tenant_name": tenant},
        )
        assert r.status_code == 201, r.json()
        return r.json()["data"]  # type: ignore[no-any-return]


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def svc(clock: Clock) -> Iterator[Svc]:
    app = build_app(graph_store=MemoryStore(), hub_store=SQLiteHubStore())
    identity = IdentityStore(clock=clock)
    mail = ConsoleSender()
    api = create_app(app, identity, scheduler=False, email=mail, auth_rate_limit=1000)
    with TestClient(api) as tc:
        yield Svc(tc, identity, mail)


# ---------------------------------------------------------------- identity store


def test_invite_is_single_use_and_bound_to_email(clock: Clock) -> None:
    ids = IdentityStore(clock=clock)
    inv = ids.create_invite("a@x.io", "operator")
    assert re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}", inv["code"])
    with pytest.raises(GraphError, match="another email"):
        ids.register(inv["code"], "b@x.io", "B")
    out = ids.register(inv["code"].lower(), "A@x.io", "A", "Acme")
    assert out["tenant"]["name"] == "Acme" and out["token"].startswith("fwg_")
    with pytest.raises(GraphError, match="invalid, used or expired"):
        ids.register(inv["code"], "a@x.io", "A")
    late = ids.create_invite("c@x.io", "operator")
    clock.now += timedelta(days=15)
    with pytest.raises(GraphError, match="expired"):
        ids.register(late["code"], "c@x.io", "C")


def test_second_invite_joins_existing_tenant(clock: Clock) -> None:
    ids = IdentityStore(clock=clock)
    a = ids.register(ids.create_invite("a@x.io", "operator")["code"], "a@x.io", "A", "Acme")
    tid = a["tenant"]["id"]
    b = ids.register(ids.create_invite("b@x.io", a["user"]["id"], tid)["code"], "b@x.io", "B")
    assert b["tenant"]["id"] == tid
    with pytest.raises(GraphError, match="already registered"):
        ids.register(ids.create_invite("a@x.io", "operator")["code"], "a@x.io", "A")
    info = ids.resolve(b["token"])
    assert info is not None and info.principal.tenant_id == tid
    assert info.principal.roles == {"*": "admin"} and info.principal.can_create_projects


def test_login_codes_expire_and_limit_attempts(clock: Clock) -> None:
    ids = IdentityStore(clock=clock)
    ids.register(ids.create_invite("a@x.io", "operator")["code"], "a@x.io", "A")
    assert ids.start_login("nobody@x.io") is None
    code = ids.start_login("a@x.io")
    assert code is not None and re.fullmatch(r"\d{6}", code)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        with pytest.raises(GraphError):
            ids.verify_login("a@x.io", wrong)
    with pytest.raises(GraphError):  # locked after 5 attempts, even with the right code
        ids.verify_login("a@x.io", code)
    code = ids.start_login("a@x.io")
    assert code is not None
    clock.now += timedelta(minutes=11)
    with pytest.raises(GraphError, match="expired"):
        ids.verify_login("a@x.io", code)
    code = ids.start_login("a@x.io")
    assert code is not None
    out = ids.verify_login("a@x.io", code, label="laptop")
    assert ids.resolve(out["token"]) is not None
    with pytest.raises(GraphError):  # one use only
        ids.verify_login("a@x.io", code)


def test_tokens_expire_and_revoke(clock: Clock) -> None:
    ids = IdentityStore(clock=clock)
    out = ids.register(ids.create_invite("a@x.io", "operator")["code"], "a@x.io", "A")
    assert ids.resolve(out["token"]) is not None
    clock.now += timedelta(days=91)
    assert ids.resolve(out["token"]) is None
    clock.now -= timedelta(days=91)
    ingest = ids.issue_ingest_token(out["tenant"]["id"], out["user"]["id"], "ci")
    info = ids.resolve(ingest["token"])
    assert info is not None and info.kind == "ingest" and info.principal.roles == {"*": "hub"}
    assert ids.revoke(ingest["token_id"], "tenant_other") is False
    assert ids.revoke(ingest["token_id"], out["tenant"]["id"]) is True
    assert ids.resolve(ingest["token"]) is None
    assert ids.resolve("fwg_nope_nope") is None and ids.resolve("garbage") is None


def test_tokens_are_stored_hashed(tmp_path) -> None:
    db = tmp_path / "service.sqlite"
    ids = IdentityStore(str(db))
    token = ids.issue("op", {"*": "admin"})["token"]
    assert token.split("_", 2)[2].encode() not in db.read_bytes()
    assert IdentityStore(str(db)).resolve(token) is not None  # survives a restart


# ---------------------------------------------------------------- email


def test_resend_sender_posts_the_message() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "em_1"})

    s = ResendSender(
        "re_key",
        "Florque <beta@florque.com>",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    s.send("a@x.io", "Hi", "Body")
    req = seen[0]
    assert str(req.url) == "https://api.resend.com/emails"
    assert req.headers["authorization"] == "Bearer re_key"
    import json

    assert json.loads(req.content) == {
        "from": "Florque <beta@florque.com>",
        "to": ["a@x.io"],
        "subject": "Hi",
        "text": "Body",
    }
    bad = ResendSender(
        "k",
        "f@x.io",
        http=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(422, text="invalid from"))
        ),
    )
    with pytest.raises(EmailError, match="422"):
        bad.send("a@x.io", "Hi", "Body")


def test_sender_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert isinstance(sender_from_env(), ConsoleSender)
    monkeypatch.setenv("FLORQUE_ENV", "production")
    with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
        sender_from_env()
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    with pytest.raises(RuntimeError, match="FLORQUE_EMAIL_FROM"):
        sender_from_env()
    monkeypatch.setenv("FLORQUE_EMAIL_FROM", "beta@florque.com")
    assert isinstance(sender_from_env(), ResendSender)


def test_email_failure_is_an_envelope(clock: Clock) -> None:
    class Broken:
        def send(self, to: str, subject: str, text: str) -> None:
            raise EmailError("down")

    app = build_app(graph_store=MemoryStore(), hub_store=SQLiteHubStore())
    ids = IdentityStore(clock=clock)
    with TestClient(create_app(app, ids, scheduler=False, email=Broken())) as tc:
        ids.register(ids.create_invite("a@x.io", "operator")["code"], "a@x.io", "A")
        r = tc.post("/v1/auth/login", json={"email": "a@x.io"})
        assert r.status_code == 403 and r.json()["ok"] is False


# ---------------------------------------------------------------- HTTP flows


def test_register_login_me_tokens_over_http(svc: Svc) -> None:
    tc = svc.tc
    a = svc.signup("a@x.io", "Acme")
    assert "token" in a and a["tenant"]["name"] == "Acme"
    me = tc.get("/v1/auth/me", headers=auth(a["token"])).json()["data"]
    assert me["user"]["email"] == "a@x.io" and me["tenant"]["id"] == a["tenant"]["id"]

    r = tc.post("/v1/auth/login", json={"email": "a@x.io"})
    assert r.status_code == 202
    code = svc.last_code(r"login code is (\d{6})")
    # unknown addresses get the same answer and no email
    sent = len(svc.mail.outbox)
    assert tc.post("/v1/auth/login", json={"email": "ghost@x.io"}).status_code == 202
    assert len(svc.mail.outbox) == sent
    v = tc.post("/v1/auth/verify", json={"email": "a@x.io", "code": code, "label": "laptop"})
    assert v.status_code == 200
    laptop = v.json()["data"]["token"]

    t = tc.post("/v1/auth/tokens", json={"label": "agent", "agent": True}, headers=auth(laptop))
    assert t.status_code == 201
    agent = t.json()["data"]
    listed = tc.get("/v1/auth/tokens", headers=auth(laptop)).json()["data"]["tokens"]
    assert {agent["token_id"], v.json()["data"]["token_id"]} <= {x["id"] for x in listed}
    assert all("hash" not in x for x in listed)
    assert (
        tc.delete(f"/v1/auth/tokens/{agent['token_id']}", headers=auth(laptop)).status_code == 200
    )
    assert tc.get("/v1/auth/me", headers=auth(agent["token"])).status_code == 401
    assert (
        tc.delete(f"/v1/auth/tokens/{agent['token_id']}", headers=auth(laptop)).status_code == 404
    )


def test_members_invite_colleagues_by_email(svc: Svc) -> None:
    tc = svc.tc
    a = svc.signup("a@x.io", "Acme")
    r = tc.post("/v1/auth/invites", json={"email": "b@x.io"}, headers=auth(a["token"]))
    assert r.status_code == 201 and "code" not in r.json()["data"]
    assert svc.mail.outbox[-1]["to"] == "b@x.io" and "Acme" in svc.mail.outbox[-1]["text"]
    code = svc.last_code(r"Invite code: (\S+)")
    b = tc.post("/v1/auth/register", json={"invite_code": code, "email": "b@x.io"}).json()["data"]
    assert b["tenant"]["id"] == a["tenant"]["id"]
    r = tc.post("/v1/auth/invites", json={"email": "not-an-email"}, headers=auth(a["token"]))
    assert r.json()["ok"] is False


def test_tenants_are_isolated_over_http(svc: Svc) -> None:
    tc = svc.tc
    a = auth(svc.signup("a@x.io", "Acme")["token"])
    b = auth(svc.signup("b@y.io", "Beta")["token"])
    pa = tc.post("/v1/projects", json={"props": {"title": "Apollo"}}, headers=a).json()["data"]
    pid = pa["node"]["id"]
    goal = tc.post(
        "/v1/nodes",
        json={"cls": "Goal", "props": {"kind": "objective", "title": "Ship"}, "parent_id": pid},
        headers=a,
    ).json()["data"]["node"]["id"]
    # same title in another tenant is not a duplicate
    assert (
        tc.post("/v1/projects", json={"props": {"title": "Apollo"}}, headers=b).status_code == 201
    )
    assert [p["id"] for p in tc.get("/v1/projects", headers=a).json()["data"]["projects"]] == [pid]
    assert pid not in str(tc.get("/v1/projects", headers=b).json())
    assert tc.get(f"/v1/nodes/{goal}", headers=b).status_code == 404
    r = tc.post(
        "/v1/nodes",
        json={"cls": "Goal", "props": {"kind": "objective", "title": "X"}, "parent_id": pid},
        headers=b,
    )
    assert r.status_code == 404
    assert tc.get(f"/v1/projects/{pid}/nodes", headers=b).status_code in (403, 404)


def test_ingest_tokens_only_push_observations(svc: Svc) -> None:
    tc = svc.tc
    a = auth(svc.signup("a@x.io", "Acme")["token"])
    t = tc.post("/v1/auth/tokens", json={"kind": "ingest", "label": "ci"}, headers=a)
    ingest = auth(t.json()["data"]["token"])
    assert tc.get("/v1/projects", headers=ingest).status_code == 403
    assert tc.get("/v1/auth/me", headers=ingest).status_code == 403
    r = tc.post(
        "/v1/hub/observations",
        json={
            "source": "ci",
            "series_code": "x.y",
            "value": 1,
            "observed_at": "2026-11-10T12:00:00Z",
        },
        headers=ingest,
    )
    assert r.status_code not in (401, 403), r.json()
    assert tc.post("/v1/auth/tokens", json={"kind": "root"}, headers=a).json()["ok"] is False


def test_operator_tokens_cannot_use_account_endpoints(svc: Svc) -> None:
    op = auth(svc.identity.issue("ops", {"*": "admin"})["token"])
    assert svc.tc.get("/v1/auth/me", headers=op).status_code == 403


# ---------------------------------------------------------------- guards


def test_rate_limits_answer_429() -> None:
    app = build_app(graph_store=MemoryStore(), hub_store=SQLiteHubStore())
    api = create_app(app, IdentityStore(), scheduler=False, rate_limit=3, auth_rate_limit=2)
    with TestClient(api) as tc:
        codes = [tc.post("/v1/auth/login", json={"email": "a@x.io"}).status_code for _ in range(3)]
        assert codes == [202, 202, 429]
        r = tc.post("/v1/auth/login", json={"email": "a@x.io"})
        assert r.json()["error"]["code"] == "RATE_LIMITED" and int(r.headers["retry-after"]) >= 1
        codes = [tc.get("/v1/projects").status_code for _ in range(4)]
        assert codes[:3] == [401, 401, 401] and codes[3] == 429
        assert tc.get("/healthz").status_code == 200  # probes are not limited


def test_body_limit_and_min_client_header(svc: Svc) -> None:
    r = svc.tc.post(
        "/v1/auth/login",
        content=b"{}",
        headers={"content-length": str(2 * 1024 * 1024), "content-type": "application/json"},
    )
    assert r.status_code == 413
    assert svc.tc.get("/healthz").headers["x-florque-min-client"] == "0.2.0"


def test_agent_user_tokens_propose_and_cannot_accept(svc: Svc) -> None:
    tc = svc.tc
    human = auth(svc.signup("a@x.io", "Acme")["token"])
    agent_tok = tc.post("/v1/auth/tokens", json={"label": "bot", "agent": True}, headers=human)
    agent = auth(agent_tok.json()["data"]["token"])
    pid = tc.post("/v1/projects", json={"props": {"title": "P"}}, headers=human).json()["data"][
        "node"
    ]["id"]
    body = {
        "cls": "Goal",
        "props": {"kind": "objective", "title": "G", "status": "active"},
        "parent_id": pid,
    }
    node = tc.post("/v1/nodes", json=body, headers=agent).json()["data"]["node"]
    assert node["status"] == "proposed"
    r = tc.patch(f"/v1/nodes/{node['id']}", json={"patch": {"status": "active"}}, headers=agent)
    assert r.status_code == 403
    r = tc.patch(f"/v1/nodes/{node['id']}", json={"patch": {"status": "active"}}, headers=human)
    assert r.status_code == 200
    r = tc.patch(f"/v1/nodes/{node['id']}", json={"patch": {"status": "done"}}, headers=agent)
    assert r.status_code == 200 and r.json()["data"]["node"]["status"] == "done"


def test_project_scoped_tokens(svc: Svc) -> None:
    tc = svc.tc
    human = auth(svc.signup("a@x.io", "Acme")["token"])
    other_tenant = auth(svc.signup("b@y.io", "Beta")["token"])
    p1 = tc.post("/v1/projects", json={"props": {"title": "P1"}}, headers=human).json()["data"]
    p2 = tc.post("/v1/projects", json={"props": {"title": "P2"}}, headers=human).json()["data"]
    p1, p2 = p1["node"]["id"], p2["node"]["id"]
    foreign = tc.post("/v1/projects", json={"props": {"title": "X"}}, headers=other_tenant)
    r = tc.post(
        "/v1/auth/tokens",
        json={"label": "bot", "agent": True, "project_id": foreign.json()["data"]["node"]["id"]},
        headers=human,
    )
    assert r.status_code == 404
    r = tc.post("/v1/auth/tokens", json={"label": "bot", "project_id": p1}, headers=human)
    assert r.status_code == 201 and r.json()["data"]["project_id"] == p1
    bot = auth(r.json()["data"]["token"])

    assert tc.get("/v1/auth/me", headers=bot).json()["data"]["token"]["project_id"] == p1
    assert [p["id"] for p in tc.get("/v1/projects", headers=bot).json()["data"]["projects"]] == [p1]
    goal = {"cls": "Goal", "props": {"kind": "objective", "title": "G"}}
    assert tc.post("/v1/nodes", json={**goal, "parent_id": p1}, headers=bot).status_code == 201
    assert tc.post("/v1/nodes", json={**goal, "parent_id": p2}, headers=bot).status_code in (
        403,
        404,
    )
    assert tc.get(f"/v1/nodes/{p2}", headers=bot).status_code in (403, 404)
    assert tc.post("/v1/projects", json={"props": {"title": "P3"}}, headers=bot).status_code == 403
    # a scoped token cannot widen itself, mint ingest tokens or invite people
    r = tc.post("/v1/auth/tokens", json={"project_id": p2}, headers=bot)
    assert r.status_code == 403
    r = tc.post("/v1/auth/tokens", json={"label": "child"}, headers=bot)
    assert r.status_code == 201 and r.json()["data"]["project_id"] == p1
    assert tc.post("/v1/auth/tokens", json={"kind": "ingest"}, headers=bot).status_code == 403
    assert tc.post("/v1/auth/invites", json={"email": "c@x.io"}, headers=bot).status_code == 403
