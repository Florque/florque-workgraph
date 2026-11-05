-- Hub store v1. Portable types: text ids, UTC ISO timestamps, JSON as text.
-- tenant_id is on every table and in every unique key.

CREATE TABLE sources (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  kind TEXT NOT NULL,
  name TEXT,
  config TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  archived_at TEXT,
  PRIMARY KEY (tenant_id, id)
);

CREATE TABLE sensors (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  series_code TEXT NOT NULL,
  source_id TEXT,
  project_id TEXT NOT NULL,
  unit TEXT NOT NULL,
  aggregation TEXT NOT NULL DEFAULT 'last',
  description TEXT,
  flag TEXT,
  created_at TEXT NOT NULL,
  archived_at TEXT,
  PRIMARY KEY (tenant_id, id),
  UNIQUE (tenant_id, series_code)
);

CREATE TABLE channel_bindings (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  project_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  archived_at TEXT,
  flag TEXT,
  PRIMARY KEY (tenant_id, id),
  UNIQUE (tenant_id, source_id, channel)
);

CREATE TABLE thread_bindings (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  thread_ref TEXT NOT NULL,
  node_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  archived_at TEXT,
  flag TEXT,
  PRIMARY KEY (tenant_id, id),
  UNIQUE (tenant_id, source_id, thread_ref)
);

CREATE TABLE cursors (
  tenant_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  cursor TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, source_id)
);

CREATE TABLE observation_ledger (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  external_id TEXT NOT NULL,
  received_at TEXT NOT NULL,
  envelope TEXT NOT NULL,
  status TEXT NOT NULL,
  signal_id TEXT,
  detail TEXT,
  PRIMARY KEY (tenant_id, id),
  UNIQUE (tenant_id, source_id, external_id)
);

CREATE TABLE inbox (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  ledger_id TEXT,
  reason TEXT NOT NULL,
  envelope TEXT NOT NULL,
  candidates TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'open',
  resolution TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolved_by TEXT,
  PRIMARY KEY (tenant_id, id)
);
CREATE INDEX inbox_status ON inbox (tenant_id, status);

CREATE TABLE match_feedback (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  inbox_id TEXT NOT NULL,
  node_id TEXT,
  verdict TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, id)
);

CREATE TABLE audit_log (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  at TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL,
  subject TEXT,
  detail TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (tenant_id, id)
);
CREATE INDEX audit_log_at ON audit_log (tenant_id, at);

CREATE TABLE jobs (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'queued',
  run_after TEXT NOT NULL,
  locked_until TEXT,
  worker_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, id)
);
CREATE INDEX jobs_claim ON jobs (tenant_id, status, run_after);

CREATE TABLE events (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  at TEXT NOT NULL,
  type TEXT NOT NULL,
  node_id TEXT,
  origin TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (tenant_id, id)
);
CREATE INDEX events_at ON events (tenant_id, at);
