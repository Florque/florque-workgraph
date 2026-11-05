---
name: workgraph
description: Domain guide for the Florque work graph — projects, objectives and key results, initiatives/epics/tasks/bugs, documents, signals and actors. Use when planning, recording or explaining work in a Florque project through the fwg CLI.
---

# Florque workgraph

The graph has one **Project** root per effort and two typed trees under it:

- **Goals:** `objective` (under the Project) → `key_result` (under an objective). A key result is measurable: it carries `series_code`, `comparator`, `target_value`, `unit`, `reducer`, `window_start` and `window_end`.
- **Work:** `initiative` (under the Project, must `serves` at least one Goal) → optional `epic` → `task` / `bug`.
- **Document** (spec, design, guideline, reference) and **Signal** (metric, feedback, research, experiment, debrief, incident, insight, update) sit under the Project and point at their subject with `about`.
- **Actor** (person, team, agent) is cross-project and joins projects with `member_of`; any node may be `owned_by` one Actor.

The full class card is in `generated/card.md` (refresh it with `fwg sync`).

## Protocol

1. `fwg search` before `fwg create`; reuse what exists. `DUPLICATE_EXACT` gives you the node to reuse; `DUPLICATE_SIMILAR` lists candidates (pass `--confirm-new` only if it really is new).
2. Give every node evidence in `sources`. New nodes start as `proposed`; an admin accepts them.
3. Never write Cypher or touch the database. Use `fwg` only.
4. On an error, read `hint` and change the request. Don't retry blindly.
5. Work in one project per session and pass its id (`FLORQUE_PROJECT`).
6. Never print or store tokens.
7. Record chat and email content as Signals. Never turn it into status changes.

## Useful recipes

| Recipe | Use |
| --- | --- |
| `fwg recipe project_overview project_id=<id>` | Objectives, KRs with outcome/health, active initiatives |
| `fwg recipe why node_id=<id>` | Why a node exists, up to the objective |
| `fwg brief <task>` | Goal chain, documents, feedback, lessons and owner for a task |
| `fwg recipe kr_progress kr_id=<id>` | Baseline, latest value, trend, staleness |
| `fwg recipe hygiene project_id=<id>` | Initiatives serving nothing, incomplete KRs, stale proposals |
