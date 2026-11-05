"""fwg: one command for agents and humans, local or remote (spec 8). JSON in, JSON out."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer
from florque_client import Client, Config, client_from_config, load_config

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
app.add_typer(hub_app, name="hub")
hub_app.add_typer(source_app, name="source")
hub_app.add_typer(sensor_app, name="sensor")
hub_app.add_typer(inbox_app, name="inbox")


class State:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._client: Client | None = None

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
    def state_file(self) -> Path:
        return Path(self.cfg.config_dir or ".florque") / "state.json"


def _st(ctx: typer.Context) -> State:
    return ctx.obj  # type: ignore[no-any-return]


def _emit(env: dict[str, Any], st: State | None = None) -> None:
    typer.echo(json.dumps(env, indent=2, default=str))
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
def describe(ctx: typer.Context) -> None:
    """Ontology version, classes and the generated card."""
    st = _st(ctx)
    _emit(st.client.describe(), st)


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
    """Regenerate the local card from the server's ontology version."""
    st = _st(ctx)
    env = st.client.describe()
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


if __name__ == "__main__":
    app()
