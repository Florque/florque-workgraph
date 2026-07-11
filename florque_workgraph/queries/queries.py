# Cypher query registry — all raw Cypher stays here, never in services or repositories
#
# Workspace isolation contract
# ─────────────────────────────
# Every query that touches a Ticket, Timebox node carries a mandatory
# $workspace_id parameter.  Repositories inject this automatically from their
# constructor-bound workspace_id so no cross-tenant operation is possible even
# when a caller supplies a direct node ID.

from .ticket import *
from .strategy import *
from .goal import *
from .user import *
from .authorization import *

# ── Workspace & Tenant: Node Creation ─────────────────────────────────────────

CREATE_WORKSPACE = """
CREATE (w:Workspace {
    id: $id,
    name: $name,
    created_at: datetime()
})
RETURN w
"""

CREATE_TENANT = """
CREATE (t:Tenant {
    id: $id,
    name: $name,
    created_at: datetime()
})
RETURN t
"""

# ── Workspace & Tenant: Node Deletion ─────────────────────────────────────────

DELETE_WORKSPACE = "MATCH (w:Workspace {id: $id}) DETACH DELETE w"
DELETE_TENANT = "MATCH (t:Tenant {id: $id}) DETACH DELETE t"

# ── Workspace: Node Getters ───────────────────────────────────────────────────

GET_WORKSPACE = "MATCH (w:Workspace {id: $id}) RETURN w"


# ── Timebox: Node Creation ────────────────────────────────────────────────────

CREATE_TIMEBOX = """
CREATE (tb:Timebox {
    id: $id,
    name: $name,
    start_date: date($start_date),
    end_date: date($end_date),
    status: $status,
    workspace_id: $workspace_id
})
RETURN tb
"""

# ── Timebox: Node Deletion ────────────────────────────────────────────────────

DELETE_TIMEBOX = "MATCH (tb:Timebox {id: $id, workspace_id: $workspace_id}) DETACH DELETE tb"

# ── Timebox: Edge Creation ────────────────────────────────────────────────────

CREATE_SCHEDULED = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
MATCH (tb:Timebox {id: $timebox_id, workspace_id: $workspace_id})
MERGE (t)-[:SCHEDULED]->(tb)
"""

# ── Timebox: Node Getters ──────────────────────────────────────────────────────

GET_TIMEBOX = "MATCH (tb:Timebox {id: $id, workspace_id: $workspace_id}) RETURN tb"

GET_ALL_TIMEBOXES = "MATCH (tb:Timebox {workspace_id: $workspace_id}) RETURN tb"

# ── Timebox: Edge Getters ──────────────────────────────────────────────────────

GET_SCHEDULED_TIMEBOX = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[:SCHEDULED]->(tb:Timebox {workspace_id: $workspace_id})
RETURN tb
"""

GET_SCHEDULED_TICKETS = """
MATCH (t:Ticket {workspace_id: $workspace_id})-[:SCHEDULED]->(tb:Timebox {id: $timebox_id, workspace_id: $workspace_id})
RETURN t
"""

# ── Timebox: Combined Getters ─────────────────────────────────────────────────

GET_ALL_TICKETS_FOR_TIMEBOX = """
MATCH (t:Ticket {workspace_id: $workspace_id})-[:SCHEDULED]->(tb:Timebox {id: $timebox_id, workspace_id: $workspace_id})
RETURN t
"""


# ── Labels: Node Creation ─────────────────────────────────────────────────────

CREATE_LABEL = """
CREATE (l:Label {
    id: $id,
    title: $title,
    description: $description,
    color: $color,
    workspace_id: $workspace_id,
    created_at: datetime(),
    updated_at: datetime()
})
RETURN l
"""

# ── Labels: Node Deletion ─────────────────────────────────────────────────────

DELETE_LABEL = "MATCH (l:Label {id: $id, workspace_id: $workspace_id}) DETACH DELETE l"

# ── Labels: Edge Creation ─────────────────────────────────────────────────────

CREATE_LABELED_RELATIONSHIP = """
MATCH (l:Label {id: $label_id, workspace_id: $workspace_id})
MATCH (n)
WHERE (n:Ticket OR n:Goal OR n:Strategy) AND n.id = $node_id AND n.workspace_id = $workspace_id
MERGE (n)-[:LABELED]->(l)
"""

# ── Labels: Edge Deletion ─────────────────────────────────────────────────────

DELETE_LABELED_RELATIONSHIP = """
MATCH (n)-[r:LABELED]->(l:Label {id: $label_id, workspace_id: $workspace_id})
WHERE (n:Ticket OR n:Goal OR n:Strategy) AND n.id = $node_id AND n.workspace_id = $workspace_id
DELETE r
"""

# ── Labels: Node Getters ──────────────────────────────────────────────────────

GET_LABEL = "MATCH (l:Label {id: $id, workspace_id: $workspace_id}) RETURN l"
GET_ALL_LABELS = "MATCH (l:Label {workspace_id: $workspace_id}) RETURN l"

# ── Labels: Edge Getters ──────────────────────────────────────────────────────

GET_LABELS_FOR_NODE = """
MATCH (n)-[:LABELED]->(l:Label {workspace_id: $workspace_id})
WHERE (n:Ticket OR n:Goal OR n:Strategy) AND n.id = $node_id AND n.workspace_id = $workspace_id
RETURN l
"""

# ── Labels: Updates ───────────────────────────────────────────────────────────

UPDATE_LABEL = """
MATCH (l:Label {id: $id, workspace_id: $workspace_id})
FOREACH (_ IN CASE WHEN $title IS NOT NULL THEN [1] ELSE [] END | SET l.title = $title)
FOREACH (_ IN CASE WHEN $description IS NOT NULL THEN [1] ELSE [] END | SET l.description = $description)
FOREACH (_ IN CASE WHEN $color IS NOT NULL THEN [1] ELSE [] END | SET l.color = $color)
SET l.updated_at = datetime()
RETURN l
"""


# ── Constraints ───────────────────────────────────────────────────────────────

CONSTRAINTS = [
    "CREATE CONSTRAINT ON (t:Ticket) ASSERT t.id IS UNIQUE",
    "CREATE CONSTRAINT ON (u:User) ASSERT u.id IS UNIQUE",
    "CREATE CONSTRAINT ON (tb:Timebox) ASSERT tb.id IS UNIQUE",
    "CREATE CONSTRAINT ON (t:Tenant) ASSERT t.id IS UNIQUE",
    "CREATE CONSTRAINT ON (w:Workspace) ASSERT w.id IS UNIQUE",
    "CREATE CONSTRAINT ON (r:Role) ASSERT r.id IS UNIQUE",
    "CREATE CONSTRAINT ON (c:Capability) ASSERT c.id IS UNIQUE",
    "CREATE CONSTRAINT ON (m:Membership) ASSERT m.id IS UNIQUE",
    "CREATE CONSTRAINT ON (s:Strategy) ASSERT s.id IS UNIQUE",
    "CREATE CONSTRAINT ON (g:Goal) ASSERT g.id IS UNIQUE",
    "CREATE CONSTRAINT ON (l:Label) ASSERT l.id IS UNIQUE",
]


# ── Hierarchy / VSGT Retrieval ────────────────────────────────────────────────

GET_NODE_TYPE_AND_LABELS = """
MATCH (n {id: $id, workspace_id: $workspace_id})
RETURN labels(n) AS labels, n
"""
