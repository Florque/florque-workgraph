# Florque Workgraph

The backbone of the Florque project-management copilot: a typed project graph (goals, work, documents, evidence) validated against a LinkML ontology, with a signal hub that evaluates key results from external metrics. See [the system specification](Florque%20Workgraph%20%E2%80%94%20System%20Specification.md).

## Packages (uv workspace)

| Package | Role |
| --- | --- |
| `packages/graph-core` | Generic engine: ontology loader, validation pipeline, CRUD, Neo4j and memory graph stores, generators |
| `packages/workgraph-domain` | Workgraph v0.2 ontology + mixins (LinkML), policies, recipes, generated card/constraints/integrity checks |
| `packages/signal-hub` | Registry, observation ledger, Lane 1 routing, expectation evaluator, inbox, jobs (SQLite store) |
| `packages/client` | `FlorqueApp` wiring plus one client interface with in-process and HTTP implementations |
| `packages/service` | FastAPI service under `/v1`, bearer tokens, scheduler, metrics |
| `packages/cli` | `fwg`: JSON in, JSON out, local or remote |

Dependencies point downward only, which `lint-imports` enforces. The hub never imports workgraph-domain; it works on the `Expectation` and `Observation` mixin roles.

## Two ways to run

```
local mode:   fwg ──(in-process)──► graph-core + hub ──► graph store (file or Neo4j) + .florque/hub.sqlite
remote mode:  fwg ──(HTTP, token)──► florque-service ──► graph-core + hub ──► Neo4j + hub.sqlite
              curl / other clients ─┘
```

Both modes run the same operations and return the same JSON envelope, so anything you can do with `fwg` locally you can do against the service, and vice versa.

| | Local mode | Remote mode (service) |
| --- | --- | --- |
| Users | one, trusted by convention (acts as admin) | many, each with a token and per-project roles |
| Graph store | `file` (`.florque/graph.json`) or Neo4j | Neo4j (or `file` for a single-process demo) |
| Hub evaluation | on ingest, or `fwg hub evaluate` | on ingest, plus a scheduler every 15 min |
| Needs | nothing but `uv sync` | a running `florque-service` |

`uv sync` installs three commands into `.venv/bin`: `fwg` (CLI), `florque-service` (API server and token admin) and `fwg-gen` (artifact generator). Run them with `uv run <cmd>`, or activate the venv (`source .venv/bin/activate`).

## CLI (`fwg`)

### Quickstart (local mode)

```bash
uv sync
export FLORQUE_STORE=file            # file-backed graph; or run Neo4j (below) and use the default "neo4j"
fwg create Project --title "Checkout revamp"            # -> data.node.id
export FLORQUE_PROJECT=<project id>
fwg create Goal --kind objective --title "Faster checkout" --parent $FLORQUE_PROJECT
fwg hub source add metrics --kind sensor
fwg hub sensor add --series-code checkout_p95_ms --unit ms --source metrics
fwg create Goal --kind key_result --title "p95 under 800ms" --parent <objective id> \
  --prop series_code=checkout_p95_ms --prop 'comparator="<="' --prop target_value=800 --prop unit=ms \
  --prop reducer=last --prop 'window_start="2026-11-01"' --prop 'window_end="2026-11-30"' --prop status=active
fwg create WorkItem --kind initiative --title "Payment API rewrite" --parent $FLORQUE_PROJECT --edge serves:<kr id>
echo '{"source_id":"metrics","external_id":"m1","subject_code":"checkout_p95_ms","type":"metric","value":950,"observed_at":"2026-11-05T10:00:00Z"}' | fwg hub ingest
fwg recipe project_overview
fwg check
```

With Neo4j instead of the file store:

```bash
export NEO4J_PASSWORD=change-me
docker compose up -d neo4j            # bolt://127.0.0.1:7687
unset FLORQUE_STORE                   # default store is neo4j
fwg describe
```

### Commands

| Group | Commands |
| --- | --- |
| Read | `describe`, `get <id> [--depth 0-3]`, `search <query>`, `list [--cls C] [-f FIELD=VALUE]`, `changes [--since N]` |
| Write | `create <Class> --title --kind --parent --prop F=V --edge EDGE:ID`, `update <id> --set F=V`, `archive <id> [--cascade]`, `move <id> <parent>`, `link <src> <edge> <dst>`, `unlink`, `merge <keep> <drop>` |
| Context | `recipe [name] [key=value ...]` (no name lists recipes), `brief <task id>`, `check`, `sync` |
| Hub | `hub ingest`, `hub evaluate [--node ID]`, `hub reconcile`, `hub source add/list/archive`, `hub sensor add/list/archive`, `hub inbox list/resolve` |

Every command has `--help`. Notes:

- **Output** is always the JSON envelope `{"ok": true, "data": ...}` or `{"ok": false, "error": {"code", "message", "hint", "details"}}`, plus `ontology_version`. The exit code is 1 when `ok` is false, so scripts can branch on it; errors carry a `hint` with the fix.
- **Values** in `--prop F=V` are parsed as JSON when possible (`target_value=800` is a number), so quote strings that look like something else: `--prop 'comparator="<="'`.
- **Full requests** can be passed as JSON with `--json '{...}'` or `--json -` (stdin), e.g. for `create` and `hub ingest`.
- **Duplicates:** `create` refuses near-duplicates with `DUPLICATE_SIMILAR` and lists the candidates; pass `--confirm-new` if it really is new. `--idempotency-key K` makes a retry return the first result instead of creating twice.
- **`sync`** writes `.florque/card.md` (the ontology card for agents) and `.florque/state.json`. When a response's `ontology_version` differs from the synced one, the CLI prints a hint to run `fwg sync`.

### Configuration

Precedence: flags > environment > `.florque/config.yaml` (searched upward from the current directory) > `~/.config/florque/config.yaml`. Relative paths resolve against the folder containing `.florque/`.

| Setting (config key) | Environment | Flag | Default |
| --- | --- | --- | --- |
| `mode` | `FLORQUE_MODE` | `--mode` | `local` (or `remote`) |
| `api_url` | `FLORQUE_API_URL` | `--api-url` | `http://127.0.0.1:8000` |
| `project` | `FLORQUE_PROJECT` | `--project` / `-p` | none |
| `store` | `FLORQUE_STORE` | `--store` | `neo4j` (or `file`, `memory`) |
| `data_file` | `FLORQUE_DATA_FILE` | | `.florque/graph.json` |
| `hub_db` | `FLORQUE_HUB_DB` | | `.florque/hub.sqlite` |
| `actor_id` | `FLORQUE_ACTOR` | | `$USER` (local mode) |
| `agent` | `FLORQUE_AGENT` | | `false`; marks the actor as an agent (the "agent writes start as `proposed`" rule applies to agent *contributors*, i.e. `--agent` tokens in remote mode; local mode always acts as admin) |
| `neo4j_uri`, `neo4j_user`, `neo4j_database` | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_DATABASE` | | `bolt://127.0.0.1:7687`, `neo4j` |
| (env only) | `NEO4J_PASSWORD`, `FLORQUE_TOKEN` | | none |

Secrets (`FLORQUE_TOKEN`, `NEO4J_PASSWORD`) are read from the environment only; config files ignore them. A project-level config might look like:

```yaml
# .florque/config.yaml
mode: remote
api_url: https://workgraph.example.com
project: project_769f98195a7646c4
```

The `memory` store forgets everything when the process exits, so from the CLI it is only useful for a throwaway look; use `file` for a persistent single-user graph. Do not point a local `fwg` and a running service at the same `graph.json`: the file store has no cross-process locking.

## Service (`florque-service`)

The service hosts the same graph-core + hub behind an HTTP API under `/v1`, authenticates callers with bearer tokens and runs the hub scheduler. It reads the same configuration as the CLI (store, Neo4j, hub database), plus:

| Environment | Default | Meaning |
| --- | --- | --- |
| `FLORQUE_SERVICE_DB` | `service.sqlite` next to the hub database | token store |
| `FLORQUE_SCHEDULER` | `on` | `off` disables background evaluation/reconciliation |

### 1. Issue a token

Tokens are issued on the server host, against the same service database the server uses (run from the same directory or with the same `FLORQUE_HUB_DB` / `FLORQUE_SERVICE_DB`):

```bash
florque-service token issue --actor alice --role '*=admin' --create-projects
# {"id": "b3e0b313", "token": "fwg_b3e0b313_...", "actor_id": "alice", "roles": {"*": "admin"}}
florque-service token issue --actor bob --role project_769f...=contributor --role project_12ab...=viewer
florque-service token issue --actor ci-bot --role '*=contributor' --agent --label "release agent"
florque-service token list
florque-service token revoke b3e0b313
```

The secret is printed once and only its argon2 hash is stored. `--role PROJECT=ROLE` is repeatable and `*` means every project. Roles:

| Role | Can |
| --- | --- |
| `admin` | everything: human-owned fields, accepting proposals (`proposed` → `active`), hub registry (sources, sensors, bindings), reconcile |
| `contributor` | create and edit human-owned fields; with `--agent` its new nodes start as `proposed` |
| `viewer` | read only |
| `hub` | create observation Signals and write evaluator-owned fields (`outcome`, `health`, `last_*`); nothing else |

`--create-projects` allows creating new Projects. Roles come only from the token, so a creator without a `*` role has no access to the project it just created: issue it a new token with `--role <new project id>=admin` (or use `*=admin` for operators).

### 2. Run the server

```bash
export FLORQUE_STORE=neo4j NEO4J_PASSWORD=change-me     # or FLORQUE_STORE=file for a single-process demo
florque-service serve --host 127.0.0.1 --port 8000
```

- Interactive API docs (OpenAPI): <http://127.0.0.1:8000/docs>
- Health: `GET /healthz` (process up), `GET /readyz` (graph store reachable, ontology and mixins versions)
- Prometheus metrics: `GET /metrics` (request latency, validation failures by error code, hub lag, expectations by outcome)
- Logs are JSON lines on stdout with a `request_id` and the `idempotency_key`.

With Docker Compose (Neo4j plus the service image built from the `Dockerfile`):

```bash
export NEO4J_PASSWORD=change-me
docker compose up -d neo4j
docker compose --profile service up -d --build          # http://127.0.0.1:8000
docker compose --profile service exec service \
  florque-service token issue --actor alice --role '*=admin' --create-projects
```

Inside Compose the hub and token databases live on the `hub_data` volume (`/data`). Both containers bind to `127.0.0.1` only; put a TLS-terminating proxy in front before exposing the service.

### 3. Use the CLI against the service (remote mode)

```bash
export FLORQUE_MODE=remote FLORQUE_API_URL=http://127.0.0.1:8000 FLORQUE_TOKEN=fwg_...
fwg describe
fwg create Project --title "Checkout revamp"
export FLORQUE_PROJECT=<project id>
fwg recipe project_overview
fwg hub inbox list
```

The commands and output are the same as in local mode; permissions now come from the token. For example, a viewer token gets `{"ok": false, "error": {"code": "FORBIDDEN", ...}}` on any write.

### 4. Call the HTTP API directly

Every request except `/v1/ontology`, `/healthz`, `/readyz` and `/metrics` needs `Authorization: Bearer <token>`. Responses use the same envelope as the CLI.

```bash
TOKEN=fwg_...
API=http://127.0.0.1:8000

# create a node; Idempotency-Key makes retries safe (same key -> same node)
curl -s -X POST $API/v1/nodes -H "Authorization: Bearer $TOKEN" -H "Idempotency-Key: obj-1" \
  -H 'content-type: application/json' \
  -d '{"cls": "Goal", "parent_id": "<project id>", "props": {"kind": "objective", "title": "Faster checkout"}}'

# patch with optimistic concurrency
curl -s -X PATCH $API/v1/nodes/<id> -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"patch": {"summary": "Cut p95 latency"}, "if_version": 1}'

# push an observation to the hub (202 Accepted)
curl -s -X POST $API/v1/hub/observations -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"source_id": "metrics", "external_id": "m1", "subject_code": "checkout_p95_ms", "type": "metric", "value": 750, "observed_at": "2026-11-05T10:00:00Z"}'

# run a recipe
curl -s "$API/v1/recipes/kr_progress?kr_id=<kr id>" -H "Authorization: Bearer $TOKEN"
```

| Area | Endpoints |
| --- | --- |
| Ontology | `GET /v1/ontology` (public) |
| Nodes | `POST /v1/projects`, `POST /v1/nodes`, `POST /v1/nodes:list`, `GET /v1/nodes/{id}?depth=`, `PATCH /v1/nodes/{id}`, `POST /v1/nodes/{id}:archive`, `POST /v1/nodes/{id}:move`, `GET /v1/search?project_id=&q=` |
| Edges | `POST /v1/edges`, `POST /v1/edges:unlink`, `POST /v1/merge` |
| Context | `GET /v1/recipes`, `GET /v1/recipes/{name}?...`, `POST /v1/check`, `GET /v1/changes?project_id=&since=` |
| Hub | `POST /v1/hub/observations`, `GET/POST /v1/hub/sources`, `DELETE /v1/hub/sources/{id}`, `GET/POST /v1/hub/sensors`, `DELETE /v1/hub/sensors/{id}`, `GET/POST /v1/hub/bindings`, `DELETE /v1/hub/bindings/{kind}/{id}`, `GET /v1/hub/inbox`, `POST /v1/hub/inbox/{id}:resolve`, `POST /v1/hub/evaluate`, `POST /v1/hub/reconcile` |

Error codes map to HTTP statuses: `UNAUTHENTICATED` 401; `FORBIDDEN`, `OWNERSHIP` 403; `NOT_FOUND` 404; `VERSION_CONFLICT`, `DUPLICATE_EXACT`, `DUPLICATE_SIMILAR`, `MERGE_CONFLICT` 409; `ONTOLOGY_VIOLATION`, `PARENT_RULE`, `REQUIRED_EDGE`, `SCOPE_VIOLATION` 422.

### Background jobs

When the scheduler is on, the service enqueues an evaluation of all open expectations every 15 minutes and a reconciliation at 03:00 UTC (it flags unregistered series codes, unused sensors and bindings to archived nodes; it never deletes). A worker claims queued jobs every 10 seconds. Ingesting an observation also evaluates the affected key results immediately.

## Development

```bash
uv run pytest                 # Neo4j variants run when NEO4J_URI/NEO4J_PASSWORD are set or Docker is available
uv run ruff check packages tests && uv run ruff format --check packages tests
uv run mypy && uv run lint-imports
uv run fwg-gen                # regenerate packages/workgraph-domain/.../generated after ontology changes (CI runs --check)
```
