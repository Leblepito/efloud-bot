-- Migration 015: Multi-instance coordination tables
-- PostgreSQL version for asyncpg backend

CREATE TABLE IF NOT EXISTS instance_registry (
    instance_id    TEXT PRIMARY KEY,
    symbols        TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'active',
    started_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_heartbeat TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS symbol_lease (
    symbol      TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL,
    lease_token TEXT NOT NULL,
    acquired_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    FOREIGN KEY (instance_id) REFERENCES instance_registry(instance_id)
);

CREATE INDEX IF NOT EXISTS idx_lease_symbol ON symbol_lease(symbol);
CREATE INDEX IF NOT EXISTS idx_heartbeat ON instance_registry(last_heartbeat);