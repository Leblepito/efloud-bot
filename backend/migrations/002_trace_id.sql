-- 002_trace_id.sql — Add trace_id column for log correlation.
-- Additive (NULLABLE), idempotent (IF NOT EXISTS where supported).
-- Width: CHAR(12) matches new_trace_id() output exactly (uuid4 hex truncated to 12).

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS trace_id CHAR(12);

-- Index for alerter/post-mortem queries by trace_id
CREATE INDEX IF NOT EXISTS idx_trades_trace_id
    ON trades (trace_id)
    WHERE trace_id IS NOT NULL;
