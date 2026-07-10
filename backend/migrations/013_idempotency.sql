-- Idempotency tablosu: mobile close_position çift-post korunması
-- Postgres row-level lock + unique constraint ile idempotent DDL
CREATE TABLE IF NOT EXISTS mobile_idempotency (
    id SERIAL PRIMARY KEY,
    bot_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (bot_id, idempotency_key)
);

-- Index sonraki sorgular için
CREATE INDEX IF NOT EXISTS idx_mobile_idempotency_key
    ON mobile_idempotency (idempotency_key)
    WHERE created_at > NOW() - INTERVAL '7 days';