# Florque Workgraph — System Specification

Draft v0.1 · 4 November 2026

## 1. Purpose and scope

Florque Workgraph is the backbone of the Florque project-management copilot. It stores a project's goals, work, documents and evidence as a typed graph, lets agents read context from it and write to it through a validated API, and links measured results back to the goals they prove.

It ships two ways from one codebase: a Claude Code plugin that works against a local or remote instance, and a server application exposing an HTTP API.

**Goals**

1. Every node reaches a Project root. No orphans. The one exception is Actor, which is cross-project and must have at least one member\_of edge.
2. Every write is validated against the ontology, whoever makes it.
3. The engine is domain-agnostic. Domain knowledge lives in an injected ontology.
4. Measurement and outcome evaluation are deterministic code, not LLM judgment.
5. The agent-facing contract is identical in local and remote mode.

**Non-goals (v0.1):** a UI; file storage (the graph keeps links to a bucket only); decision records and edit history as graph nodes; capacity planning (optional module); real-time collaboration; an MCP server.

## 2. florque-workgraph-domain (the work-graph domain)

Purpose: the work-graph domain, as data plus a few functions.

```
packages/workgraph-domain/
  ontology/workgraph.linkml.yaml          v0.2 (section 4)
  ontology/mixins.linkml.yaml             Expectation, Observation
  ontology/modules/impact.fragment.yaml   optional
  generated/                              card.md, constraints.cypher, integrity_checks.cypher
  recipes/                                context bundles
  policies.py                             merge, dedupe_scope, role to capability map
  SKILL.md                                domain skill for the plugin
```

Generated artifacts come from the ontology in a build step and are committed. CI fails if they drift.

Recipes return one bundle each, so agents make few calls:

| Recipe | Answers |
| --- | --- |
| project\_overview | Objectives, KRs with outcome and health, active initiatives |
| why(node) | Ancestor chain and served goals up to the objective |
| kr\_progress(kr) | Baseline, latest value, trend, progress, staleness |
| start\_task\_brief(task) | Goal chain, related Documents, feedback, past debrief lessons, owner |
| hygiene | Initiatives serving nothing, KRs without series or target, stale proposed nodes |
| blast\_radius(task) | Everything relying on the components a task touches (impact module) |
| recurring\_issues(scope) | Debrief tags and incidents grouped by area, epic or owner |

Debriefs: a debrief Signal about a task triggers one analysis run. Code computes cycle time, time blocked and estimate error. The model tags the text against controlled vocabularies (outcome, blocker\_types). Results are stored as flat fields on the debrief. Aggregation is Cypher over those fields, and a weekly job writes a proposed insight Signal that cites its evidence and requires a minimum sample.

## 3. Architecture

```
        Claude Code plugin                 other clients
        skills · commands · hooks              (HTTP)
                 │                                │
              fwg CLI ───────────────────────────┤
         local │        │ remote                  │
               ▼        ▼                         ▼
        in-process   florque-service  (HTTP API, auth, workers)
        client            │
                          ├── florque-signal-hub ──► hub store (SQLite → SQL)
                          └── florque-workgraph-domain (ontology + recipes)
                                     │ injected
                              florque-graph-core
                                     │ GraphStore
                                   Neo4j
```

Packages (monorepo, Python 3.11+, one version):

| Package | Role | Depends on |
| --- | --- | --- |
| florque-graph-core | Generic engine: CRUD, validation, graph stores | none of the others |
| florque-workgraph-domain | Work-graph ontology, mixins, recipes, policies | graph-core |
| florque-signal-hub | Routes external observations to graph nodes | graph-core client, workgraph-domain mixin contracts |
| florque-service | HTTP API, auth, scheduling, wiring | all of the above |
| florque-cli (fwg) | One command for agents and humans, local or remote | client interface |
| plugin | Claude Code plugin wrapping fwg | fwg |

The CLI is the fifth library package, added because the plugin needs it. The plugin is a distribution artifact, not a library. A small florque-client package holds the client interface shared by the CLI and the service tests.

Rule: dependencies point downward only. graph-core never imports workgraph or the hub. The hub never names a work-graph class; it depends on mixin roles.

Modes:

- **Local:** single user. fwg calls the core in-process against your own Neo4j and SQLite. Trust is by convention.
- **Remote:** fwg calls the service with a token. Database credentials never reach the agent's shell, and permissions are enforced server-side.

## 4. Domain model (workgraph v0.2) LinkML ontology definition

### 4.1 Structure

```
Project  (root, one per effort)
 ├─ Goal: objective ── Goal: key_result
 ├─ WorkItem: initiative ── (epic) ── task | bug
 ├─ Document, Signal
Actor (person | team | agent) ── member_of ──► Project
```

Two typed trees plus links. Initiatives serve goals; metric Signals are about key results.

### 4.2 Classes

| Class | Kinds | Purpose | Parent |
| --- | --- | --- | --- |
| Project | none | Root; one product or effort | none |
| Goal | objective, key\_result | Why. A key result must be measurable | Project (objective); Goal:objective (key\_result) |
| WorkItem | initiative, epic, task, bug | What is done. Epics are optional | initiative: Project; epic: initiative; task, bug: epic or initiative |
| Document | spec, design, guideline, reference | Pointer (uri) plus summary of long-form content | Project |
| Signal | metric, feedback, research, experiment, debrief, incident, insight, update | An observation | Project |
| Actor | person, team, agent | Who owns or does work. Cross-project: no project\_id, joined to projects by member\_of | Actor (team) or none; exempt from the part\_of rule |

Shared fields on every node: id, project\_id (denormalized, immutable; absent on Actor), title, summary, status (proposed, active, done, archived), created\_at, updated\_at, version, owned\_by, sources, aliases.

### 4.3 Edges

| Edge | From → To | Meaning |
| --- | --- | --- |
| part\_of | each class → its typed parent | Containment. Exactly one parent; every node except Project and a top-level Actor has one |
| serves | WorkItem → Goal | Purpose. Initiatives must serve at least one goal |
| depends\_on | WorkItem → WorkItem | Hard prerequisite |
| about | Document, Signal → WorkItem, Goal, Project | Subject |
| member\_of | Actor → Project | Access. Property role: admin, contributor, viewer or hub (hub is assigned only by an admin command) |
| owned\_by | any → Actor | One accountable owner |

### 4.4 Key result expectation

Flat fields on the Goal (level key\_result), supplied by the Expectation mixin:

- Definition: series\_code, comparator (<=, >=, between), target\_value, unit, reducer (last, mean, max, all\_points), window\_start and window\_end (ISO dates), baseline\_value.
- Evaluator-owned: outcome (pending, succeeded, failed, expired), health (on\_track, at\_risk, no\_data), last\_value, last\_observed\_at, evaluated\_at.

Rules: relative targets are resolved to absolute values at creation. Only an admin moves a KR from proposed to active. Definition fields are immutable once the KR is active; a change means a new KR and the old one is archived. Several dimensions mean several KRs under one objective.

### 4.5 Metric Signals

Fields: series\_code, numeric\_value, unit, aggregation, period, source, observed\_at, revision. Natural key: (series\_code, period, source), matched against non-archived nodes only. A corrected value goes through an explicit supersede operation: one transaction archives the old node and creates the new one with revision + 1. The current value is the latest observed\_at that is not archived and has the same unit and aggregation. Store aggregates (one per period), not raw points.

### 4.6 Mixins

Contracts the hub depends on, declared in a small LinkML schema with its own mixins\_version and mixed into workgraph classes. The file lives in workgraph as the published contract. The hub pins a compatible range and owns the conformance test.

- **Expectation:** the fields in 4.4. Mixed into Goal; a LinkML rule requires them when level is key\_result.
- **Observation:** kind, source, observed\_at and an edge to the subject. Mixed into Signal.
- **Routable (later):** title and summary indexed for association.

In Neo4j a node also carries its mixin names as labels (for example :Goal:Expectation), so the hub can find :Expectation nodes without knowing about Goal. It does this through graph-core's find\_by\_mixin operation, never through its own Cypher.

### 4.7 Annotation vocabulary

LinkML annotations are free-form, so the engine owns the list and rejects unknown keys at load.

| Annotation | On | Meaning |
| --- | --- | --- |
| edge, edge\_properties | slot | Relationship type and its properties |
| allowed\_parent | enum value | Allowed parent as Class or Class:kind, comma separated |
| requires | enum value | Edge that must exist at creation |
| root | class | Anchors the graph |
| natural\_key | class | Fields that identify a node exactly |
| dedupe\_scope | class | parent, root, global, or none (natural key and similarity only; used by Signal, whose titles repeat) |
| scope | class | project (default) or global. Global classes (Actor) carry no project\_id and are exempt from part\_of |
| immutable | slot | always, or a status: the field is frozen once the node reaches it (Expectation definition fields use active) |
| merge | class | additive (default) or claims |
| owner | slot | human (default), evaluator, hub or system (engine-managed): who may write the field. Roles map to owners in workgraph policies: admin and contributor write human, hub writes evaluator and hub, viewer writes nothing |
| branch, use\_when, not\_for | class | Agent guidance, rendered into the card |
| required\_kind\_values, required\_edge | mixin class | Contract the host class must satisfy (checked by the hub at startup) |
| mixins\_version | schema | Version of the mixin contract, checked against the hub's compatible range |

### 4.8 Optional modules

The workgraph-impact fragment adds Component, Risk, Period, Commitment and Area, with edges touches, relies\_on, planned\_in, in\_area, threatens, mitigated\_by and rests\_on. It enables the blast\_radius, collision, slip\_alert and plan\_check recipes. Adopt one module at a time, starting with Components and Areas.

## 5. florque-graph-core python app

Purpose: execute CRUD against a graph database and validate everything against an ontology injected from outside. It contains no domain knowledge.

### 5.1 Inputs

- **Ontology:** path to a LinkML schema plus fragments, loaded with SchemaView. Required; startup fails without it.
- **GraphStore:** a graph database backend instance (Neo4j first).
- **Principal:** actor id, role and project scope, passed with every call.
- **Policy hooks:** optional validators registered by the host. The service registers one that checks series\_code against the hub registry.

### 5.2 Operations

| Operation | Behaviour |
| --- | --- |
| describe | Ontology version, class list, generated card |
| get(id, depth) | Node with its parent chain and neighbours to the given depth |
| search(query, cls, scope, limit) | Lexical and optional embedding search inside one project |
| create(cls, props, parent\_id, edges, idempotency\_key, confirm\_new) | Node and parent edge in one transaction |
| update(id, patch, if\_version) | Additive patch with optimistic concurrency |
| archive(id, cascade) | Sets status archived and moves dedupe\_key to archived\_dedupe\_key so the key can be reused; refuses if live children exist unless cascade |
| move(id, new\_parent\_id) | Re-parent with the same validation as create |
| link, unlink | Typed edge between existing nodes |
| merge(keep, drop) | Redirect edges, add the dropped title to aliases, archive the dropped node |
| check(scope) | Run integrity checks |
| changes(since) | Append-only change log; since is the cursor (sequence number) returned by the previous call |
| list\_nodes(scope, cls, filters), edges\_of(id, edge, direction) | Read primitives used by recipes |
| find\_by\_mixin(mixin, filters, scope) | Nodes carrying a mixin label, for hosts such as the hub that work on roles |
| supersede(id, props) | Archive a node and create its next revision in one transaction (metric corrections) |

### 5.3 Validation pipeline

Every write runs these steps in order and fails with an actionable error:

1. Class and kind exist.
2. Slot types, enums and required fields (LinkML).
3. LinkML rules (conditional requirements).
4. Edge typing: source and target classes allowed by slot ranges.
5. Parent rules: single parent, required parent, allowed\_parent by kind, requires.
6. Project isolation: project\_id equal on both endpoints and immutable after creation. Only edges whose target is an Actor (member\_of, owned\_by) cross projects.
7. Field ownership: the principal's role may write each field's owner class. On create, a role allowed to create the class (per the host policy) authors its human fields; evaluator and hub fields still need their owner. On update, every changed field needs its owner.
8. Duplicate protocol: natural\_key, then dedupe\_key, then similarity.
9. Transaction: write, idempotency record and change-log entry together. Idempotency records and change-log entries are infrastructure nodes (:\_Idempotency, :\_ChangeLog) outside the ontology. They are never linked to domain nodes and are hidden from get and search.
10. Integrity check on touched nodes inside the transaction, before commit. The full check(scope) runs asynchronously.

### 5.4 Duplicate protocol

An exact natural\_key or dedupe\_key match returns the existing node (DUPLICATE\_EXACT). A similar match above the review threshold returns candidates and refuses unless confirm\_new is set (DUPLICATE\_SIMILAR). dedupe\_key is a hash of class, kind, parent\_id and normalized title, and is unique per project in the database. Merge rules: fill empty fields, append to the summary, status only moves forward, and conflicts are refused with a review error.

### 5.5 Errors

Every response is {ok, data} or {ok: false, error: {code, message, hint, details}}. Codes: ONTOLOGY\_VIOLATION, PARENT\_RULE, REQUIRED\_EDGE, SCOPE\_VIOLATION, OWNERSHIP, DUPLICATE\_EXACT, DUPLICATE\_SIMILAR, VERSION\_CONFLICT, MERGE\_CONFLICT, NOT\_FOUND, FORBIDDEN, UNAUTHENTICATED. The hint tells the agent what to change.

### 5.6 GraphStore interface

ensure\_schema(ontology) creates constraints and indexes; read(fn) and write(fn) each run fn in one transaction over a small set of primitives (get/find/create/update nodes, create/delete/list edges, search, idempotency records, change log, native integrity checks); health(). No Cypher outside the Neo4j store and a single queries module, and only parameterized queries. A memory store (optionally file-backed) implements the same primitives for tests and single-user local use.

### 5.7 Neo4j mapping

- Labels: class name, Node, and mixin names.
- Relationship types: uppercase slot names.
- Common properties: id, project\_id, dedupe\_key, version, status, created\_at, updated\_at, sources.
- Constraints: unique id on Node; unique (project\_id, dedupe\_key) per label.
- Indexes: status, series\_code, observed\_at.
- Property existence constraints need Enterprise; elsewhere the write layer enforces required fields.

### 5.8 Acceptance

- Rejected: a task under the Project, an initiative without serves, an edge across projects, a write to a field the role does not own.
- The same create with the same idempotency\_key twice yields one node.
- Two parallel creates with one dedupe\_key yield one node.
- Generated integrity checks return zero rows on a fresh graph and flag seeded violations.

## 6. florque-signal-hub

Purpose: listen to external sources and route what they report to graph nodes. It is a separate engine with its own permissions.

### 6.1 Contract

The hub depends on mixin roles, not class names. At startup it asks graph-core which classes carry Expectation and Observation, verifies the fields, types and owner annotations, and refuses to start on a mismatch. Ontology and mixin versions must be inside the declared compatible range.

### 6.2 Observation envelope

source\_id, external\_id, subject\_code, type (metric, incident, feedback or update), value or payload\_ref, observed\_at. Idempotency key: (tenant, source, external\_id). Adapters (sensor poll, webhook, Slack, Teams, email, CI) normalize to this shape.

### 6.3 Lane 1: registered match

subject\_code is looked up in the registry and resolved to a node. Metrics become metric Signals about the key result. The evaluator then checks open expectations:

- pending until the window closes or the reducer decides the target;
- succeeded or failed on the window result;
- expired when the window closes with too little data, which is not a failure;
- health no\_data after N empty days, a grace period before finalizing, and corrections that re-evaluate idempotently and are logged.

Evaluator configuration and defaults: no\_data after 7 empty days; a grace period of 2 days; at\_risk when a linear projection of the series to window\_end misses the target. Reducer all\_points succeeds only if every point in the window satisfies the comparator.

Windows are inclusive dates in the project time zone. An unmatched observation goes to the inbox; the hub never guesses.

### 6.4 Lane 2: association

Channel and email input carries no code. Steps: explicit hints first (ticket id, link, bound thread, channel-to-project mapping, mentions); candidate retrieval inside the mapped project; then an LLM choice among the retrieved candidates only, with cited evidence, or none.

| Confidence | Effect |
| --- | --- |
| High | Signal about the node; thread bound for later messages |
| Medium | Signal as proposed with ranked candidates; one-tap confirm |
| Low | Inbox, or dropped as noise |

Chat text never changes status or structure. Only summaries and links are stored. Channels are opt-in, mapped to a project, and honour membership.

### 6.5 Permissions

The hub runs as an agent Actor with role hub.

- Allowed: create Signals of kind metric, feedback, incident and update with about edges to existing nodes; write evaluator-owned fields on key results.
- Forbidden: create structure, edit titles or targets, change work item status.

Enforcement is in graph-core through owner annotations, not through the hub's own behaviour. Registry changes need a project admin.

### 6.6 Store

A separate database: SQLite in WAL mode first, hosted SQL later, behind a repository interface. The same tests run on both.

- tenant\_id on every table and in every unique key.
- Numbered migrations; portable types (text ids, UTC timestamps, JSON as text).
- Lease-based job claiming (locked\_until, worker\_id).
- Tables: sources, sensors (unique series\_code), channel\_bindings, thread\_bindings, cursors, observation\_ledger (unique on tenant, source\_id, external\_id), inbox, match\_feedback, audit\_log, jobs.

Consistency: KR creation validates series\_code against sensors. A scheduled reconciliation reports unregistered codes, unused sensors and bindings that point at archived nodes. It archives and flags, and never deletes.

### 6.7 Events

Outcome changes (for example pending to failed) emit events for alerts and agents. Writes carry an origin tag to prevent loops.

## 7. florque-service

Purpose: expose the system over HTTP and run the workers.

- Stack: Python ASGI app (FastAPI as the reference choice), OpenAPI generated, versioned under /v1.
- Wiring: loads the ontology, builds graph-core with the Neo4j graph store, registers hub validators, starts hub workers and the scheduler.

| Endpoint | Purpose |
| --- | --- |
| GET /v1/ontology | Version and card |
| POST /v1/projects | Create a Project root |
| GET /v1/nodes/{id}, GET /v1/search | Read |
| POST /v1/nodes, PATCH /v1/nodes/{id} | Create, update |
| POST /v1/nodes/{id}:archive, :move | Lifecycle |
| POST /v1/edges, POST /v1/edges:unlink | Links |
| POST /v1/merge | Merge duplicates |
| GET /v1/recipes/{name} | Context bundles |
| POST /v1/check, GET /v1/changes | Integrity and audit |
| POST /v1/hub/observations | Push ingestion |
| CRUD /v1/hub/sources, /v1/hub/sensors, /v1/hub/bindings | Registry (admin) |
| POST /v1/hub/evaluate, POST /v1/hub/reconcile | Trigger evaluation or reconciliation (admin) |
| POST /v1/nodes:list | Nodes by class and field filters |
| GET /v1/hub/inbox, POST /v1/hub/inbox/{id}:resolve | Triage |
| GET /healthz, GET /readyz, GET /metrics | Probes and Prometheus metrics |

GET /v1/ontology is public (version and card only) so clients can detect drift before authenticating.

Conventions: an Idempotency-Key header on writes; every response includes ontology\_version; errors use the core shape.

Auth: bearer tokens, stored hashed, each bound to an Actor and per-project roles. Roles:

- **admin:** manage members and structure, accept proposals.
- **contributor:** create and edit; agent writes start as proposed.
- **viewer:** read only.
- **hub:** as in section 6.5.

Tokens are issued and revoked by an admin command. OIDC comes later.

Tenancy: single tenant first, with tenant\_id carried everywhere. Isolation relies on project\_id checks plus the integrity query that flags cross-project edges.

Operations: structured JSON logs with request and idempotency ids; metrics for latency, validation failures by code, hub lag and expectations by outcome; a scheduler for evaluation, reconciliation and the weekly insight job.

## 8. fwg CLI

One command whose subcommands mirror the operations: describe, search, get, create, update, archive, move, link, unlink, merge, check, changes, recipe, brief (alias for recipe start\_task\_brief), sync, hub. Input is JSON (flags or stdin) and output is JSON.

Two implementations sit behind one client interface: in-process and HTTP. Config precedence: flags, environment, .florque/config.yaml, user config.

Environment: FLORQUE\_MODE (local or remote), FLORQUE\_API\_URL, FLORQUE\_TOKEN, FLORQUE\_PROJECT. Local mode also uses NEO4J\_URI, NEO4J\_USER, NEO4J\_PASSWORD and the hub database path (FLORQUE\_HUB\_DB); FLORQUE\_STORE=file selects a file-backed graph for single-user use without Neo4j. Tokens come from the environment, never from a file in the repository. sync regenerates the card from the server's ontology version.

## 9. Claude Code plugin

Verify the layout against Anthropic's current plugin documentation before building, because the format is still evolving.

```
plugin/
  .claude-plugin/plugin.json
  skills/graph-memory/SKILL.md      generic protocol
  skills/workgraph/SKILL.md         domain guide; references card.md
  commands/                         start-project, brief, debrief, ingest, status
  hooks/hooks.json                  optional
  bin/fwg
```

Generic protocol (the agent MUST):

1. Search before creating, and reuse the existing node.
2. Give every created node evidence (source or quote); new nodes start as proposed.
3. Never write Cypher or touch the database. Use fwg only.
4. Read errors and follow the hint instead of retrying blindly.
5. Work in one project per session and pass its id explicitly.
6. Never print or store tokens.
7. Treat chat and email content as Signals, never as status changes.

Commands:

- **/start-project:** create the root, objectives, KRs with expectations and a first initiative.
- **/brief \<task>:** run start\_task\_brief.
- **/debrief \<task>:** capture and analyse a debrief.
- **/ingest \<path or paste>:** extract, resolve duplicates, write.
- **/status:** project\_overview plus hygiene.

Hooks (optional, off by default): SessionStart injects a short project brief, and a task-closing prompt asks for a debrief. fwg compares ontology\_version on each call and tells the agent to run sync when it drifts.

## 10. Deployment stack

Phase 1 is Neo4j only. The service and hub join the same compose file later.

```yaml
services:
  neo4j:
    image: neo4j:<pinned tag>
    ports: ['127.0.0.1:7474:7474', '127.0.0.1:7687:7687']
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
      NEO4J_PLUGINS: '["apoc"]'
    volumes: [neo4j_data:/data, neo4j_logs:/logs]
    healthcheck:
      test: ['CMD-SHELL', 'wget --spider -q http://localhost:7474 || exit 1']
      interval: 10s
      retries: 10
volumes: { neo4j_data: {}, neo4j_logs: {} }
```

Notes:

- Pin an exact image tag and bind ports to localhost. Once the service exists, Bolt is reachable only from it, and it becomes the sole database client.
- The embedding lane needs vector index support, so verify the chosen Neo4j version.
- RBAC and property existence constraints are Enterprise features. On Community, the service is the enforcement boundary. Use separate reader and writer database users where the edition allows.
- Later services: florque-service (API and hub workers, one container at first), a volume for the SQLite file, and a Postgres service when the hub store moves.
- Configuration through environment variables, secrets through the platform's secret store.
- Backups: a scheduled Neo4j dump, plus SQLite .backup or Litestream. Test restores.
- Migrations: ensure\_schema is idempotent, hub tables use numbered migrations, and ontology versions are checked at startup.

## 11. Cross-cutting

**Security:** in remote mode agents never hold database credentials. Tokens are scoped per project and role, and the hub has least privilege. Message bodies and files stay out of the graph (links and summaries only). Every write is audit-logged with the acting Actor.

**Testing:** one contract suite runs against both the in-process and HTTP clients. Duplicate and idempotency tests cover same input twice, a paraphrase, and parallel creates. Validation fixtures exist per rule. Hub conformance tests cover the mixin contracts. Golden ingestion cases and registry tests run on SQLite and Postgres.

**Versioning:** one package version, API under /v1, and ontology and mixin versions with a compatibility range checked at startup. Additive ontology changes are minor; anything that breaks existing data needs a migration script.

## 12. Delivery plan

| Milestone | Scope | Done when |
| --- | --- | --- |
| M1 Core and workgraph | graph-core, Neo4j graph store, v0.2 ontology, generator, local fwg, plugin skills | Section 5.8 tests pass; a project built with /start-project has no orphans |
| M2 Service | HTTP API, tokens, remote mode, compose with service | The same contract suite passes over HTTP; a remote agent cannot reach the database |
| M3 Signal hub | Registry, sensor adapter, evaluator, conformance check | A sensor series flips a KR to succeeded or failed correctly and idempotently |
| M4 Association | Slack or email lane, thread bindings, inbox | Precision measured on confirmed proposals; no cross-project leaks |
| M5 Insights and modules | Debrief analysis, recurring issues, impact module | Insights cite evidence and respect the minimum sample |
| M6 Hosted | Postgres hub store, multi-tenant, OIDC | Tenant isolation tests pass |

## 13. Open questions

- Does pi support plugins or skills in a compatible way, or does it need an adapter?
- Where do embeddings live: a Neo4j vector index or a separate store?
- Is the Actor model org-level, with a root organization node?
- Are program areas above Project a node or a property?
- Which Slack, Teams or email source comes first, and how are thread semantics mapped?
- What ontology migration tooling is needed beyond additive changes?

## 14. Decisions

- Recipes are Python functions in workgraph. They call named, parameterized queries registered in graph-core's queries module, so workgraph contains no raw Cypher.
- Monorepo tooling: a uv workspace, with dependency direction enforced by import-linter in CI.
- Embeddings are a pluggable search lane, a no-op until the open question on where they live is resolved.
