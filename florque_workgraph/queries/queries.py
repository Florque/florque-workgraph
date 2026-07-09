# Cypher query registry — all raw Cypher stays here, never in services or repositories
#
# Workspace isolation contract
# ─────────────────────────────
# Every query that touches a Ticket, Timebox node carries a mandatory
# $workspace_id parameter.  Repositories inject this automatically from their
# constructor-bound workspace_id so no cross-tenant operation is possible even
# when a caller supplies a direct node ID.

# ── Node Creation ──────────────────────────────────────────────────────────────

CREATE_WORKSPACE = """
CREATE (w:Workspace {
    id: $id,
    name: $name,
    created_at: datetime()
})
RETURN w
"""

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

UPDATE_USER = """
MATCH (u:User {id: $id})
SET u.name = $name, u.email = $email, u.updated_at = datetime()
RETURN u
"""

CREATE_TENANT = """
CREATE (t:Tenant {
    id: $id,
    name: $name,
    created_at: datetime()
})
RETURN t
"""

# ── Node Deletion ──────────────────────────────────────────────────────────────

DELETE_WORKSPACE = "MATCH (w:Workspace {id: $id}) DETACH DELETE w"
DELETE_TICKET = "MATCH (t:Ticket {id: $id, workspace_id: $workspace_id}) DETACH DELETE t"
DELETE_TIMEBOX = "MATCH (tb:Timebox {id: $id, workspace_id: $workspace_id}) DETACH DELETE tb"
DELETE_USER = "MATCH (u:User {id: $id}) DETACH DELETE u"
DELETE_STRATEGY = "MATCH (s:Strategy {id: $id, workspace_id: $workspace_id}) DETACH DELETE s"
DELETE_GOAL = "MATCH (g:Goal {id: $id, workspace_id: $workspace_id}) DETACH DELETE g"

DELETE_MEMBERSHIP = "MATCH (m:Membership {id: $id, workspace_id: $workspace_id}) DETACH DELETE m"
DELETE_TENANT = "MATCH (t:Tenant {id: $id}) DETACH DELETE t"

# ── Edge Creation ──────────────────────────────────────────────────────────────

CREATE_SUBTASK = """
MATCH (parent:Ticket {id: $parent_id, workspace_id: $workspace_id})
MATCH (child:Ticket {id: $child_id, workspace_id: $workspace_id})
MERGE (parent)-[r:INITIATES]->(child)
SET r.archived = coalesce($archived, false)
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

CREATE_SCHEDULED = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
MATCH (tb:Timebox {id: $timebox_id, workspace_id: $workspace_id})
MERGE (t)-[:SCHEDULED]->(tb)
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

CREATE_TRACKS_VIA = """
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})
MATCH (g:Goal {id: $goal_id, workspace_id: $workspace_id})
MERGE (s)-[:TRACKS_VIA]->(g)
"""

#TODO: possibly change executes to contributes
CREATE_EXECUTES = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
MATCH (g:Goal {id: $goal_id, workspace_id: $workspace_id})
MERGE (t)-[r:EXECUTES]->(g)
SET r.archived = coalesce($archived, false)
"""

# ── Membership ─────────────────────────────────────────────────────────────────
# Membership node creation without edges, used for both attached and detached memberships.
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

GET_MEMBERSHIP = "MATCH (m:Membership {id: $id, workspace_id: $workspace_id}) RETURN m"

GET_MEMBERSHIP_BY_USER_WORKSPACE = """
MATCH (m:Membership {user_id: $user_id, workspace_id: $workspace_id})
RETURN m
"""

GET_PENDING_INVITATIONS = """
MATCH (m:Membership {workspace_id: $workspace_id})
WHERE NOT ()-[:HAS_MEMBERSHIP]->(m)
  AND m.email IS NOT NULL
RETURN m.email AS email
"""

LINK_DETACHED_MEMBERSHIPS = """
MATCH (u:User {id: $user_id})
MATCH (m:Membership {email: $email, workspace_id: $workspace_id})
WHERE m.user_id IS NULL OR m.user_id = '' OR m.user_id = 'detached'
SET m.user_id = u.id
MERGE (u)-[:HAS_MEMBERSHIP]->(m)
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

DELETE_MEMBERSHIP_HAS_ROLE = """
MATCH (m:Membership {id: $membership_id, workspace_id: $workspace_id})-[rel:HAS_ROLE]->(r:Role {id: $role_id, workspace_id: $workspace_id})
DELETE rel
"""

# ── Edge Deletion ──────────────────────────────────────────────────────────────

DELETE_SUBTASK = """
MATCH (parent:Ticket {id: $parent_id, workspace_id: $workspace_id})-[r:SUBTASK|INITIATES]->(child:Ticket {id: $child_id, workspace_id: $workspace_id})
DELETE r
"""

DELETE_ASSIGNED = """
MATCH (u:User {id: $user_id})-[r:ASSIGNED]->(t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
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

DELETE_TRACKS_VIA = """
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})-[r:TRACKS_VIA]->(g:Goal {id: $goal_id, workspace_id: $workspace_id})
DELETE r
"""

DELETE_EXECUTES = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[r:EXECUTES]->(g:Goal {id: $goal_id, workspace_id: $workspace_id})
DELETE r
"""

# ── Node Getters ──────────────────────────────────────────────────────────────

GET_WORKSPACE = "MATCH (w:Workspace {id: $id}) RETURN w"

GET_USER_WORKSPACES = """
MATCH (u:User {id: $user_id})-[:HAS_MEMBERSHIP]->(m:Membership)-[:IN_WORKSPACE]->(w:Workspace)
WHERE m.workspace_id = w.id
RETURN w
"""

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

GET_TIMEBOX = "MATCH (tb:Timebox {id: $id, workspace_id: $workspace_id}) RETURN tb"
GET_ALL_TIMEBOXES = "MATCH (tb:Timebox {workspace_id: $workspace_id}) RETURN tb"

GET_USER = "MATCH (u:User {id: $id}) RETURN u"

GET_USER_BY_EMAIL = "MATCH (u:User {email: $email}) RETURN u"

GET_WORKSPACE_USERS = """
MATCH (u:User)-[:HAS_MEMBERSHIP]->(m:Membership)-[:IN_WORKSPACE]->(w:Workspace {id: $workspace_id})
WHERE m.workspace_id = $workspace_id
RETURN u
"""

GET_STRATEGY = "MATCH (s:Strategy {id: $id, workspace_id: $workspace_id}) RETURN s"
GET_ALL_STRATEGIES = """
MATCH (s:Strategy {workspace_id: $workspace_id})
WHERE $include_archived OR (s.archived IS NULL OR s.archived = false)
RETURN s
"""

GET_GOAL = "MATCH (g:Goal {id: $id, workspace_id: $workspace_id}) RETURN g"
GET_ALL_GOALS = """
MATCH (g:Goal {workspace_id: $workspace_id})
WHERE $include_archived OR (g.archived IS NULL OR g.archived = false)
RETURN g
"""


# ── Edge Getters ──────────────────────────────────────────────────────────────

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

GET_SCHEDULED_TIMEBOX = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[:SCHEDULED]->(tb:Timebox {workspace_id: $workspace_id})
RETURN tb
"""

GET_SCHEDULED_TICKETS = """
MATCH (t:Ticket {workspace_id: $workspace_id})-[:SCHEDULED]->(tb:Timebox {id: $timebox_id, workspace_id: $workspace_id})
RETURN t
"""

GET_PROJECTS_FOR_WORKSPACE = """
MATCH (t:Ticket {is_project: true, workspace_id: $workspace_id})
RETURN t
"""

GET_TICKETS_FOR_WORKSPACE = """
MATCH (t:Ticket {workspace_id: $workspace_id})
RETURN t, null AS parent_id
"""

GET_STRATEGY_GOALS = """
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})-[:TRACKS_VIA]->(g:Goal {workspace_id: $workspace_id})
WHERE $include_archived OR (g.archived IS NULL OR g.archived = false)
RETURN g
"""

GET_GOAL_STRATEGY = """
MATCH (s:Strategy {workspace_id: $workspace_id})-[:TRACKS_VIA]->(g:Goal {id: $goal_id, workspace_id: $workspace_id})
RETURN s
"""

GET_TICKET_GOALS = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[:EXECUTES]->(g:Goal {workspace_id: $workspace_id})
RETURN g
"""

GET_GOAL_TICKETS = """
MATCH (t:Ticket {workspace_id: $workspace_id})-[:EXECUTES]->(g:Goal {id: $goal_id, workspace_id: $workspace_id})
RETURN t
"""

ADD_TICKET_TO_STRATEGY = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})
MERGE (s)-[:INITIATES]->(t)
"""

REMOVE_TICKET_FROM_STRATEGY = """
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})-[r:INITIATES]->(t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
DELETE r
"""

GET_TICKETS_FOR_STRATEGY = """
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})-[:INITIATES]->(t:Ticket {workspace_id: $workspace_id})
RETURN t, s.is_project AS is_initiative
"""

CREATE_REQUIRES_STRATEGY = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})
MERGE (t)-[:REQUIRES_STRATEGY]->(s)
"""

GET_TICKET_STRATEGY = """
MATCH (t:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[:REQUIRES_STRATEGY]->(s:Strategy {workspace_id: $workspace_id})
RETURN s
"""

GET_INITIATING_STRATEGY = """
MATCH (s:Strategy {workspace_id: $workspace_id})-[:INITIATES]->(t:Ticket {id: $ticket_id, workspace_id: $workspace_id})
RETURN s
"""

GET_TICKETS_REQUIRING_STRATEGY = """
MATCH (t:Ticket {workspace_id: $workspace_id})-[:REQUIRES_STRATEGY]->(s:Strategy {id: $strategy_id, workspace_id: $workspace_id})
RETURN t
"""

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

UPDATE_STRATEGY = """
MATCH (s:Strategy {id: $id, workspace_id: $workspace_id})
FOREACH (_ IN CASE WHEN $title IS NOT NULL THEN [1] ELSE [] END | SET s.title = $title)
FOREACH (_ IN CASE WHEN $description IS NOT NULL THEN [1] ELSE [] END | SET s.description = $description)
FOREACH (_ IN CASE WHEN $is_project IS NOT NULL THEN [1] ELSE [] END | SET s.is_project = $is_project)
FOREACH (_ IN CASE WHEN $archived IS NOT NULL THEN [1] ELSE [] END | SET s.archived = $archived)
SET s.updated_at = datetime()
RETURN s
"""

UPDATE_GOAL = """
MATCH (g:Goal {id: $id, workspace_id: $workspace_id})
FOREACH (_ IN CASE WHEN $title IS NOT NULL THEN [1] ELSE [] END | SET g.title = $title)
FOREACH (_ IN CASE WHEN $description IS NOT NULL THEN [1] ELSE [] END | SET g.description = $description)
FOREACH (_ IN CASE WHEN $archived IS NOT NULL THEN [1] ELSE [] END | SET g.archived = $archived)
SET g.updated_at = datetime()
RETURN g
"""

# ── Combined Getters ──────────────────────────────────────────────────────────

GET_ALL_SUBTICKETS_FOR_TICKET = """
MATCH (parent:Ticket {id: $ticket_id, workspace_id: $workspace_id})-[:SUBTASK|INITIATES*1..]->(sub:Ticket {workspace_id: $workspace_id})
RETURN DISTINCT sub
"""

GET_ALL_TICKETS_FOR_ASSIGNEE = """
MATCH (u:User {id: $user_id})-[:ASSIGNED]->(t:Ticket {workspace_id: $workspace_id})
RETURN t
"""

GET_ALL_TICKETS_FOR_TIMEBOX = """
MATCH (t:Ticket {workspace_id: $workspace_id})-[:SCHEDULED]->(tb:Timebox {id: $timebox_id, workspace_id: $workspace_id})
RETURN t
"""

GET_TICKET_EDGES_BY_TYPE = """
MATCH (from_ticket:Ticket {workspace_id: $workspace_id})-[r]->(to_ticket:Ticket {workspace_id: $workspace_id})
WHERE type(r) = $edge_type
  AND (from_ticket.id IN $ticket_ids OR to_ticket.id IN $ticket_ids)
RETURN DISTINCT from_ticket.id AS from_ticket_id, type(r) AS edge_type, to_ticket.id AS to_ticket_id
"""

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

# ── Authorization: Node Deletion ───────────────────────────────────────────────

DELETE_ROLE = "MATCH (r:Role {id: $id, workspace_id: $workspace_id}) DETACH DELETE r"
DELETE_CAPABILITY = "MATCH (c:Capability {id: $id}) DETACH DELETE c"

# ── Authorization: Node Getters ────────────────────────────────────────────────

GET_ROLE = "MATCH (r:Role {id: $id, workspace_id: $workspace_id}) RETURN r"
GET_ALL_ROLES = "MATCH (r:Role {workspace_id: $workspace_id}) RETURN r"

GET_WORKSPACE_ROLES = """
MATCH (r:Role {workspace_id: $workspace_id, scope: 'workspace'})
RETURN r
"""

GET_CAPABILITY = "MATCH (c:Capability {id: $id}) RETURN c"
GET_ALL_CAPABILITIES = "MATCH (c:Capability) RETURN c"

# ── Authorization: Edge Creation ───────────────────────────────────────────────

ADD_CAPABILITY_TO_ROLE = """
MATCH (r:Role {id: $role_id, workspace_id: $workspace_id})
MATCH (c:Capability {id: $capability_id})
MERGE (r)-[:HAS_CAPABILITY]->(c)
"""

# ── Authorization: Edge Deletion ───────────────────────────────────────────────

DELETE_HAS_CAPABILITY = """
MATCH (r:Role {id: $role_id, workspace_id: $workspace_id})-[rel:HAS_CAPABILITY]->(c:Capability {id: $capability_id})
DELETE rel
"""

# ── Authorization: Edge Getters ────────────────────────────────────────────────

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

# ── Constraints ────────────────────────────────────────────────────────────────

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

GET_GOAL_TRACKED_BY_STRATEGY = """
MATCH (s:Strategy {workspace_id: $workspace_id})-[:TRACKS_VIA]->(g:Goal {id: $id, workspace_id: $workspace_id})
RETURN s
"""

GET_STRATEGY_WORKGRAPH = """
MATCH path = (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})-[:INITIATES|SUBTASK|REQUIRES_STRATEGY*0..]->(downstream)
WHERE downstream.workspace_id = $workspace_id
WITH COLLECT(DISTINCT downstream) AS nodes
UNWIND nodes AS n
OPTIONAL MATCH (n)-[r:INITIATES|SUBTASK|REQUIRES_STRATEGY]->(m)
WHERE m IN nodes
OPTIONAL MATCH (s:Strategy {is_project: true, workspace_id: $workspace_id})-[:INITIATES]->(t)
OPTIONAL MATCH (relateds:Strategy {is_project: true, workspace_id: $workspace_id})-[:INITIATES]->(m)
RETURN n AS node, r AS relationship, m AS related_node, s IS NOT NULL AS is_initiative, relateds IS NOT NULL AS is_related_initiative
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

# ── Archiving ──────────────────────────────────────────────────────────────────

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

SET_STRATEGY_ARCHIVED_STATUS = """
MATCH (s:Strategy {id: $strategy_id, workspace_id: $workspace_id})
SET s.archived = $archived, s.updated_at = datetime()
RETURN s
"""

SET_GOAL_ARCHIVED_STATUS = """
MATCH (g:Goal {id: $goal_id, workspace_id: $workspace_id})
SET g.archived = $archived, g.updated_at = datetime()
RETURN g
"""

# ── Labels ─────────────────────────────────────────────────────────────────────

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

GET_LABEL = "MATCH (l:Label {id: $id, workspace_id: $workspace_id}) RETURN l"
GET_ALL_LABELS = "MATCH (l:Label {workspace_id: $workspace_id}) RETURN l"

UPDATE_LABEL = """
MATCH (l:Label {id: $id, workspace_id: $workspace_id})
FOREACH (_ IN CASE WHEN $title IS NOT NULL THEN [1] ELSE [] END | SET l.title = $title)
FOREACH (_ IN CASE WHEN $description IS NOT NULL THEN [1] ELSE [] END | SET l.description = $description)
FOREACH (_ IN CASE WHEN $color IS NOT NULL THEN [1] ELSE [] END | SET l.color = $color)
SET l.updated_at = datetime()
RETURN l
"""

DELETE_LABEL = "MATCH (l:Label {id: $id, workspace_id: $workspace_id}) DETACH DELETE l"

CREATE_LABELED_RELATIONSHIP = """
MATCH (l:Label {id: $label_id, workspace_id: $workspace_id})
MATCH (n)
WHERE (n:Ticket OR n:Goal OR n:Strategy) AND n.id = $node_id AND n.workspace_id = $workspace_id
MERGE (n)-[:LABELED]->(l)
"""

DELETE_LABELED_RELATIONSHIP = """
MATCH (n)-[r:LABELED]->(l:Label {id: $label_id, workspace_id: $workspace_id})
WHERE (n:Ticket OR n:Goal OR n:Strategy) AND n.id = $node_id AND n.workspace_id = $workspace_id
DELETE r
"""

GET_LABELS_FOR_NODE = """
MATCH (n)-[:LABELED]->(l:Label {workspace_id: $workspace_id})
WHERE (n:Ticket OR n:Goal OR n:Strategy) AND n.id = $node_id AND n.workspace_id = $workspace_id
RETURN l
"""

