# ── User: Node Creation ───────────────────────────────────────────────────────

CREATE_USER = """
CREATE (u:User {
    id: $id,
    name: $name,
    email: $email,
    created_at: datetime(),
    updated_at: datetime()
})
RETURN u
"""

UPDATE_USER = """
MATCH (u:User {id: $id})
SET u.name = $name, u.email = $email, u.updated_at = datetime()
RETURN u
"""

# ── User: Node Deletion ───────────────────────────────────────────────────────

DELETE_USER = "MATCH (u:User {id: $id}) DETACH DELETE u"

# ── User: Edge Creation ───────────────────────────────────────────────────────

LINK_DETACHED_MEMBERSHIPS = """
MATCH (u:User {id: $user_id})
MATCH (m:Membership {email: $email, workspace_id: $workspace_id})
WHERE m.user_id IS NULL OR m.user_id = '' OR m.user_id = 'detached'
SET m.user_id = u.id
MERGE (u)-[:HAS_MEMBERSHIP]->(m)
"""

CREATE_ASSIGNED = """
MATCH (u:User {id: $user_id})
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
MERGE (u)-[:ASSIGNED]->(t)
"""

CREATE_CREATED = """
MATCH (u:User {id: $user_id})
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
MERGE (u)-[:CREATED]->(t)
"""

# ── User: Edge Deletion ───────────────────────────────────────────────────────

DELETE_ASSIGNED = """
MATCH (u:User {id: $user_id})-[r:ASSIGNED]->(t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
DELETE r
"""

# ── User: Node Getters ────────────────────────────────────────────────────────

GET_USER = "MATCH (u:User {id: $id}) RETURN u"

GET_USER_BY_EMAIL = "MATCH (u:User {email: $email}) RETURN u"

GET_WORKSPACE_USERS = """
MATCH (u:User)-[:HAS_MEMBERSHIP]->(m:Membership)-[:IN_WORKSPACE]->(w:Workspace {id: $workspace_id})
WHERE m.workspace_id = $workspace_id
RETURN u
"""

GET_USER_WORKSPACES = """
MATCH (u:User {id: $user_id})-[:HAS_MEMBERSHIP]->(m:Membership)-[:IN_WORKSPACE]->(w:Workspace)
WHERE m.workspace_id = w.id
RETURN w
"""

# ── User: Edge Getters ────────────────────────────────────────────────────────

GET_ASSIGNED_TICKETS = """
MATCH (u:User {id: $user_id})-[:ASSIGNED]->(t:Ticket {workspace_id: $workspace_id})
RETURN t
"""

GET_ASSIGNED_USERS = """
MATCH (u:User)-[:ASSIGNED]->(t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
RETURN u
"""

GET_CREATED_TICKETS = """
MATCH (u:User {id: $user_id})-[:CREATED]->(t:Ticket {workspace_id: $workspace_id})
RETURN t
"""

GET_CREATOR = """
MATCH (u:User)-[:CREATED]->(t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
RETURN u
"""

# ── User: Combined Getters ────────────────────────────────────────────────────

GET_ALL_TICKETS_FOR_ASSIGNEE = """
MATCH (u:User {id: $user_id})-[:ASSIGNED]->(t:Ticket {workspace_id: $workspace_id})
RETURN t
"""
