# ── Ticket: Node Creation ─────────────────────────────────────────────────────

CREATE_TICKET = """
CREATE (t:Ticket {
    id: $id,
    title: $title,
    description: $description,
    status: $status,
    workspace_id: $workspace_id,
    is_project: coalesce($is_project, false),
    archived: coalesce($archived, false),
    created_at: datetime(),
    updated_at: datetime()
})
RETURN t
"""

# ── Ticket: Node Deletion ─────────────────────────────────────────────────────

DELETE_TICKET = (
    "MATCH (t:Ticket {id: $id, workspace_id: $workspace_id}) DETACH DELETE t"
)

DELETE_TICKET_BRANCH = """
MATCH (t:Ticket {id: $id, workspace_id: $workspace_id})
CALL {
    WITH t
    OPTIONAL MATCH (t)-[:INITIATES*]->(sub)
    DETACH DELETE sub
    RETURN count(sub) AS deleted_count
}
DETACH DELETE t
RETURN deleted_count + 1
"""

# ── Ticket: Edge Creation ─────────────────────────────────────────────────────

CREATE_SUBTASK = """
MATCH (parent:Ticket {id: $parent_id, workspace_id: $workspace_id})
MATCH (child:Ticket {id: $child_id, workspace_id: $workspace_id})
MERGE (parent)-[r:INITIATES]->(child)
SET r.archived = coalesce($archived, false)
"""

CREATE_DEPEND_ON = """
MATCH (t1:Ticket {id: $ticket_id, workspace_id: $workspace_id})
MATCH (t2:Ticket {id: $depends_on_id, workspace_id: $workspace_id})
MERGE (t1)-[:DEPEND_ON]->(t2)
"""

CREATE_RELATES_TO = """
MATCH (t1:Ticket {id: $ticket_id, workspace_id: $workspace_id})
MATCH (t2:Ticket {id: $related_id, workspace_id: $workspace_id})
MERGE (t1)-[:RELATES_TO]->(t2)
"""

CREATE_EXECUTES = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
MATCH (g:Goal {id: $goal_id, workspace_id: $workspace_id})
MERGE (t)-[r:EXECUTES]->(g)
SET r.archived = coalesce($archived, false)
"""

CREATE_REQUIRES_STRATEGY = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})
MERGE (t)-[:REQUIRES_STRATEGY]->(s)
"""

# ── Ticket: Edge Deletion ─────────────────────────────────────────────────────

DELETE_SUBTASK = """
MATCH (parent:Ticket {id: $parent_id, workspace_id: $workspace_id})-[r:SUBTASK|INITIATES]->(child:Ticket {id: $child_id, workspace_id: $workspace_id})
DELETE r
"""

DELETE_DEPEND_ON = """
MATCH (t1:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[r:DEPEND_ON]->(t2:Ticket {id: $depends_on_id, workspace_id: $workspace_id})
DELETE r
"""

DELETE_RELATES_TO = """
MATCH (t1:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[r:RELATES_TO]->(t2:Ticket {id: $related_id, workspace_id: $workspace_id})
DELETE r
"""

DELETE_EXECUTES = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[r:EXECUTES]->(g:Goal {id: $goal_id, workspace_id: $workspace_id})
DELETE r
"""

# ── Ticket: Node Getters ──────────────────────────────────────────────────────

GET_TICKET = """
MATCH (t:Ticket {id: $id, workspace_id: $workspace_id})
OPTIONAL MATCH (parent:Ticket {workspace_id: $workspace_id})-[:SUBTASK|INITIATES]->(t)
OPTIONAL MATCH (s:Strategy {is_project: true, workspace_id: $workspace_id})-[:INITIATES]->(t)
RETURN t, parent.id AS parent_id, s IS NOT NULL AS is_initiative
"""

GET_ALL_TICKETS = """
MATCH (t:Ticket {workspace_id: $workspace_id})
OPTIONAL MATCH (parent:Ticket {workspace_id: $workspace_id})-[:SUBTASK|INITIATES]->(t)
OPTIONAL MATCH (s:Strategy {is_project: true, workspace_id: $workspace_id})-[:INITIATES]->(t)
RETURN t, parent.id AS parent_id, s IS NOT NULL AS is_initiative
"""

# ── Ticket: Edge Getters ──────────────────────────────────────────────────────

GET_SUBTASKS = """
MATCH (parent:Ticket {id: $parent_id, workspace_id: $workspace_id})-[:SUBTASK|INITIATES]->(child:Ticket {workspace_id: $workspace_id})
RETURN child
"""

GET_PARENT_TICKETS = """
MATCH (parent:Ticket {workspace_id: $workspace_id})-[:SUBTASK|INITIATES]->(child:Ticket {id: $child_id, workspace_id: $workspace_id})
OPTIONAL MATCH (s:Strategy {is_project: true, workspace_id: $workspace_id})-[:INITIATES]->(parent)
RETURN parent, s IS NOT NULL AS is_initiative
"""

GET_DEPENDENCIES = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[:DEPEND_ON]->(dep:Ticket {workspace_id: $workspace_id})
RETURN dep
"""

GET_DEPENDENTS = """
MATCH (dep:Ticket {workspace_id: $workspace_id})-[:DEPEND_ON]->(t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
RETURN dep
"""

GET_RELATED = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[:RELATES_TO]-(other:Ticket {workspace_id: $workspace_id})
RETURN other
"""

GET_PROJECTS_FOR_WORKSPACE = """
MATCH (t:Ticket {is_project: true, workspace_id: $workspace_id})
RETURN t
"""

GET_TICKETS_FOR_WORKSPACE = """
MATCH (t:Ticket {workspace_id: $workspace_id})
RETURN t, null AS parent_id
"""

GET_TICKET_GOALS = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[:EXECUTES]->(g:Goal {workspace_id: $workspace_id})
RETURN g
"""

GET_TICKET_STRATEGY = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[:REQUIRES_STRATEGY]->(s:Strategy {workspace_id: $workspace_id})
RETURN s
"""

GET_INITIATING_STRATEGY = """
MATCH (s:Strategy {workspace_id: $workspace_id})-[:INITIATES]->(t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
RETURN s
"""

# ── Ticket: Combined Getters ──────────────────────────────────────────────────

SEARCH_TICKETS = """
MATCH (t:Ticket {workspace_id: $workspace_id})
WHERE t.title CONTAINS $search_string OR t.id CONTAINS $search_string
OPTIONAL MATCH (parent:Ticket {workspace_id: $workspace_id})-[:SUBTASK|INITIATES]->(t)
OPTIONAL MATCH (s:Strategy {is_project: true, workspace_id: $workspace_id})-[:INITIATES]->(t)
RETURN t, parent.id AS parent_id, s IS NOT NULL AS is_initiative
"""

GET_ALL_SUBTICKETS_FOR_TICKET = """
MATCH (parent:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[:SUBTASK|INITIATES*1..]->(sub:Ticket {workspace_id: $workspace_id})
RETURN DISTINCT sub
"""

GET_TICKET_EDGES_BY_TYPE = """
MATCH (from_ticket:Ticket {workspace_id: $workspace_id})-[r]->(to_ticket:Ticket {workspace_id: $workspace_id})
WHERE type(r) = $edge_type
  AND (from_ticket.id IN $ticket_ids OR to_ticket.id IN $ticket_ids)
RETURN DISTINCT from_ticket.id AS from_ticket_id, type(r) AS edge_type, to_ticket.id AS to_ticket_id
"""

# ── Ticket: Updates ───────────────────────────────────────────────────────────

UPDATE_TICKET = """
MATCH (t:Ticket {id: $id, workspace_id: $workspace_id})
FOREACH (_ IN CASE WHEN $title IS NOT NULL THEN [1] ELSE [] END |
    SET t.title = $title
)
FOREACH (_ IN CASE WHEN $description IS NOT NULL THEN [1] ELSE [] END |
    SET t.description = $description
)
FOREACH (_ IN CASE WHEN $status IS NOT NULL THEN [1] ELSE [] END |
    SET t.status = $status
)
FOREACH (_ IN CASE WHEN $is_project IS NOT NULL THEN [1] ELSE [] END |
    SET t.is_project = $is_project
)
FOREACH (_ IN CASE WHEN $archived IS NOT NULL THEN [1] ELSE [] END |
    SET t.archived = $archived
)
SET t.updated_at = datetime()
RETURN t
"""

# ── Ticket: Hierarchy / VSGT Retrieval ────────────────────────────────────────

GET_TICKET_ANCESTORS = """
MATCH path = (root:Ticket {workspace_id: $workspace_id})-[:SUBTASK|INITIATES*0..]->(t:Ticket {id: $id, workspace_id: $workspace_id})
RETURN nodes(path) AS path_nodes
"""

GET_TICKET_GOAL_EXECUTION = """
MATCH (t:Ticket {id: $id, workspace_id: $workspace_id})-[:EXECUTES]->(g:Goal {workspace_id: $workspace_id})
RETURN g
"""

GET_ANCESTORS_WITH_GOALS = """
MATCH path = (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})<-[:SUBTASK|INITIATES*0..]-(ancestor:Ticket {workspace_id: $workspace_id})
OPTIONAL MATCH (ancestor)-[:EXECUTES]->(g:Goal {workspace_id: $workspace_id})
RETURN ancestor, g, length(path) AS distance
ORDER BY distance ASC
"""

GET_REASONING_CONTEXT = """
MATCH path = (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})<-[:SUBTASK|INITIATES|REQUIRES_STRATEGY*1..]-(ancestor)
WHERE NONE(x IN nodes(path)[1..-1] WHERE "Strategy" IN labels(x) AND x.is_project = true)
OPTIONAL MATCH (s:Strategy {is_project: true, workspace_id: $workspace_id})-[:INITIATES]->(ancestor)
RETURN ancestor, labels(ancestor) AS labels, s IS NOT NULL AS is_initiative
"""

GET_TICKET_WORKGRAPH = """
MATCH path = (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[:SUBTASK|INITIATES|REQUIRES_STRATEGY*0..]->(downstream)
WHERE downstream.workspace_id = $workspace_id
WITH COLLECT(DISTINCT downstream) AS nodes
UNWIND nodes AS n
OPTIONAL MATCH (n)-[r:SUBTASK|INITIATES|REQUIRES_STRATEGY]->(m)
WHERE m IN nodes

RETURN n AS node, r AS relationship, m AS related_node
"""

# ── Ticket: Archiving ─────────────────────────────────────────────────────────

SET_TICKET_ARCHIVED_STATUS = """
// Find the ticket and its optional incoming relationship first
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
OPTIONAL MATCH (parent)-[r:SUBTASK|INITIATES|EXECUTES]->(t)
WHERE (parent:Ticket OR parent:Goal) AND parent.workspace_id = $workspace_id

// Now, perform all updates
SET t.archived = $archived, t.updated_at = datetime()

// Conditionally update the relationship if it exists
FOREACH (rel IN CASE WHEN r IS NOT NULL THEN [r] ELSE [] END |
    SET rel.archived = $archived
)

RETURN t
"""

SET_SUBTICKETS_ARCHIVED_STATUS_CASCADED = """
// Find all paths to descendant subtickets
MATCH path = (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[:SUBTASK|INITIATES*1..]->(subticket:Ticket {workspace_id: $workspace_id})

// Collect unique nodes and relationships from all found paths
WITH COLLECT(DISTINCT subticket) AS all_subtickets, COLLECT(path) AS all_paths, $archived AS archived_status

// Flatten the list of relationship lists and get unique relationships
UNWIND all_paths AS p
UNWIND relationships(p) AS r
WITH all_subtickets, COLLECT(DISTINCT r) AS all_rels, archived_status

// Perform updates
FOREACH(st IN all_subtickets |
    SET st.archived = archived_status, st.updated_at = datetime()
)
FOREACH(rel IN all_rels |
    SET rel.archived = archived_status
)
"""
