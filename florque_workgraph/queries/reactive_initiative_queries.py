# CRUD queries for ReactiveInitiative nodes
CREATE_REACTIVE_INITIATIVE = """
    CREATE (ri:ReactiveInitiative {
        id: $id,
        workspace_id: $workspace_id,
        title: $title,
        description: coalesce($description, ''),
        archived: $archived,
        created_at: datetime(),
        updated_at: datetime()
    })
    RETURN ri
"""

GET_REACTIVE_INITIATIVE = """
    MATCH (ri:ReactiveInitiative {id: $id, workspace_id: $workspace_id})
    RETURN ri
"""

UPDATE_REACTIVE_INITIATIVE = """
    MATCH (ri:ReactiveInitiative {id: $id, workspace_id: $workspace_id})
    SET
        ri.title = $title,
        ri.description = $description,
        ri.archived = $archived,
        ri.updated_at = datetime()
    RETURN ri
"""

DELETE_REACTIVE_INITIATIVE = """
    MATCH (ri:ReactiveInitiative {id: $id, workspace_id: $workspace_id})
    DETACH DELETE ri
"""

SET_REACTIVE_INITIATIVE_ARCHIVED_STATUS = """
    MATCH (ri:ReactiveInitiative {id: $id, workspace_id: $workspace_id})
    SET ri.archived = $archived,
        ri.updated_at = datetime()
    RETURN ri
"""

# Relationship queries
ADD_REACTIVE_INITIATIVE_TO_PROJECT = """
    MATCH (ri:ReactiveInitiative {id: $reactive_initiative_id, workspace_id: $workspace_id})
    MATCH (p:Project {id: $project_id, workspace_id: $workspace_id})
    MERGE (ri)-[:IN_PROJECT]->(p)
"""

CREATE_REACTIVE_INITIATIVE_IN_PROJECT = """
    MATCH (p:Project {id: $project_id, workspace_id: $workspace_id})
    CREATE (ri:ReactiveInitiative {
        id: $id,
        workspace_id: $workspace_id,
        title: $title,
        description: coalesce($description, ''),
        archived: $archived,
        created_at: datetime(),
        updated_at: datetime()
    })
    MERGE (ri)-[:IN_PROJECT]->(p)
    RETURN ri
"""

DELETE_IN_PROJECT_BY_REACTIVE_INITIATIVE = """
    MATCH (ri:ReactiveInitiative {id: $reactive_initiative_id, workspace_id: $workspace_id})-[r:IN_PROJECT]->(:Project)
    DELETE r
"""

GET_PROJECT_REACTIVE_INITIATIVES = """
    MATCH (p:Project {id: $project_id, workspace_id: $workspace_id})<-[:IN_PROJECT]-(ri:ReactiveInitiative)
    WHERE ri.archived = $include_archived OR ri.archived = false
    RETURN ri
"""

GET_REACTIVE_INITIATIVE_TICKETS = """
    MATCH (ri:ReactiveInitiative {id: $reactive_initiative_id, workspace_id: $workspace_id})<-[:EXECUTES]-(t:Ticket)
    WHERE t.archived = $include_archived OR t.archived = false
    RETURN t
"""
