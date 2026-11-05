// Integrity checks (parameter $project_id); each returns violation rows for ontology workgraph 0.2.0 (mixins 0.1.0).
// Generated; do not edit.

// multiple_parents: Node with more than one parent
MATCH (n:Node)-[r:PART_OF]->(:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' WITH n, count(r) AS c WHERE c > 1 RETURN 'multiple_parents' AS `check`, n.id AS node_id, toString(c) + ' parents' AS detail;

// cross_project_edge: Edge between nodes of different projects (Actor targets exempt)
MATCH (n:Node)-[r]->(m:Node) WHERE n.project_id = $project_id AND n.project_id IS NOT NULL AND m.project_id IS NOT NULL AND n.project_id <> m.project_id RETURN 'cross_project_edge' AS `check`, n.id AS node_id, type(r) + ' ' + n.id + '->' + m.id AS detail;

// goal_orphan: Goal without a parent
MATCH (n:Goal) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND NOT (n)-[:PART_OF]->(:Node) RETURN 'goal_orphan' AS `check`, n.id AS node_id, 'no parent' AS detail;

// goal_objective_parent_kind: Goal:objective under a parent not in Project
MATCH (n:Goal)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'objective' AND NOT ((p:Project)) RETURN 'goal_objective_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// goal_key_result_parent_kind: Goal:key_result under a parent not in Goal:objective
MATCH (n:Goal)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'key_result' AND NOT ((p:Goal AND p.kind = 'objective')) RETURN 'goal_key_result_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// workitem_orphan: WorkItem without a parent
MATCH (n:WorkItem) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND NOT (n)-[:PART_OF]->(:Node) RETURN 'workitem_orphan' AS `check`, n.id AS node_id, 'no parent' AS detail;

// workitem_initiative_parent_kind: WorkItem:initiative under a parent not in Project
MATCH (n:WorkItem)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'initiative' AND NOT ((p:Project)) RETURN 'workitem_initiative_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// workitem_initiative_without_serves: Live WorkItem:initiative without a serves edge
MATCH (n:WorkItem) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'initiative' AND NOT (n)-[:SERVES]->(:Node) RETURN 'workitem_initiative_without_serves' AS `check`, n.id AS node_id, 'missing SERVES' AS detail;

// workitem_epic_parent_kind: WorkItem:epic under a parent not in WorkItem:initiative
MATCH (n:WorkItem)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'epic' AND NOT ((p:WorkItem AND p.kind = 'initiative')) RETURN 'workitem_epic_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// workitem_task_parent_kind: WorkItem:task under a parent not in WorkItem:epic, WorkItem:initiative
MATCH (n:WorkItem)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'task' AND NOT ((p:WorkItem AND p.kind = 'epic') OR (p:WorkItem AND p.kind = 'initiative')) RETURN 'workitem_task_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// workitem_bug_parent_kind: WorkItem:bug under a parent not in WorkItem:epic, WorkItem:initiative
MATCH (n:WorkItem)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'bug' AND NOT ((p:WorkItem AND p.kind = 'epic') OR (p:WorkItem AND p.kind = 'initiative')) RETURN 'workitem_bug_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// document_orphan: Document without a parent
MATCH (n:Document) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND NOT (n)-[:PART_OF]->(:Node) RETURN 'document_orphan' AS `check`, n.id AS node_id, 'no parent' AS detail;

// document_spec_parent_kind: Document:spec under a parent not in Project
MATCH (n:Document)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'spec' AND NOT ((p:Project)) RETURN 'document_spec_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// document_design_parent_kind: Document:design under a parent not in Project
MATCH (n:Document)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'design' AND NOT ((p:Project)) RETURN 'document_design_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// document_guideline_parent_kind: Document:guideline under a parent not in Project
MATCH (n:Document)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'guideline' AND NOT ((p:Project)) RETURN 'document_guideline_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// document_reference_parent_kind: Document:reference under a parent not in Project
MATCH (n:Document)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'reference' AND NOT ((p:Project)) RETURN 'document_reference_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// signal_orphan: Signal without a parent
MATCH (n:Signal) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND NOT (n)-[:PART_OF]->(:Node) RETURN 'signal_orphan' AS `check`, n.id AS node_id, 'no parent' AS detail;

// signal_metric_parent_kind: Signal:metric under a parent not in Project
MATCH (n:Signal)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'metric' AND NOT ((p:Project)) RETURN 'signal_metric_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// signal_feedback_parent_kind: Signal:feedback under a parent not in Project
MATCH (n:Signal)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'feedback' AND NOT ((p:Project)) RETURN 'signal_feedback_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// signal_research_parent_kind: Signal:research under a parent not in Project
MATCH (n:Signal)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'research' AND NOT ((p:Project)) RETURN 'signal_research_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// signal_experiment_parent_kind: Signal:experiment under a parent not in Project
MATCH (n:Signal)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'experiment' AND NOT ((p:Project)) RETURN 'signal_experiment_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// signal_debrief_parent_kind: Signal:debrief under a parent not in Project
MATCH (n:Signal)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'debrief' AND NOT ((p:Project)) RETURN 'signal_debrief_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// signal_incident_parent_kind: Signal:incident under a parent not in Project
MATCH (n:Signal)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'incident' AND NOT ((p:Project)) RETURN 'signal_incident_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// signal_insight_parent_kind: Signal:insight under a parent not in Project
MATCH (n:Signal)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'insight' AND NOT ((p:Project)) RETURN 'signal_insight_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// signal_update_parent_kind: Signal:update under a parent not in Project
MATCH (n:Signal)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'update' AND NOT ((p:Project)) RETURN 'signal_update_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// actor_without_membership: Actor with no member_of edge
MATCH (n:Actor)-[:MEMBER_OF]->(:Node) WITH collect(DISTINCT n.id) AS members MATCH (n:Actor) WHERE coalesce(n.status, '') <> 'archived' AND NOT n.id IN members AND (n)-[]-(:Node {project_id: $project_id}) RETURN 'actor_without_membership' AS `check`, n.id AS node_id, 'no membership' AS detail;

// actor_person_parent_kind: Actor:person under a parent not in Actor:team
MATCH (n:Actor)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'person' AND NOT ((p:Actor AND p.kind = 'team')) RETURN 'actor_person_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// actor_team_parent_kind: Actor:team under a parent not in Actor:team
MATCH (n:Actor)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'team' AND NOT ((p:Actor AND p.kind = 'team')) RETURN 'actor_team_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;

// actor_agent_parent_kind: Actor:agent under a parent not in Actor:team
MATCH (n:Actor)-[:PART_OF]->(p:Node) WHERE n.project_id = $project_id AND coalesce(n.status, '') <> 'archived' AND n.kind = 'agent' AND NOT ((p:Actor AND p.kind = 'team')) RETURN 'actor_agent_parent_kind' AS `check`, n.id AS node_id, 'parent=' + coalesce(p.`class`, '?') + ':' + coalesce(p.kind, '') AS detail;
