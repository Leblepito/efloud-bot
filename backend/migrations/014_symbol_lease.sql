-- Multi-instance coordination: symbol lease table
-- Part of PR #236 A5 multi-instance migration

CREATE TABLE IF NOT EXISTS symbol_lease (
    symbol TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    lease_token TEXT NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (symbol)
);

-- Index for expired lease cleanup
CREATE INDEX IF NOT EXISTS idx_symbol_lease_expires_at ON symbol_lease(expires_at);

-- Index for instance-specific queries
CREATE INDEX IF NOT EXISTS idx_symbol_lease_instance_id ON symbol_lease(instance_id);