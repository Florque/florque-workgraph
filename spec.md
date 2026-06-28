# Fractal Work Graph Ontology Specification

## 1. Core Principles

* **Fractal Structure:** All work is organized as a recursive tree.
* **Relationship-Driven:** Node behavior and hierarchy are defined by relationships (edges), not just property flags.
* **Workspace Safety:** A mandatory `workspace_id` property exists on every node to prevent orphans and enable global namespace filtering.
* **Dynamic Projection:** Any `Strategy` node can become a "Project" root by setting `is_project: true`. It may be assumed as bookmarking particular strategy as (sub)project.
* **Dynamic  Initiative status** Any `Ticket` node is automatically seen as Initiative if it's executed strategy is "Project" (node has `is_project: true`)

---

## 2. Node Types & Labels

* **`:Strategy`**: Represents intent, vision, and project boundaries.
* **`:Ticket`**: Represents execution units. (Distinguished by the is_initiative(computed) and exec_mode properties).

---

## 3. Relationships & Cardinality

### 3.1 Nodes
| Source Node | Target Node | Relationship | Logic |
| --- | --- | --- | --- |
| `:Strategy` | `:Ticket` | `INITIATES` | Strategy branches into an Initiative. |
| `:Strategy` | `:Goal` | `HAS_GOAL` | Strategy measured by Goal. |
| `:Ticket` | `:Strategy` | `REQUIRES_STRATEGY` | Mandatory link for Creative Ticket type. |
| `:Ticket` | `:Ticket` | `SUBTASK` | Fractal link: Parent ticket manages sub-tickets. |
| `:Ticket` | `:Goal` | `CONTRIBUTES_TO` | Ticket linked to the Goal it contributes to. |

### 3.2 Work graph units
| Work Graph Unit | Source Node + Relevant Property | Cypher Implementation | Use Case |
| --- | --- | --- | --- |
| Project Root | :Strategy {is_project: true} | MATCH (s:Strategy {is_project: true}) | Strategic Planning & Vision
| Execution Strategy | :Strategy | MATCH (s:Strategy {is_project: false}) | Strategic Planning & Vision
| Creative Initiative | :Ticket {exec_mode: 'creative'} | MATCH (s:Strategy {is_project:true})-[:INITIATES]->(t:Ticket {id: $ticket_id, exec_mode:'creative'}) | High-level scoping
| Reactive Initiative | :Ticket {exec_mode: 'reactive'} | MATCH (s:Strategy {is_project:true})-[:INITIATES]->(t:Ticket {id: $ticket_id, exec_mode:'reactive'}) | High-level scoping
| Scheduled Initiative | :Ticket {exec_mode: 'scheduled'} | MATCH (s:Strategy {is_project:true})-[:INITIATES]->(t:Ticket {id: $ticket_id, exec_mode:'scheduled'}) | High-level scoping
| Creative Task | :Ticket {exec_mode: 'creative'} | MATCH (t:Ticket {exec_mode:'creative'})-[:REQUIRES_STRATEGY]->(s:Strategy) | Deep/Focus work
| Reactive Task | :Ticket {exec_mode: 'reactive'} | MATCH (t:Ticket {exec_mode:'reactive'}) | Flow & operational demand, final leaves
| Scheduled Task | :Ticket {exec_mode: 'scheduled'} | MATCH (t:Ticket {exec_mode:'scheduled'})-[:SUBTASK]->(sub:Ticket) | Routine & cadence work
---

## 4. Node Ontology & Rules

### Strategy Nodes

* **`is_project` (Boolean):** If `true`, acts as a project root (bookmark).
* **`workspace_id` (UUID):** Mandatory safety anchor.

### Ticket Roles & Execution Modes

* **Initiative:** The top-level execution node. Must be linked to a `Strategy` with `is_project: true` via `INITIATES`.
* **Creative Ticket:** Must be `REQUIRES_STRATEGY` (Cardinality: 1). Represents qualitative work.
* **Reactive Ticket:** The primary unit of flow.
* Can be `EXECUTED_BY` other Reactive/Creative tickets (nesting).
* Can be a **Leaf** (no outgoing `EXECUTED_BY` edges).

is_initiative query:
MATCH (s:Strategy)-[:INITIATES]-(t:Ticket {id: $ticket_id})
WHERE s.is_project = true
RETURN count(s) > 0 AS is_initiative


* **Repeating Ticket:** The "Scheduler."
* Must use `SCHEDULES` relationship to generate child Reactive tickets based on cadence.



---

## 5. Status & Leaf Logic

* **No `is_leaf` property needed:** A node is programmatically determined as a leaf if it has no outgoing `EXECUTED_BY` or `SCHEDULES` relationships.
* **Status Aggregation:** * `Leaf Status`: User-defined (`todo`, `in_progress`, `done`).
* `Intermediate Status`: Computed recursively via `avg()` of child statuses.



---

## 6. Integrity Safeguards (Memgraph Triggers)

1. **Orphan Prevention:** Any `Ticket` created without a `workspace_id` or an incoming `INITIATES` / `EXECUTED_BY` / `SCHEDULES` edge is rejected.
2. **Strategy Constraint:** Any `Creative` or `Initiative` ticket must have a `REQUIRES_STRATEGY` edge to a valid `Strategy` node upon creation.