-- Multi-instance coordination: instance registry table
-- Part of PR #236 A5 multi-instance migration

CREATE TABLE IF NOT EXISTS instance_registry (
    instance_id TEXT NOT NULL PRIMARY KEY,
    symbols TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for heartbeat queries and dead instance cleanup
CREATE INDEX IF NOT EXISTS idx_instance_registry_last_heartbeat ON instance_registry(last_heartbeat) WHERE status = 'active';

-- Index for status queries
CREATE INDEX IF NOT EXISTS idx_instance_registry_status ON instance_registry(status);
