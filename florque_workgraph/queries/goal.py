# ── Goal: Node Creation ───────────────────────────────────────────────────────

CREATE_GOAL = """
CREATE (g:Goal {
    id: $id,
    title: $title,
    description: $description,
    workspace_id: $workspace_id,
    archived: coalesce($archived, false),
    created_at: datetime(),
    updated_at: datetime()
})
RETURN g
"""

CREATE_GOAL_TRACKING_STRATEGY = """
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})
CREATE (g:Goal {
    id: $id,
    title: $title,
    description: $description,
    workspace_id: $workspace_id,
    archived: coalesce($archived, false),
    created_at: datetime(),
    updated_at: datetime()
})
CREATE (s)-[:TRACKS_VIA]->(g)
RETURN g
"""

# ── Goal: Node Deletion ───────────────────────────────────────────────────────

DELETE_GOAL = "MATCH (g:Goal {id: $id, workspace_id: $workspace_id}) DETACH DELETE g"

# ── Goal: Node Getters ────────────────────────────────────────────────────────

GET_GOAL = "MATCH (g:Goal {id: $id, workspace_id: $workspace_id}) RETURN g"

GET_ALL_GOALS = """
MATCH (g:Goal {workspace_id: $workspace_id})
WHERE $include_archived OR (g.archived IS NULL OR g.archived = false)
RETURN g
"""

# ── Goal: Edge Getters ────────────────────────────────────────────────────────

GET_GOAL_STRATEGY = """
MATCH (s:Strategy {workspace_id: $workspace_id})-[:TRACKS_VIA]->(g:Goal {id: $goal_id, workspace_id: $workspace_id})
RETURN s
"""

GET_GOAL_TICKETS = """
MATCH (t:Ticket {workspace_id: $workspace_id})-[:EXECUTES]->(g:Goal {id: $goal_id, workspace_id: $workspace_id})
RETURN t
"""

# ── Goal: Hierarchy / VSGT Retrieval ──────────────────────────────────────────

GET_GOAL_TRACKED_BY_STRATEGY = """
MATCH (s:Strategy {workspace_id: $workspace_id})-[:TRACKS_VIA]->(g:Goal {id: $id, workspace_id: $workspace_id})
RETURN s
"""

# ── Goal: Updates ─────────────────────────────────────────────────────────────

UPDATE_GOAL = """
MATCH (g:Goal {id: $id, workspace_id: $workspace_id})
FOREACH (_ IN CASE WHEN $title IS NOT NULL THEN [1] ELSE [] END | SET g.title = $title)
FOREACH (_ IN CASE WHEN $description IS NOT NULL THEN [1] ELSE [] END | SET g.description = $description)
FOREACH (_ IN CASE WHEN $archived IS NOT NULL THEN [1] ELSE [] END | SET g.archived = $archived)
SET g.updated_at = datetime()
RETURN g
"""

# ── Goal: Archiving ───────────────────────────────────────────────────────────

SET_GOAL_ARCHIVED_STATUS = """
MATCH (g:Goal {id: $goal_id, workspace_id: $workspace_id})
SET g.archived = $archived, g.updated_at = datetime()
RETURN g
"""
