-- Idempotency tablosu: mobile close_position çift-post korunması
-- Postgres row-level lock + unique constraint ile idempotent DDL
CREATE TABLE IF NOT EXISTS mobile_idempotency (
    id SERIAL PRIMARY KEY,
    bot_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (bot_id, idempotency_key)
);

-- Index sonraki sorgular için (partial index with stable function)
CREATE INDEX IF NOT EXISTS idx_mobile_idempotency_key
    ON mobile_idempotency (idempotency_key, created_at);