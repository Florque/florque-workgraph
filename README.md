# Florque Workgraph

The backbone of the Florque project-management copilot: a typed project graph (goals, work, documents, evidence) validated against a LinkML ontology, with a signal hub that evaluates key results from external metrics. See [the system specification](Florque%20Workgraph%20%E2%80%94%20System%20Specification.md).

## Packages (uv workspace)

| Package | Role |
| --- | --- |
| `packages/graph-core` | Generic engine: ontology loader, validation pipeline, CRUD, Neo4j and memory graph stores, generators |
| `packages/workgraph-domain` | Workgraph v0.2 ontology + mixins (LinkML), policies, recipes, generated card/constraints/integrity checks |
| `packages/signal-hub` | Registry, observation ledger, Lane 1 routing, expectation evaluator, inbox, jobs (SQLite store) |
| `packages/client` | One client interface with HTTP (thin: httpx only) and in-process implementations; `FlorqueApp` wiring, the per-tenant ontology-extension registry (`[local]` extra) |
| `packages/service` | FastAPI service under `/v1`: invite registration, email login (Resend), tokens, rate limits, scheduler, metrics |
| `packages/cli` | `fwg`: JSON in, JSON out, local or remote. `uv tool install florque-cli` is remote-only; `florque-cli[local]` adds the engine |

Dependencies point downward only, which `lint-imports` enforces. The hub never imports workgraph-domain; it works on the `Expectation` and `Observation` mixin roles. The thin client modules and the CLI never import the engine.

Other folders: `plugin/` (the Claude Code plugin: skills and slash commands; `.claude-plugin/marketplace.json` at the root) and `deploy/` (the one-server production stack, see [deploy/README.md](deploy/README.md)).

## Two ways to run

```
local mode:   fwg ──(in-process)──► graph-core + hub ──► graph store (file or Neo4j) + .florque/hub.sqlite
remote mode:  fwg ──(HTTP, token)──► florque-service ──► graph-core + hub ──► Neo4j + hub.sqlite
              curl / other clients ─┘
```

Both modes run the same operations and return the same JSON envelope, so anything you can do with `fwg` locally you can do against the service, and vice versa.

| | Local mode | Remote mode (service) |
| --- | --- | --- |
| Users | one, trusted by convention (acts as admin) | tenants with invited users; each tenant sees only its own projects |
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
| Account (remote) | `register --invite CODE --email E`, `login --email E`, `logout`, `whoami`, `invite EMAIL`, `token create/list/revoke` |
| Projects, ontology | `projects`, `use [P] [--clear]`, `status`, `describe [-p P]`, `ontology show/list [-p P]`, `ontology validate/add FILE.yaml [-p P]`, `ontology retire ID` |

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
| `ontology_db` | `FLORQUE_ONTOLOGY_DB` | | `.florque/ontologies.sqlite` (extensions) |
| `actor_id` | `FLORQUE_ACTOR` | | `$USER` (local mode) |
| `agent` | `FLORQUE_AGENT` | | `false`; marks the actor as an agent: its new nodes start as `proposed` and it cannot accept proposals, whatever its role (in remote mode the token's agent flag decides) |
| `neo4j_uri`, `neo4j_user`, `neo4j_database` | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_DATABASE` | | `bolt://127.0.0.1:7687`, `neo4j` |
| (env only) | `NEO4J_PASSWORD`, `FLORQUE_TOKEN` | | none |

Secrets (`FLORQUE_TOKEN`, `NEO4J_PASSWORD`) never come from config files. The one exception for tokens is the credentials file that `fwg register` / `fwg login` write outside the repository: `~/.config/florque/credentials.json` (mode 0600, or `FLORQUE_CREDENTIALS`), keyed by server URL. When it exists and no mode is configured, `fwg` uses remote mode against its default server; `FLORQUE_TOKEN` still wins. A project-level config might look like:

```yaml
# .florque/config.yaml
mode: remote
api_url: https://workgraph.example.com
project: project_769f98195a7646c4
```

### One project per folder (agents)

`fwg use <project id>` binds the current folder: it writes `project:` (and, in remote mode, `api_url:`) into the nearest `.florque/config.yaml`. That file holds no secrets, so commit it, and every agent session in the repository, including subfolders, works on that project. `fwg use` with no id lists the projects to pick from, `fwg status` shows the binding, and `fwg use --clear` removes it.

The binding is a default, not a fence: an agent could still pass another `-p`. To enforce one project on the server, give the agent a project-limited token, `fwg token create --label repo-bot --agent -p <project id>`, as `FLORQUE_TOKEN`. That token sees only that project, cannot create projects or invite people, and the tokens it creates are limited to the same project.

The `memory` store forgets everything when the process exits, so from the CLI it is only useful for a throwaway look; use `file` for a persistent single-user graph. Do not point a local `fwg` and a running service at the same `graph.json`: the file store has no cross-process locking.

## Service (`florque-service`)

The service hosts the same graph-core + hub behind an HTTP API under `/v1`, authenticates callers with bearer tokens and runs the hub scheduler. It reads the same configuration as the CLI (store, Neo4j, hub database), plus:

| Environment | Default | Meaning |
| --- | --- | --- |
| `FLORQUE_SERVICE_DB` | `service.sqlite` next to the hub database | tenants, users, invites, tokens |
| `FLORQUE_SCHEDULER` | `on` | `off` disables background evaluation/reconciliation |

### 1. Accounts: invites, login, tokens

Registration is invite-only and email-based; users never set passwords.

```bash
# operator, on the server host (same FLORQUE_HUB_DB / FLORQUE_SERVICE_DB as the server)
florque-service invite create --email alice@example.com            # new tenant; emails the code
florque-service invite create --email bob@example.com --tenant-id tenant_...   # join a tenant
florque-service invite create --email carol@example.com --no-email  # only print the code
florque-service invite list; florque-service tenant list; florque-service user list

# the invitee
fwg --api-url https://wg.example.com register --invite XXXX-XXXX-XXXX --email alice@example.com --tenant-name Acme
fwg whoami
fwg --api-url https://wg.example.com login --email alice@example.com   # another machine: prompts for the emailed code
fwg invite bob@example.com                       # members invite colleagues into their tenant
fwg token create --label ci --agent              # a token for an agent or CI (FLORQUE_TOKEN)
fwg token create --kind ingest --label metrics   # may only push observations
fwg token list && fwg token revoke <id> && fwg logout
```

Tokens look like `fwg_<id>_<secret>`. The secret is shown once and only its SHA-256 hash is stored. User tokens last 90 days, ingest tokens 365. Tokens from before 0.2 (argon2) are not migrated, so issue new ones.

Closed beta: there is **no RBAC** yet. A user token, including one marked `--agent`, is admin of every project in its tenant (agent writes still start as `proposed`). The roles below apply to operator tokens, which carry an explicit role map:

```bash
florque-service token issue --actor ci-bot --role '*=contributor' --agent --label "release agent" --days 30
florque-service token list
florque-service token revoke b3e0b313
```

`--role PROJECT=ROLE` is repeatable and `*` means every project. Any token or actor marked as an agent creates `proposed` nodes and cannot accept proposals, whatever its role. Roles:

| Role | Can |
| --- | --- |
| `admin` | everything: human-owned fields, accepting proposals (`proposed` → `active`), hub registry (sources, sensors, bindings), reconcile |
| `contributor` | create and edit human-owned fields |
| `viewer` | read only |
| `hub` | create observation Signals and write evaluator-owned fields (`outcome`, `health`, `last_*`); nothing else |

Email goes through [Resend](https://resend.com) when `RESEND_API_KEY` and `FLORQUE_EMAIL_FROM` are set. Without them the service logs each message instead (development), and with `FLORQUE_ENV=production` it refuses to start.

| Environment | Default | Meaning |
| --- | --- | --- |
| `FLORQUE_PUBLIC_URL` | `http://127.0.0.1:8000` | server URL used in emails |
| `FLORQUE_CLI_INSTALL` | `uv tool install florque-cli` | install line used in invite emails |
| `FLORQUE_MIN_CLIENT` | `0.2.0` | older CLIs print an upgrade warning |
| `FLORQUE_RATE_LIMIT`, `FLORQUE_AUTH_RATE_LIMIT` | `600`, `20` | requests per minute per token (or IP), and per IP on `/v1/auth` |
| `FLORQUE_FORWARDED_ALLOW_IPS` | `127.0.0.1` | proxies trusted for `X-Forwarded-For` |
| `FLORQUE_LOG_LEVEL` | `INFO` | log level |

### Tenant ontology extensions

A tenant (or a single project) can add classes, slots and enum values to the base ontology. The changes are additive only, as described in spec section 4.9:

```bash
fwg ontology validate experiments.yaml           # compile + mixin contract + dry run, nothing stored
fwg ontology add experiments.yaml                # tenant-wide; -p PROJECT for one project
fwg ontology show -p $FLORQUE_PROJECT            # effective card; version e.g. 0.2.0+experiments@1.0.0
fwg ontology list && fwg ontology retire <id>    # retire is refused while nodes still use it
```

### 2. Run the server

```bash
export FLORQUE_STORE=neo4j NEO4J_PASSWORD=change-me     # or FLORQUE_STORE=file for a single-process demo
florque-service serve --host 127.0.0.1 --port 8000
```

- Interactive API docs (OpenAPI): <http://127.0.0.1:8000/docs>
- Health: `GET /healthz` (process up), `GET /readyz` (graph store reachable and the ontology version)
- Prometheus metrics: `GET /metrics` (request latency, validation failures by error code, hub lag, expectations by outcome)
- Logs are JSON lines on stdout with a `request_id` and the `idempotency_key`.

With Docker Compose (Neo4j plus the service image built from the `Dockerfile`):

```bash
export NEO4J_PASSWORD=change-me
docker compose up -d neo4j
docker compose --profile service up -d --build          # http://127.0.0.1:8000
docker compose --profile service exec service \
  florque-service invite create --email you@example.com --no-email
```

Inside Compose the SQLite databases live on the `hub_data` volume (`/data`). Both containers bind to `127.0.0.1` only. For production (TLS, backups, releases) use [deploy/](deploy/README.md).

### 3. Use the CLI against the service (remote mode)

```bash
fwg --api-url http://127.0.0.1:8000 register --invite <code> --email you@example.com
# (or: export FLORQUE_MODE=remote FLORQUE_API_URL=... FLORQUE_TOKEN=fwg_...)
fwg projects
fwg create Project --title "Checkout revamp"
export FLORQUE_PROJECT=<project id>
fwg recipe project_overview
fwg hub inbox list
```

The commands and output are the same as in local mode; permissions now come from the token. For example, a viewer token gets `{"ok": false, "error": {"code": "FORBIDDEN", ...}}` on any write.

### 4. Call the HTTP API directly

Every request except `/v1/ontology`, `POST /v1/auth/register|login|verify`, `/healthz`, `/readyz` and `/metrics` needs `Authorization: Bearer <token>`. Ingest tokens are accepted only on `POST /v1/hub/observations`. Responses use the same envelope as the CLI.

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
| Auth | `POST /v1/auth/register`, `POST /v1/auth/login`, `POST /v1/auth/verify`, `GET /v1/auth/me`, `GET/POST /v1/auth/tokens`, `DELETE /v1/auth/tokens/{id}`, `POST /v1/auth/invites` |
| Ontology | `GET /v1/ontology?project_id=` (public without a token: the base), `GET/POST /v1/ontology/extensions`, `POST /v1/ontology/extensions:validate`, `DELETE /v1/ontology/extensions/{id}` |
| Projects | `GET /v1/projects`, `POST /v1/projects` |
| Nodes | `POST /v1/nodes`, `POST /v1/nodes:list`, `GET /v1/nodes/{id}?depth=`, `PATCH /v1/nodes/{id}`, `POST /v1/nodes/{id}:archive`, `POST /v1/nodes/{id}:move`, `GET /v1/search?project_id=&q=` |
| Edges | `POST /v1/edges`, `POST /v1/edges:unlink`, `POST /v1/merge` |
| Context | `GET /v1/recipes`, `GET /v1/recipes/{name}?...`, `POST /v1/check`, `GET /v1/changes?project_id=&since=` |
| Hub | `POST /v1/hub/observations`, `GET/POST /v1/hub/sources`, `DELETE /v1/hub/sources/{id}`, `GET/POST /v1/hub/sensors`, `DELETE /v1/hub/sensors/{id}`, `GET/POST /v1/hub/bindings`, `DELETE /v1/hub/bindings/{kind}/{id}`, `GET /v1/hub/inbox`, `POST /v1/hub/inbox/{id}:resolve`, `POST /v1/hub/evaluate`, `POST /v1/hub/reconcile` |

Error codes map to HTTP statuses: `UNAUTHENTICATED` 401; `FORBIDDEN`, `OWNERSHIP` 403; `NOT_FOUND` 404; `VERSION_CONFLICT`, `DUPLICATE_EXACT`, `DUPLICATE_SIMILAR`, `MERGE_CONFLICT` 409; `ONTOLOGY_VIOLATION`, `PARENT_RULE`, `REQUIRED_EDGE`, `SCOPE_VIOLATION` 422; `RATE_LIMITED` 429 (with `Retry-After`); a body over 1 MiB 413.

### Background jobs

When the scheduler is on, the service enqueues an evaluation of all open expectations every 15 minutes and a reconciliation at 03:00 UTC (it flags unregistered series codes, unused sensors and bindings to archived nodes; it never deletes). A worker claims queued jobs every 10 seconds. Ingesting an observation also evaluates the affected key results immediately.

## Claude Code plugin

`plugin/` holds two skills: `graph-memory` (setup and the agent protocol) and `workgraph` (the domain guide plus the ontology card, generated by `fwg-gen`). It also has the commands `/project`, `/start-project`, `/brief`, `/debrief`, `/ingest` and `/status`. A `SessionStart` hook runs `fwg session-context`, so each session starts knowing the bound project and its open objectives, key results and initiatives. In an unbound folder the agent is told to ask you which project to use and run `fwg use`; when `fwg` is not logged in, it asks you to run `fwg login`. Install it from this repository's marketplace:

```
/plugin marketplace add Florque/florque-workgraph
/plugin install florque-workgraph@florque
```

## Development

```bash
uv run pytest                 # Neo4j variants run when NEO4J_URI/NEO4J_PASSWORD are set or Docker is available
uv run ruff check packages tests && uv run ruff format --check packages tests
uv run mypy && uv run lint-imports
uv run fwg-gen                # regenerate generated/ and plugin/skills/workgraph/SKILL.md after ontology changes (CI runs --check)
```
