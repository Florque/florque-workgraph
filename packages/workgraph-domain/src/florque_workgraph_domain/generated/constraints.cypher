// Constraints and indexes for ontology workgraph 0.2.0 (mixins 0.1.0).
// Generated; do not edit.
CREATE CONSTRAINT node_id_unique IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT idempotency_key_unique IF NOT EXISTS FOR (n:_Idempotency) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT actor_dedupe_unique IF NOT EXISTS FOR (n:Actor) REQUIRE n.dedupe_key IS UNIQUE;
CREATE CONSTRAINT document_dedupe_unique IF NOT EXISTS FOR (n:Document) REQUIRE (n.project_id, n.dedupe_key) IS UNIQUE;
CREATE CONSTRAINT goal_dedupe_unique IF NOT EXISTS FOR (n:Goal) REQUIRE (n.project_id, n.dedupe_key) IS UNIQUE;
CREATE CONSTRAINT project_dedupe_unique IF NOT EXISTS FOR (n:Project) REQUIRE n.dedupe_key IS UNIQUE;
CREATE CONSTRAINT signal_dedupe_unique IF NOT EXISTS FOR (n:Signal) REQUIRE (n.project_id, n.dedupe_key) IS UNIQUE;
CREATE CONSTRAINT workitem_dedupe_unique IF NOT EXISTS FOR (n:WorkItem) REQUIRE (n.project_id, n.dedupe_key) IS UNIQUE;
CREATE INDEX node_project_id IF NOT EXISTS FOR (n:Node) ON (n.project_id);
CREATE INDEX node_status IF NOT EXISTS FOR (n:Node) ON (n.status);
CREATE INDEX node_series_code IF NOT EXISTS FOR (n:Node) ON (n.series_code);
CREATE INDEX node_observed_at IF NOT EXISTS FOR (n:Node) ON (n.observed_at);
CREATE INDEX changelog_project_seq IF NOT EXISTS FOR (c:_ChangeLog) ON (c.project_id, c.seq);
CREATE CONSTRAINT sequence_name_unique IF NOT EXISTS FOR (s:_Sequence) REQUIRE s.name IS UNIQUE;
