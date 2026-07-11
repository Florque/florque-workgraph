# ── Strategy: Node Creation ───────────────────────────────────────────────────

CREATE_STRATEGY = """
CREATE (s:Strategy {
    id: $id,
    title: $title,
    description: $description,
    workspace_id: $workspace_id,
    is_project: coalesce($is_project, false),
    archived: coalesce($archived, false),
    created_at: datetime(),
    updated_at: datetime()
})
RETURN s
"""

# ── Strategy: Node Deletion ───────────────────────────────────────────────────

DELETE_STRATEGY = "MATCH (s:Strategy {id: $id, workspace_id: $workspace_id}) DETACH DELETE s"

# ── Strategy: Edge Creation ───────────────────────────────────────────────────

CREATE_TRACKS_VIA = """
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})
MATCH (g:Goal {id: $goal_id, workspace_id: $workspace_id})
MERGE (s)-[:TRACKS_VIA]->(g)
"""

ADD_TICKET_TO_STRATEGY = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})
MERGE (s)-[:INITIATES]->(t)
"""

# ── Strategy: Edge Deletion ───────────────────────────────────────────────────

DELETE_TRACKS_VIA = """
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})-[r:TRACKS_VIA]->(g:Goal {id: $goal_id, workspace_id: $workspace_id})
DELETE r
"""

REMOVE_TICKET_FROM_STRATEGY = """
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})-[r:INITIATES]->(t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
DELETE r
"""

# ── Strategy: Node Getters ────────────────────────────────────────────────────

GET_STRATEGY = "MATCH (s:Strategy {id: $id, workspace_id: $workspace_id}) RETURN s"

GET_ALL_STRATEGIES = """
MATCH (s:Strategy {workspace_id: $workspace_id})
WHERE $include_archived OR (s.archived IS NULL OR s.archived = false)
RETURN s
"""

# ── Strategy: Edge Getters ────────────────────────────────────────────────────

GET_STRATEGY_GOALS = """
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})-[:TRACKS_VIA]->(g:Goal {workspace_id: $workspace_id})
WHERE $include_archived OR (g.archived IS NULL OR g.archived = false)
RETURN g
"""

GET_TICKETS_FOR_STRATEGY = """
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})-[:INITIATES]->(t:Ticket {workspace_id: $workspace_id})
RETURN t, s.is_project AS is_initiative
"""

GET_TICKETS_REQUIRING_STRATEGY = """
MATCH (t:Ticket {workspace_id: $workspace_id})-[:REQUIRES_STRATEGY]->(s:Strategy {id: $strategy_id, workspace_id: $workspace_id})
RETURN t
"""

# ── Strategy: Updates ─────────────────────────────────────────────────────────

UPDATE_STRATEGY = """
MATCH (s:Strategy {id: $id, workspace_id: $workspace_id})
FOREACH (_ IN CASE WHEN $title IS NOT NULL THEN [1] ELSE [] END | SET s.title = $title)
FOREACH (_ IN CASE WHEN $description IS NOT NULL THEN [1] ELSE [] END | SET s.description = $description)
FOREACH (_ IN CASE WHEN $is_project IS NOT NULL THEN [1] ELSE [] END | SET s.is_project = $is_project)
FOREACH (_ IN CASE WHEN $archived IS NOT NULL THEN [1] ELSE [] END | SET s.archived = $archived)
SET s.updated_at = datetime()
RETURN s
"""

# ── Strategy: Archiving ───────────────────────────────────────────────────────

SET_STRATEGY_ARCHIVED_STATUS = """
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})
SET s.archived = $archived, s.updated_at = datetime()
RETURN s
"""
