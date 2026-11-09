---
name: graph-memory
description: Persistent project memory in the Florque Workgraph, reached only through the fwg CLI. Use it before starting a task to recall why work exists, who owns it, what it depends on and which specs or metrics relate to it, and to record new work items, decisions, findings or metrics so they persist across sessions and agents. Covers setup (register, login, tokens) and the rules every write follows.
---

# Graph memory (fwg)

All access goes agent → `fwg` → the Florque service. Every command prints one JSON envelope:
`{"ok": true, "data": ..., "ontology_version": "..."}` or
`{"ok": false, "error": {"code", "message", "hint", "details"}}`; exit code 0 means ok.
The classes, kinds and parents are in the `workgraph` skill.

## Setup (once per machine)

Check first: `fwg whoami`. If it answers `UNAUTHENTICATED`, ask the user to run one of these
themselves (they need the emailed code; never ask them to paste a token into the chat):

```bash
uv tool install florque-cli                      # or: pipx install florque-cli
fwg --api-url https://<server> register --invite XXXX-XXXX-XXXX --email <address>
fwg --api-url https://<server> login --email <address>    # new machine; prompts for the code
```

The token lands in `~/.config/florque/credentials.json` (0600). For CI or a headless agent:
`fwg token create --label ci --agent`, then set `FLORQUE_API_URL` and `FLORQUE_TOKEN` in that
environment; `--project <id>` limits such a token to one project (enforced by the server).
`fwg use <id>` binds the current folder to a project (`.florque/config.yaml`, safe to commit);
`/project` picks or switches it.

## Protocol (MUST)

1. Search before creating (`fwg search "<words>" -p <id>`), and reuse the existing node.
2. Give every created node evidence in `sources` (a link, path or quote). New nodes start as `proposed`.
3. Never write Cypher or touch a database. Use `fwg` only.
4. Read errors and follow `error.hint` instead of retrying the same call.
5. Work in one project per session: the one bound to this folder (`fwg status`; the session start
   context names it). If none is bound, ask the user and run `fwg use <id>`. Never pass another `-p` unless the user asks.
6. Never print, log or store tokens.
7. Treat chat and email content as Signals, never as status changes.

## Typical calls

| Goal | Command |
| --- | --- |
| Context for a task | `fwg brief <task_id>` |
| Big picture | `fwg recipe project_overview project_id=<id>` |
| Read a node | `fwg get <id>` (note `version` for updates) |
| New task | `fwg create WorkItem --kind task --title "..." --parent <epic_id> --prop 'sources=["<link>"]'` |
| Dependency | `fwg link <task> depends_on <other_task>` |
| Status change | `fwg update <id> --set status=done --if-version <n>` |
| A finding | `fwg create Signal --kind insight --title "..." --parent <project_id> --edge about:<node_id>` |
| Metric value | `echo '<observation JSON>' \| fwg hub ingest` |
| Integrity | `fwg recipe hygiene project_id=<id>` / `fwg check -p <id>` |

Errors you will meet: `DUPLICATE_EXACT` (reuse `details.existing`), `DUPLICATE_SIMILAR` (reuse a
candidate or repeat with `--confirm-new`), `VERSION_CONFLICT` (`get` again, reapply), `SCOPE_VIOLATION`
(wrong parent or cross-project edge), `NOT_FOUND`, `FORBIDDEN`, `RATE_LIMITED` (wait `Retry-After`).
When a response says the ontology changed, run `fwg sync`.
