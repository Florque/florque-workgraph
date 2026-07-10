# ── Authorization: Node Creation ──────────────────────────────────────────────
#
# Role scope
# ──────────────────
# scope = "workspace"  →  role applies to the entire workspace; project_id is NOT set
# scope = "project"    →  role applies to one project; project_id IS set
#
# The FOREACH trick conditionally sets project_id only when a non-null value is
# provided, keeping workspace-scoped Role nodes free of the property entirely.

CREATE_ROLE = """
CREATE (r:Role {
    id: $id,
    name: $name,
    scope: $scope,
    workspace_id: $workspace_id,
    created_at: datetime()
})
RETURN r
"""

CREATE_CAPABILITY = """
CREATE (c:Capability {
    id: $id,
    name: $name,
    description: $description,
    created_at: datetime()
})
RETURN c
"""

CREATE_MEMBERSHIP = """
CREATE (m:Membership {
    id: $id,
    user_id: $user_id,
    workspace_id: $workspace_id,
    email: $email,
    created_at: datetime()
})
RETURN m
"""

# Create edge between User and Membership for attached memberships (those with a valid user_id) that may have been created after the user was created.
# This ensures that even if detached memberships are created first, they will be linked to the user once the user is created.
# Caller should run this before querying for a user's workspaces to ensure all memberships are properly linked.
CREATE_HAS_MEMBERSHIP = """
MATCH (u:User {id: $user_id})
MATCH (m:Membership {id: $membership_id, workspace_id: $workspace_id})
MERGE (u)-[:HAS_MEMBERSHIP]->(m)
"""

# Create edge between Membership and Workspace for all memberships, including detached ones that may have been created without a user_id.
# This ensures that even detached memberships are properly linked to the workspace so that workspace access checks can find them.
# Caller should run this before querying for a user's workspaces to ensure all memberships are properly linked.
CREATE_MEMBERSHIP_IN_WORKSPACE = """
MATCH (m:Membership {id: $membership_id, workspace_id: $workspace_id})
MATCH (w:Workspace {id: $workspace_id})
MERGE (m)-[:IN_WORKSPACE]->(w)
"""

CREATE_MEMBERSHIP_HAS_ROLE = """
MATCH (m:Membership {id: $membership_id, workspace_id: $workspace_id})
MATCH (r:Role {id: $role_id, workspace_id: $workspace_id})
MERGE (m)-[:HAS_ROLE]->(r)
"""

# ── Authorization: Edge Creation ───────────────────────────────────────────────

ADD_CAPABILITY_TO_ROLE = """
MATCH (r:Role {id: $role_id, workspace_id: $workspace_id})
MATCH (c:Capability {id: $capability_id})
MERGE (r)-[:HAS_CAPABILITY]->(c)
"""

# ── Authorization: Node/Edge Deletion ───────────────────────────────────────────────

DELETE_ROLE = "MATCH (r:Role {id: $id, workspace_id: $workspace_id}) DETACH DELETE r"
DELETE_CAPABILITY = "MATCH (c:Capability {id: $id}) DETACH DELETE c"
DELETE_MEMBERSHIP = "MATCH (m:Membership {id: $id, workspace_id: $workspace_id}) DETACH DELETE m"

DELETE_HAS_CAPABILITY = """
MATCH (r:Role {id: $role_id, workspace_id: $workspace_id})-[rel:HAS_CAPABILITY]->(c:Capability {id: $capability_id})
DELETE rel
"""

DELETE_MEMBERSHIP_HAS_ROLE = """
MATCH (m:Membership {id: $membership_id, workspace_id: $workspace_id})-[rel:HAS_ROLE]->(r:Role {id: $role_id, workspace_id: $workspace_id})
DELETE rel
"""

# ── Authorization: Node/Edge Getters ────────────────────────────────────────────────

GET_MEMBERSHIP = "MATCH (m:Membership {id: $id, workspace_id: $workspace_id}) RETURN m"

GET_MEMBERSHIP_BY_USER_WORKSPACE = """
MATCH (m:Membership {user_id: $user_id, workspace_id: $workspace_id})
RETURN m
"""

GET_USER_ROLES = """
MATCH (u:User {id: $user_id})-[:HAS_MEMBERSHIP]->(m:Membership {workspace_id: $workspace_id})-[:HAS_ROLE]->(r:Role)
WHERE r.workspace_id = $workspace_id
RETURN r
"""

GET_ROLE_USERS = """
MATCH (u:User)-[:HAS_MEMBERSHIP]->(m:Membership {workspace_id: $workspace_id})-[:HAS_ROLE]->(r:Role {id: $role_id, workspace_id: $workspace_id})
WHERE u.id IS NOT NULL
RETURN DISTINCT u
"""

GET_ROLE_CAPABILITIES = """
MATCH (r:Role {id: $role_id, workspace_id: $workspace_id})-[:HAS_CAPABILITY]->(c:Capability)
RETURN c
"""

GET_CAPABILITY_ROLES = """
MATCH (r:Role)-[:HAS_CAPABILITY]->(c:Capability {id: $capability_id})
WHERE r.workspace_id = $workspace_id
RETURN r
"""

GET_MEMBERSHIP_ROLES = """
MATCH (m:Membership {id: $membership_id, workspace_id: $workspace_id})-[:HAS_ROLE]->(r:Role)
WHERE r.workspace_id = $workspace_id
RETURN r
"""

GET_PENDING_INVITATIONS = """
MATCH (m:Membership {workspace_id: $workspace_id})
WHERE NOT ()-[:HAS_MEMBERSHIP]->(m)
  AND m.email IS NOT NULL
RETURN m.email AS email
"""

GET_ROLE = "MATCH (r:Role {id: $id, workspace_id: $workspace_id}) RETURN r"

GET_ALL_ROLES = "MATCH (r:Role {workspace_id: $workspace_id}) RETURN r"

GET_WORKSPACE_ROLES = """
MATCH (r:Role {workspace_id: $workspace_id, scope: 'workspace'})
RETURN r
"""

GET_CAPABILITY = "MATCH (c:Capability {id: $id}) RETURN c"

GET_ALL_CAPABILITIES = "MATCH (c:Capability) RETURN c"