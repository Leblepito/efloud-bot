-- 003_bar_ts.sql — Add bar_ts_ms column for bar-aligned timestamps.
-- Existing opened_at/closed_at are server NOW() wall-clock; bar_ts_ms
-- records the historical bar's timestamp (epoch milliseconds) for
-- regime-aware analysis and Phase B reconcile.
-- Additive, NULLABLE. Existing rows have NULL bar_ts_ms (acceptable).

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS bar_ts_ms BIGINT;
