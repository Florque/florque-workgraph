"""fwg: one command for agents and humans, local or remote (spec 8). JSON in, JSON out."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer
from florque_client import Client, Config, HttpClient, client_from_config, load_config
from florque_client.config import (
    read_credentials,
    remove_credentials,
    save_credentials,
    update_project_config,
)

app = typer.Typer(
    help="Florque Workgraph CLI. Output is the JSON response envelope.", no_args_is_help=True
)
hub_app = typer.Typer(
    help="Signal hub: sources, sensors, ingestion, inbox, evaluation.", no_args_is_help=True
)
source_app = typer.Typer(help="Registered observation sources (admin).", no_args_is_help=True)
sensor_app = typer.Typer(
    help="Sensors: series codes bound to a project (admin).", no_args_is_help=True
)
inbox_app = typer.Typer(help="Observations the hub could not route.", no_args_is_help=True)
token_app = typer.Typer(help="Your API tokens (remote mode).", no_args_is_help=True)
ontology_app = typer.Typer(
    help="Ontology: the base schema plus your tenant/project extensions.", no_args_is_help=True
)
app.add_typer(token_app, name="token")
app.add_typer(ontology_app, name="ontology")
app.add_typer(hub_app, name="hub")
hub_app.add_typer(source_app, name="source")
hub_app.add_typer(sensor_app, name="sensor")
hub_app.add_typer(inbox_app, name="inbox")


class State:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._client: Client | None = None
        self.account = False

    @property
    def client(self) -> Client:
        if self._client is None:
            try:
                self._client = client_from_config(self.cfg)
            except Exception as e:  # noqa: BLE001 - surface wiring problems as an envelope
                _emit(
                    {
                        "ok": False,
                        "error": {
                            "code": "UNAVAILABLE",
                            "message": str(e),
                            "hint": "Check fwg configuration.",
                            "details": {},
                        },
                    },
                    self,
                )
        return self._client  # type: ignore[return-value]

    def project(self, given: str | None) -> str:
        pid = given or self.cfg.project
        if not pid:
            _emit(
                {
                    "ok": False,
                    "error": {
                        "code": "ONTOLOGY_VIOLATION",
                        "message": "No project given",
                        "hint": "Pass --project or set FLORQUE_PROJECT.",
                        "details": {},
                    },
                },
                self,
            )
        return pid  # type: ignore[return-value]

    @property
    def remote(self) -> HttpClient:
        """An HTTP client for account commands, whatever the configured mode."""
        self.account = True
        return HttpClient(self.cfg.api_url, self.cfg.token)

    @property
    def state_file(self) -> Path:
        return Path(self.cfg.config_dir or ".florque") / "state.json"


def _st(ctx: typer.Context) -> State:
    return ctx.obj  # type: ignore[no-any-return]


def _emit(env: dict[str, Any], st: State | None = None) -> None:
    warning = env.pop("client_warning", None)
    error = env.get("error") or {}
    if st is not None and st.account and error.get("code") == "UNAVAILABLE":
        error["hint"] = (
            f"Account commands talk to the service at {st.cfg.api_url}. "
            "Pass --api-url https://<server> (register/login remember it) or set FLORQUE_API_URL."
        )
    typer.echo(json.dumps(env, indent=2, default=str))
    if warning:
        typer.echo(f"warning: {warning}", err=True)
    if st is not None and env.get("ontology_version"):
        _drift_hint(st, env["ontology_version"])
    raise typer.Exit(0 if env.get("ok") else 1)


def _drift_hint(st: State, version: str) -> None:
    try:
        known = json.loads(st.state_file.read_text()).get("ontology_version")
    except (OSError, ValueError):
        return
    if known and known != version:
        typer.echo(f"hint: ontology changed ({known} -> {version}); run `fwg sync`.", err=True)


def _value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _pairs(items: list[str] | None, what: str = "KEY=VALUE") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in items or []:
        key, sep, val = item.partition("=")
        if not sep:
            raise typer.BadParameter(f"expected {what}, got {item!r}")
        out[key] = _value(val)
    return out


def _json_arg(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return {}
    text = sys.stdin.read() if raw == "-" else raw
    data = json.loads(text)
    if not isinstance(data, dict):
        raise typer.BadParameter("--json must be an object")
    return data


@app.callback()
def main(
    ctx: typer.Context,
    mode: str | None = typer.Option(None, help="local or remote (FLORQUE_MODE)"),
    api_url: str | None = typer.Option(None, help="Service URL in remote mode (FLORQUE_API_URL)"),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project id (FLORQUE_PROJECT)"
    ),
    store: str | None = typer.Option(
        None, help="Local graph store: neo4j, file or memory (FLORQUE_STORE)"
    ),
) -> None:
    ctx.obj = State(
        load_config({"mode": mode, "api_url": api_url, "project": project, "store": store})
    )


# ---------------------------------------------------------------- graph commands


@app.command()
def describe(
    ctx: typer.Context, project: str | None = typer.Option(None, "--project", "-p")
) -> None:
    """Ontology version, classes and the generated card (with the project's extensions)."""
    st = _st(ctx)
    _emit(st.client.describe(project or st.cfg.project), st)


@app.command()
def projects(ctx: typer.Context, include_archived: bool = False) -> None:
    """Projects you can see."""
    st = _st(ctx)
    _emit(st.client.projects(include_archived), st)


@app.command()
def get(ctx: typer.Context, node_id: str, depth: int = typer.Option(1, min=0, max=3)) -> None:
    """A node with its parent chain and neighbours."""
    st = _st(ctx)
    _emit(st.client.get(node_id, depth), st)


@app.command()
def search(
    ctx: typer.Context,
    query: str,
    cls: str | None = typer.Option(None, "--cls"),
    limit: int = 20,
    project: str | None = typer.Option(None, "--project", "-p"),
) -> None:
    """Lexical search inside one project. Search before creating."""
    st = _st(ctx)
    _emit(st.client.search(st.project(project), query, cls, limit), st)


@app.command("list")
def list_nodes(
    ctx: typer.Context,
    cls: str | None = typer.Option(None, "--cls"),
    filter: list[str] | None = typer.Option(None, "--filter", "-f", help="FIELD=VALUE, repeatable"),
    include_archived: bool = False,
    project: str | None = typer.Option(None, "--project", "-p"),
) -> None:
    """Nodes of a project, optionally by class and field filters."""
    st = _st(ctx)
    _emit(st.client.list_nodes(st.project(project), cls, _pairs(filter), include_archived), st)


@app.command()
def create(
    ctx: typer.Context,
    cls: str = typer.Argument(
        ..., help="Class, e.g. Goal, WorkItem, Document, Signal, Actor, Project"
    ),
    title: str | None = typer.Option(None),
    kind: str | None = typer.Option(None),
    parent: str | None = typer.Option(None, "--parent", help="Parent node id"),
    prop: list[str] | None = typer.Option(
        None, "--prop", help="FIELD=VALUE (JSON values allowed), repeatable"
    ),
    edge: list[str] | None = typer.Option(
        None, "--edge", help="EDGE:TARGET_ID, e.g. serves:goal_123"
    ),
    json_: str | None = typer.Option(None, "--json", help='Full request as JSON, or "-" for stdin'),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    confirm_new: bool = typer.Option(
        False, "--confirm-new", help="Create despite DUPLICATE_SIMILAR candidates"
    ),
) -> None:
    """Create a node and its parent edge in one transaction."""
    st = _st(ctx)
    req = _json_arg(json_)
    props = {**req.get("props", {}), **_pairs(prop)}
    if title:
        props["title"] = title
    if kind:
        props["kind"] = kind
    edges = list(req.get("edges") or [])
    for e in edge or []:
        etype, sep, to = e.partition(":")
        if not sep:
            raise typer.BadParameter(f"--edge expects EDGE:TARGET_ID, got {e!r}")
        edges.append({"type": etype, "to": to})
    _emit(
        st.client.create(
            req.get("cls", cls),
            props,
            parent or req.get("parent_id"),
            edges or None,
            idempotency_key or req.get("idempotency_key"),
            confirm_new or bool(req.get("confirm_new")),
        ),
        st,
    )


@app.command()
def update(
    ctx: typer.Context,
    node_id: str,
    set_: list[str] | None = typer.Option(
        None, "--set", help="FIELD=VALUE, repeatable; VALUE null clears"
    ),
    json_: str | None = typer.Option(None, "--json", help='Patch object as JSON, or "-" for stdin'),
    if_version: int | None = typer.Option(None, "--if-version"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
) -> None:
    """Additive patch with optimistic concurrency."""
    st = _st(ctx)
    patch = {**_json_arg(json_), **_pairs(set_)}
    _emit(st.client.update(node_id, patch, if_version, idempotency_key), st)


@app.command()
def archive(ctx: typer.Context, node_id: str, cascade: bool = False) -> None:
    """Archive a node (refuses with live children unless --cascade)."""
    st = _st(ctx)
    _emit(st.client.archive(node_id, cascade), st)


@app.command()
def move(ctx: typer.Context, node_id: str, new_parent_id: str) -> None:
    """Re-parent a node with the same validation as create."""
    st = _st(ctx)
    _emit(st.client.move(node_id, new_parent_id), st)


@app.command()
def link(
    ctx: typer.Context,
    src: str,
    edge: str,
    dst: str,
    prop: list[str] | None = typer.Option(None, "--prop", help="Edge property FIELD=VALUE"),
) -> None:
    """Typed edge between existing nodes, e.g. fwg link task_1 depends_on task_2."""
    st = _st(ctx)
    _emit(st.client.link(src, edge, dst, _pairs(prop) or None), st)


@app.command()
def unlink(ctx: typer.Context, src: str, edge: str, dst: str) -> None:
    """Remove a typed edge."""
    st = _st(ctx)
    _emit(st.client.unlink(src, edge, dst), st)


@app.command()
def merge(ctx: typer.Context, keep: str, drop: str) -> None:
    """Merge duplicates: redirect edges, alias the dropped title, archive the dropped node."""
    st = _st(ctx)
    _emit(st.client.merge(keep, drop), st)


@app.command()
def check(ctx: typer.Context, project: str | None = typer.Option(None, "--project", "-p")) -> None:
    """Run integrity checks over a project."""
    st = _st(ctx)
    _emit(st.client.check(st.project(project)), st)


@app.command()
def changes(
    ctx: typer.Context,
    since: int | None = typer.Option(None, help="Cursor from a previous call"),
    limit: int = 100,
    project: str | None = typer.Option(None, "--project", "-p"),
) -> None:
    """Append-only change log."""
    st = _st(ctx)
    _emit(st.client.changes(st.project(project), since, limit), st)


@app.command()
def recipe(
    ctx: typer.Context,
    name: str = typer.Argument(None),
    args: list[str] | None = typer.Argument(None, help="KEY=VALUE"),
) -> None:
    """Run a context recipe (no name lists them). project_id defaults to FLORQUE_PROJECT."""
    st = _st(ctx)
    if not name:
        _emit(st.client.recipes(), st)
    a = _pairs(args)
    if st.cfg.project and "project_id" not in a and name in ("project_overview", "hygiene"):
        a["project_id"] = st.cfg.project
    _emit(st.client.recipe(name, a), st)


@app.command()
def brief(ctx: typer.Context, task_id: str) -> None:
    """Alias for recipe start_task_brief."""
    st = _st(ctx)
    _emit(st.client.recipe("start_task_brief", {"task_id": task_id}), st)


@app.command()
def sync(ctx: typer.Context) -> None:
    """Regenerate the local card from the server's ontology version (for FLORQUE_PROJECT)."""
    st = _st(ctx)
    env = st.client.describe(st.cfg.project)
    if env.get("ok"):
        d = env["data"]
        out_dir = st.state_file.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "card.md").write_text(d["card"])
        st.state_file.write_text(
            json.dumps(
                {"ontology_version": d["ontology_version"], "mixins_version": d["mixins_version"]}
            )
        )
        env = {
            **env,
            "data": {"card": str(out_dir / "card.md"), "ontology_version": d["ontology_version"]},
        }
    _emit(env, st)


# ---------------------------------------------------------------- hub commands


@hub_app.command("ingest")
def hub_ingest(
    ctx: typer.Context,
    json_: str = typer.Option("-", "--json", help='Observation envelope JSON, or "-" for stdin'),
) -> None:
    """Push one observation envelope."""
    st = _st(ctx)
    _emit(st.client.hub_ingest(_json_arg(json_)), st)


@hub_app.command("evaluate")
def hub_evaluate(
    ctx: typer.Context,
    node_id: str | None = typer.Option(None, "--node"),
    project: str | None = typer.Option(None, "--project", "-p"),
) -> None:
    """Evaluate one expectation, or all open ones."""
    st = _st(ctx)
    _emit(st.client.hub_evaluate(node_id, project or st.cfg.project), st)


@hub_app.command("reconcile")
def hub_reconcile(ctx: typer.Context) -> None:
    """Report unregistered codes, unused sensors and stale bindings (flags, never deletes)."""
    st = _st(ctx)
    _emit(st.client.hub_reconcile(), st)


@source_app.command("add")
def source_add(
    ctx: typer.Context,
    id: str,
    kind: str = typer.Option(..., help="sensor, webhook, slack, email, ci, ..."),
    name: str | None = None,
    config: str | None = typer.Option(None, help="JSON config"),
) -> None:
    st = _st(ctx)
    _emit(st.client.hub_source_add(id, kind, name, json.loads(config) if config else None), st)


@source_app.command("list")
def source_list(ctx: typer.Context) -> None:
    st = _st(ctx)
    _emit(st.client.hub_sources(), st)


@source_app.command("archive")
def source_archive(ctx: typer.Context, id: str) -> None:
    st = _st(ctx)
    _emit(st.client.hub_source_archive(id), st)


@sensor_app.command("add")
def sensor_add(
    ctx: typer.Context,
    series_code: str = typer.Option(..., "--series-code"),
    unit: str = typer.Option(...),
    aggregation: str = "last",
    source_id: str | None = typer.Option(None, "--source"),
    description: str | None = None,
    project: str | None = typer.Option(None, "--project", "-p"),
) -> None:
    st = _st(ctx)
    _emit(
        st.client.hub_sensor_add(
            series_code, st.project(project), unit, aggregation, source_id, description
        ),
        st,
    )


@sensor_app.command("list")
def sensor_list(
    ctx: typer.Context, project: str | None = typer.Option(None, "--project", "-p")
) -> None:
    st = _st(ctx)
    _emit(st.client.hub_sensors(project or st.cfg.project), st)


@sensor_app.command("archive")
def sensor_archive(ctx: typer.Context, id: str) -> None:
    st = _st(ctx)
    _emit(st.client.hub_sensor_archive(id), st)


@inbox_app.command("list")
def inbox_list(ctx: typer.Context, status: str = "open") -> None:
    st = _st(ctx)
    _emit(st.client.hub_inbox(status), st)


@inbox_app.command("resolve")
def inbox_resolve(
    ctx: typer.Context,
    id: str,
    action: str = typer.Option(..., help="attach or dismiss"),
    node_id: str | None = typer.Option(None, "--node"),
) -> None:
    st = _st(ctx)
    _emit(st.client.hub_inbox_resolve(id, action, node_id), st)


# ---------------------------------------------------------------- accounts


def _remember(st: State, env: dict[str, Any]) -> dict[str, Any]:
    """Store the token from a register/verify answer and hide it from the output."""
    if not env.get("ok"):
        return env
    d = dict(env["data"])
    path = save_credentials(
        st.cfg.api_url,
        {
            "token": d.pop("token"),
            "token_id": d.get("token_id"),
            "email": d.get("user", {}).get("email"),
            "tenant_id": d.get("tenant", {}).get("id"),
            "expires_at": d.get("expires_at"),
        },
    )
    d["credentials"] = str(path)
    d["api_url"] = st.cfg.api_url
    return {**env, "data": d}


@app.command()
def register(
    ctx: typer.Context,
    invite_code: str = typer.Option(..., "--invite", help="Code from the invite email"),
    email: str = typer.Option(..., help="The address the invite was sent to"),
    name: str = typer.Option("", help="Your name"),
    tenant_name: str | None = typer.Option(None, "--tenant-name", help="Workspace name"),
    label: str | None = typer.Option(None, help="Token label, e.g. laptop"),
    agent: bool = typer.Option(False, help="Mark the token as an agent's"),
) -> None:
    """Redeem an invite. Stores the token in the credentials file (pass --api-url for the server)."""
    st = _st(ctx)
    env = st.remote.auth_register(invite_code, email, name, tenant_name, label, agent)
    _emit(_remember(st, env), st)


@app.command()
def login(
    ctx: typer.Context,
    email: str = typer.Option(..., help="Your registered email"),
    code: str | None = typer.Option(None, help="The emailed code (prompted when omitted)"),
    tenant_id: str | None = typer.Option(None, "--tenant-id", help="Tenant, if you have several"),
    label: str | None = typer.Option(None, help="Token label, e.g. laptop"),
    agent: bool = typer.Option(False, help="Mark the token as an agent's"),
) -> None:
    """Log in on this machine with a one-time code sent by email."""
    st = _st(ctx)
    client = st.remote
    if code is None:
        env = client.auth_login(email)
        if not env.get("ok"):
            _emit(env, st)
        code = typer.prompt(f"Code sent to {email}").strip()
    _emit(_remember(st, client.auth_verify(email, code, label, tenant_id, agent)), st)


@app.command()
def logout(
    ctx: typer.Context,
    keep_token: bool = typer.Option(False, help="Forget locally but leave the token active"),
) -> None:
    """Revoke this machine's token and forget it."""
    st = _st(ctx)
    entry = read_credentials()["servers"].get(st.cfg.api_url.rstrip("/")) or {}
    revoked = None
    if entry.get("token") and entry.get("token_id") and not keep_token:
        env = HttpClient(st.cfg.api_url, entry["token"]).auth_token_revoke(entry["token_id"])
        revoked = entry["token_id"] if env.get("ok") else None
    removed = remove_credentials(st.cfg.api_url)
    _emit(
        {"ok": True, "data": {"api_url": st.cfg.api_url, "forgotten": removed, "revoked": revoked}}
    )


@app.command()
def whoami(ctx: typer.Context) -> None:
    """The user, tenant and token behind this machine's credentials."""
    st = _st(ctx)
    _emit(st.remote.auth_me(), st)


@app.command()
def invite(ctx: typer.Context, email: str) -> None:
    """Invite a colleague into your tenant (they get an email with a code)."""
    st = _st(ctx)
    _emit(st.remote.auth_invite(email), st)


@token_app.command("create")
def token_create(
    ctx: typer.Context,
    label: str | None = None,
    kind: str = typer.Option("user", help="user (agents, CI) or ingest (only /hub/observations)"),
    agent: bool = typer.Option(False, help="Mark a user token as an agent's"),
    days: int | None = typer.Option(None, help="Expiry in days"),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Limit the token to one project (server-enforced)"
    ),
) -> None:
    """A new token; shown once. Put it in FLORQUE_TOKEN where it is used."""
    st = _st(ctx)
    env = st.remote.auth_token_create(label, kind, agent, days, project)
    if env.get("ok"):
        typer.echo("The token is shown once; store it as FLORQUE_TOKEN.", err=True)
    _emit(env, st)


@token_app.command("list")
def token_list(ctx: typer.Context) -> None:
    st = _st(ctx)
    _emit(st.remote.auth_tokens(), st)


@token_app.command("revoke")
def token_revoke(ctx: typer.Context, token_id: str) -> None:
    st = _st(ctx)
    _emit(st.remote.auth_token_revoke(token_id), st)


# ---------------------------------------------------------------- project binding


def _fail(
    code: str, message: str, hint: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"code": code, "message": message, "hint": hint, "details": details or {}},
    }


@app.command()
def use(
    ctx: typer.Context,
    project_id: str | None = typer.Argument(None, help="Project id (omit to pick from a list)"),
    clear: bool = typer.Option(False, "--clear", help="Unbind this folder"),
) -> None:
    """Bind this folder (its .florque/config.yaml) to one project; agents here then use it."""
    st = _st(ctx)
    if clear:
        path = update_project_config({}, remove=("project",))
        _emit({"ok": True, "data": {"project": None, "config": str(path)}})
    if project_id is None:
        env = st.client.projects()
        if not env.get("ok"):
            _emit(env, st)
        projects = env["data"]["projects"]
        if not projects:
            _emit(
                _fail("NOT_FOUND", "No projects yet", "Create one: fwg create Project --title ...")
            )
        if not sys.stdin.isatty():
            _emit(
                _fail(
                    "ONTOLOGY_VIOLATION",
                    "No project id given",
                    "Pass one of the ids: fwg use PROJECT_ID",
                    {"projects": [{"id": p["id"], "title": p.get("title")} for p in projects]},
                )
            )
        for i, p in enumerate(projects, 1):
            typer.echo(f"{i:>3}. {p.get('title')}  ({p['id']})", err=True)
        choice = typer.prompt("Project number", type=int)
        if not 1 <= choice <= len(projects):
            raise typer.BadParameter(f"choose 1..{len(projects)}")
        project_id = projects[choice - 1]["id"]
    env = st.client.get(project_id, 0)
    if not env.get("ok"):
        _emit(env, st)
    node = env["data"]["node"]
    if node.get("class") not in (None, "Project") or node.get("parent_id"):
        _emit(_fail("SCOPE_VIOLATION", f"{project_id} is not a project", "Run fwg projects."))
    values: dict[str, Any] = {"project": project_id}
    if st.cfg.mode == "remote":
        values["api_url"] = st.cfg.api_url
    path = update_project_config(values)
    _emit(
        {
            "ok": True,
            "data": {
                "project": {"id": project_id, "title": node.get("title")},
                "config": str(path),
            },
            "ontology_version": env.get("ontology_version"),
        },
        st,
    )


def _status(st: State) -> dict[str, Any]:
    data: dict[str, Any] = {"mode": st.cfg.mode, "project": None}
    if st.cfg.mode == "remote":
        data["api_url"] = st.cfg.api_url
        me = st.remote.auth_me()
        if not me.get("ok"):
            return {**me, "data": data}
        data["user"] = me["data"]["user"].get("email")
        data["tenant"] = (me["data"].get("tenant") or {}).get("name")
        data["token_project"] = me["data"]["token"].get("project_id")
    if not st.cfg.project:
        return {
            **_fail(
                "NOT_FOUND",
                "No project bound to this folder",
                "Pick one with fwg use (fwg projects lists them), or pass -p.",
            ),
            "data": data,
        }
    env = st.client.get(st.cfg.project, 0)
    if not env.get("ok"):
        return {**env, "data": data}
    node = env["data"]["node"]
    data["project"] = {"id": node["id"], "title": node.get("title"), "status": node.get("status")}
    return {"ok": True, "data": data, "ontology_version": env.get("ontology_version")}


@app.command()
def status(ctx: typer.Context) -> None:
    """Where fwg points: mode, server, user and tenant, and the project bound to this folder."""
    st = _st(ctx)
    _emit(_status(st), st)


def _lines_overview(ov: dict[str, Any], limit: int = 8) -> list[str]:
    out: list[str] = []
    for o in ov.get("objectives", [])[:limit]:
        out.append(f"- Objective `{o['id']}` {o.get('title')} [{o.get('status')}]")
        for k in o.get("key_results", [])[:limit]:
            health = k.get("health") or k.get("outcome") or "n/a"
            out.append(f"  - KR `{k['id']}` {k.get('title')} [{k.get('status')}, {health}]")
    for i in ov.get("initiatives", [])[: limit * 2]:
        out.append(f"- Initiative `{i['id']}` {i.get('title')} [{i.get('status')}]")
    return out


@app.command("session-context", hidden=True)
def session_context(ctx: typer.Context) -> None:
    """Markdown for an agent session start (Claude Code SessionStart hook). Never fails."""
    st = _st(ctx)
    lines = ["## Florque Workgraph"]
    connect = (
        "Ask the user to run `fwg --api-url https://<server> login --email <address>` in a "
        "terminal. Do not ask for tokens in the chat."
    )
    try:
        st._client = client_from_config(st.cfg)
    except Exception as e:  # noqa: BLE001 - no login and no local engine/graph
        typer.echo("\n".join([*lines, f"fwg is not connected ({e}). {connect}"]))
        return
    try:
        env = _status(st)
        data = env.get("data") or {}
        err = env.get("error") or {}
        if err.get("code") in ("UNAUTHENTICATED", "UNAVAILABLE"):
            lines.append(f"fwg is not connected ({err.get('message')}). {connect}")
        elif data.get("project"):
            p = data["project"]
            lines.append(
                f"This folder is bound to project **{p['title']}** (`{p['id']}`). "
                "fwg commands use it by default; do not pass another -p unless the user asks."
            )
            if data.get("token_project"):
                lines.append("The token is limited to this project.")
            ov = st.client.recipe("project_overview", {"project_id": p["id"]})
            if ov.get("ok"):
                lines.extend(_lines_overview(ov["data"]))
            lines.append("For a task, run `fwg brief <task_id>` before starting.")
        elif err.get("code") == "NOT_FOUND" and not data.get("project"):
            env = st.client.projects()
            projects = env.get("data", {}).get("projects", []) if env.get("ok") else []
            lines.append(
                "No project is bound to this folder. Before any graph work, ask the user which "
                "project to use, then run `fwg use <project_id>` (it writes .florque/config.yaml)."
            )
            lines.extend(f"- `{p['id']}` {p.get('title')}" for p in projects[:20])
            if not projects:
                lines.append("There are no projects yet; /start-project creates one.")
        else:
            lines.append(f"fwg status: {err.get('code')}: {err.get('message')}")
    except Exception as e:  # noqa: BLE001 - a session start must never break
        lines.append(f"fwg could not read the workgraph ({e}).")
    typer.echo("\n".join(lines))


# ---------------------------------------------------------------- ontology


def _yaml_file(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text()


@ontology_app.command("show")
def ontology_show(
    ctx: typer.Context, project: str | None = typer.Option(None, "--project", "-p")
) -> None:
    """The effective ontology for a project (base plus active extensions)."""
    st = _st(ctx)
    _emit(st.client.describe(project or st.cfg.project), st)


@ontology_app.command("list")
def ontology_list(
    ctx: typer.Context,
    project: str | None = typer.Option(None, "--project", "-p"),
    include_retired: bool = False,
) -> None:
    """Extensions of your tenant (and of a project with --project)."""
    st = _st(ctx)
    _emit(st.client.ontology_extensions(project or st.cfg.project, include_retired), st)


@ontology_app.command("validate")
def ontology_validate(
    ctx: typer.Context,
    file: str = typer.Argument(..., help='Extension YAML file, or "-" for stdin'),
    project: str | None = typer.Option(None, "--project", "-p", help="Scope to one project"),
) -> None:
    """Check an extension without activating it (compile, contract, dry run)."""
    st = _st(ctx)
    _emit(st.client.ontology_validate(_yaml_file(file), project), st)


@ontology_app.command("add")
def ontology_add(
    ctx: typer.Context,
    file: str = typer.Argument(..., help='Extension YAML file, or "-" for stdin'),
    project: str | None = typer.Option(None, "--project", "-p", help="Scope to one project"),
) -> None:
    """Validate and activate an extension (tenant-wide unless --project)."""
    st = _st(ctx)
    _emit(st.client.ontology_add(_yaml_file(file), project), st)


@ontology_app.command("retire")
def ontology_retire(ctx: typer.Context, id: str) -> None:
    """Deactivate an extension (refused while nodes still use its classes)."""
    st = _st(ctx)
    _emit(st.client.ontology_retire(id), st)


if __name__ == "__main__":
    app()
