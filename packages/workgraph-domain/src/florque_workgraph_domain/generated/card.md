# Ontology card: workgraph 0.2.0

<!-- ontology_version: 0.2.0; mixins_version: 0.1.0. Generated; do not edit. -->

Every node except the root and global classes has exactly one parent (`parent_id`).
New nodes start as `proposed`. Search before creating; follow error hints.

## Classes

### Project

Root; one product or effort.

- **Use when:** Starting a new product or effort.
- **Root:** no parent; one per effort

Edges: `owned_by` → Actor

Fields: `time_zone`: str; `title`: str (required); `summary`: str; `status`: Status; `sources`: str (list); `aliases`: str (list)

### Goal

Why. Objectives contain key results; a key result must be measurable.

- **Use when:** Expressing why work exists (objective) or how success is measured (key_result).
- **Not for:** Deliverables or activities; use WorkItem.
- **Branch:** goals
- **Mixins:** Expectation

| Kind | Parent | Requires |
| --- | --- | --- |
| objective | Project | — |
| key_result | Goal:objective | — |

Edges: `owned_by` → Actor

Fields: `series_code`: str (frozen when active); `comparator`: Comparator (frozen when active); `target_value`: float (frozen when active); `target_upper`: float (frozen when active); `unit`: str; `reducer`: Reducer (frozen when active); `window_start`: date (frozen when active); `window_end`: date (frozen when active); `baseline_value`: float (frozen when active); `outcome`: Outcome (owner=evaluator); `health`: Health (owner=evaluator); `last_value`: float (owner=evaluator); `last_observed_at`: datetime (owner=evaluator); `evaluated_at`: datetime (owner=evaluator); `kind`: GoalKind (required); `title`: str (required); `summary`: str; `status`: Status; `sources`: str (list); `aliases`: str (list)
- **Rule** (when kind=key_result): requires series_code, comparator, target_value, unit, reducer, window_start, window_end

### WorkItem

What is done. Epics are optional.

- **Use when:** Planned work at any granularity (initiative, epic, task, bug).
- **Not for:** Outcomes or measurements; use Goal.
- **Branch:** work

| Kind | Parent | Requires |
| --- | --- | --- |
| initiative | Project | serves |
| epic | WorkItem:initiative | — |
| task | WorkItem:epic, WorkItem:initiative | — |
| bug | WorkItem:epic, WorkItem:initiative | — |

Edges: `serves` → Goal; `depends_on` → WorkItem; `owned_by` → Actor

Fields: `kind`: WorkItemKind (required); `title`: str (required); `summary`: str; `status`: Status; `sources`: str (list); `aliases`: str (list)

### Document

Pointer plus summary of long-form content.

- **Use when:** A spec, design, guideline or reference that lives elsewhere.
- **Not for:** Storing file contents; keep a link and a summary only.

| Kind | Parent | Requires |
| --- | --- | --- |
| spec | Project | — |
| design | Project | — |
| guideline | Project | — |
| reference | Project | — |

Edges: `about` → Goal, Project, WorkItem; `owned_by` → Actor

Fields: `uri`: str (required); `kind`: DocumentKind (required); `title`: str (required); `summary`: str; `status`: Status; `sources`: str (list); `aliases`: str (list)

### Signal

An observation (metric, feedback, research, incident, ...).

- **Use when:** Evidence from outside the plan (metrics, feedback, chat, incidents).
- **Not for:** Changing status or structure.
- **Mixins:** Observation

| Kind | Parent | Requires |
| --- | --- | --- |
| metric | Project | — |
| feedback | Project | — |
| research | Project | — |
| experiment | Project | — |
| debrief | Project | — |
| incident | Project | — |
| insight | Project | — |
| update | Project | — |

Edges: `about` → Goal, Project, WorkItem; `owned_by` → Actor

Fields: `source`: str; `observed_at`: datetime; `series_code`: str (frozen when active); `numeric_value`: float; `unit`: str; `aggregation`: str; `period`: str; `revision`: int; `payload_ref`: str; `kind`: SignalKind (required); `title`: str (required); `summary`: str; `status`: Status; `sources`: str (list); `aliases`: str (list)
- **Rule** (when kind=metric): requires series_code, numeric_value, unit, period, observed_at
- **Natural key:** series_code, period, source

### Actor

Who owns or does work. Cross-project.

- **Use when:** A person, team or agent that owns or does work.
- **Scope:** global (no project_id; joined to projects by member_of)

| Kind | Parent | Requires |
| --- | --- | --- |
| person | Actor:team | — |
| team | Actor:team | — |
| agent | Actor:team | — |

Edges: `member_of` → Project; `owned_by` → Actor

Fields: `kind`: ActorKind (required); `title`: str (required); `summary`: str; `status`: Status; `sources`: str (list); `aliases`: str (list)

## Enums

- **Comparator:** <=, >=, between
- **Health:** on_track, at_risk, no_data
- **Outcome:** pending, succeeded, failed, expired
- **Reducer:** last, mean, max, all_points
- **Status:** proposed, active, done, archived

## Error codes

ONTOLOGY_VIOLATION, PARENT_RULE, REQUIRED_EDGE, SCOPE_VIOLATION, OWNERSHIP, DUPLICATE_EXACT, DUPLICATE_SIMILAR, VERSION_CONFLICT, MERGE_CONFLICT, NOT_FOUND, FORBIDDEN, UNAUTHENTICATED
