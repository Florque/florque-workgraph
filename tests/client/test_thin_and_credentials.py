"""The thin client: no engine on import, credentials file, and the account commands of fwg."""

import json
import os
import re
import stat
import subprocess
import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient
from florque_cli.main import app as cli
from florque_client import HttpClient, build_app, load_config
from florque_client.config import (
    credentials_path,
    read_credentials,
    remove_credentials,
    save_credentials,
)
from florque_graph_core.store.memory import MemoryStore
from florque_service import ConsoleSender, IdentityStore, create_app
from florque_signal_hub import SQLiteHubStore
from typer.testing import CliRunner

ENGINE = ("florque_graph_core", "florque_signal_hub", "florque_workgraph_domain")


def test_thin_import_loads_no_engine() -> None:
    code = (
        "import sys, florque_client, florque_cli.main; "
        f"bad = [m for m in sys.modules if m.startswith({ENGINE!r})]; "
        "assert not bad, bad"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_credentials_file_is_private_and_selects_remote(tmp_path) -> None:
    assert load_config(cwd=tmp_path).mode == "local"
    path = save_credentials("https://wg.example.com/", {"token": "fwg_a_b", "token_id": "a"})
    assert path == credentials_path()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    cfg = load_config(cwd=tmp_path)
    assert (cfg.mode, cfg.api_url, cfg.token) == ("remote", "https://wg.example.com", "fwg_a_b")
    os.environ["FLORQUE_TOKEN"] = "fwg_env_wins"
    try:
        assert load_config(cwd=tmp_path).token == "fwg_env_wins"
    finally:
        del os.environ["FLORQUE_TOKEN"]
    assert load_config({"mode": "local"}, cwd=tmp_path).token is None
    assert remove_credentials("https://wg.example.com") is True
    assert read_credentials() == {"default": None, "servers": {}}
    assert load_config(cwd=tmp_path).mode == "local"


def test_token_never_read_from_config_files(tmp_path) -> None:
    (tmp_path / ".florque").mkdir()
    (tmp_path / ".florque" / "config.yaml").write_text("mode: remote\ntoken: fwg_leak_x\n")
    assert load_config(cwd=tmp_path).token is None


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> tuple[IdentityStore, ConsoleSender]:
    app = build_app(graph_store=MemoryStore(), hub_store=SQLiteHubStore())
    identity, mail = IdentityStore(), ConsoleSender()
    api = create_app(app, identity, scheduler=False, email=mail)

    def factory(base_url: str = "", token: str | None = None, **_: Any) -> HttpClient:
        return HttpClient(token=token, http=TestClient(api))

    import florque_cli.main
    import florque_client

    monkeypatch.setattr(florque_cli.main, "HttpClient", factory)
    monkeypatch.setattr(florque_client, "HttpClient", factory)
    return identity, mail


def run(*args: str, input: str | None = None) -> tuple[int, Any, str]:
    r = CliRunner().invoke(cli, ["--api-url", "https://wg.example.com", *args], input=input)
    out = r.stdout
    start = out.find("{")
    return r.exit_code, json.loads(out[start:]) if start >= 0 else None, r.stderr


def test_cli_register_login_whoami_logout(server, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    identity, mail = server
    code = identity.create_invite("a@x.io", "operator")["code"]
    rc, env, _ = run("register", "--invite", code, "--email", "a@x.io", "--tenant-name", "Acme")
    assert rc == 0 and "token" not in env["data"], env
    entry = read_credentials()["servers"]["https://wg.example.com"]
    assert entry["token"].startswith("fwg_") and entry["email"] == "a@x.io"

    # remote mode is now the default: no --mode flag needed
    rc, env, _ = run("whoami")
    assert rc == 0 and env["data"]["tenant"]["name"] == "Acme"
    rc, env, _ = run("projects")
    assert rc == 0 and env["data"]["projects"] == []

    rc, env, err = run("token", "create", "--label", "agent", "--agent")
    assert rc == 0 and env["data"]["token"].startswith("fwg_") and "shown once" in err
    rc, env, _ = run("token", "list")
    assert len(env["data"]["tokens"]) == 2

    # log in again with a prompted code
    rc, env, _ = run("logout")
    assert rc == 0 and env["data"]["revoked"] == entry["token_id"]
    assert identity.resolve(entry["token"]) is None
    rc, env, _ = run("whoami")
    assert rc == 1 and env["error"]["code"] == "UNAUTHENTICATED"

    def prompted_code(*_: Any, **__: Any) -> str:
        m = re.search(r"login code is (\d{6})", mail.outbox[-1]["text"])
        assert m
        return m.group(1)

    monkeypatch.setattr("typer.prompt", prompted_code)
    rc, env, _ = run("login", "--email", "a@x.io", "--label", "laptop")
    assert rc == 0 and env["data"]["tenant"]["name"] == "Acme", env
    rc, env, _ = run("whoami")
    assert rc == 0 and env["data"]["user"]["email"] == "a@x.io"


def test_cli_ontology_extension_lifecycle(server, tmp_path, monkeypatch) -> None:
    from tests.core.test_extensions import EXPERIMENTS

    monkeypatch.chdir(tmp_path)
    identity, _ = server
    code = identity.create_invite("a@x.io", "operator")["code"]
    assert run("register", "--invite", code, "--email", "a@x.io")[0] == 0
    ext = tmp_path / "experiments.yaml"
    ext.write_text(EXPERIMENTS)
    rc, env, _ = run("ontology", "validate", str(ext))
    assert rc == 0, env
    rc, env, _ = run("ontology", "add", str(ext))
    assert rc == 0, env
    ext_id = env["data"]["extension"]["id"]
    rc, env, _ = run("ontology", "show")
    assert "+" in env["data"]["ontology_version"], env
    rc, env, _ = run("ontology", "list")
    assert [e["id"] for e in env["data"]["extensions"]] == [ext_id]
    rc, env, _ = run("ontology", "retire", ext_id)
    assert rc == 0, env


def test_cli_warns_when_outdated(server, tmp_path, monkeypatch) -> None:
    import florque_client.http as http

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(http, "CLIENT_VERSION", "0.1.0")
    code = server[0].create_invite("a@x.io", "operator")["code"]
    rc, env, err = run("register", "--invite", code, "--email", "a@x.io")
    assert rc == 0 and "client_warning" not in env and "uv tool upgrade" in err


def test_cli_use_status_and_session_context(server, tmp_path, monkeypatch) -> None:
    import yaml

    monkeypatch.chdir(tmp_path)
    identity, _ = server
    # not logged in: the session context explains how to connect, and never fails
    r = CliRunner().invoke(cli, ["--api-url", "https://wg.example.com", "session-context"])
    assert r.exit_code == 0 and "login --email" in r.stdout and "{" not in r.stdout
    code = identity.create_invite("a@x.io", "operator")["code"]
    assert run("register", "--invite", code, "--email", "a@x.io")[0] == 0
    p1 = run("create", "Project", "--title", "Apollo")[1]["data"]["node"]["id"]
    run("create", "Goal", "--kind", "objective", "--title", "Ship", "--parent", p1)

    rc, env, _ = run("status")
    assert rc == 1 and env["error"]["code"] == "NOT_FOUND" and env["data"]["user"] == "a@x.io"
    r = CliRunner().invoke(cli, ["session-context"])
    assert r.exit_code == 0 and "No project is bound" in r.stdout and p1 in r.stdout
    rc, env, _ = run("use")  # no tty: lists the choices instead of prompting
    assert rc == 1 and env["error"]["details"]["projects"][0]["id"] == p1

    goal = run("list", "--cls", "Goal", "-p", p1)[1]["data"]["nodes"][0]["id"]
    assert run("use", goal)[1]["error"]["code"] == "SCOPE_VIOLATION"
    rc, env, _ = run("use", p1)
    assert rc == 0 and env["data"]["project"]["title"] == "Apollo"
    cfg = yaml.safe_load((tmp_path / ".florque" / "config.yaml").read_text())
    assert cfg == {"project": p1, "api_url": "https://wg.example.com"}

    sub = tmp_path / "src" / "deep"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)  # the binding applies to subfolders too
    r = CliRunner().invoke(cli, ["status"])
    assert r.exit_code == 0 and json.loads(r.stdout)["data"]["project"]["id"] == p1
    r = CliRunner().invoke(cli, ["session-context"])
    assert "bound to project **Apollo**" in r.stdout and "Objective" in r.stdout

    r = CliRunner().invoke(cli, ["token", "create", "--label", "bot", "--agent", "-p", p1])
    assert (
        r.exit_code == 0 and json.loads(r.stdout[r.stdout.find("{") :])["data"]["project_id"] == p1
    )
    rc, env, _ = run("use", "--clear")
    assert rc == 0 and "project" not in yaml.safe_load(
        (tmp_path / ".florque" / "config.yaml").read_text()
    )
