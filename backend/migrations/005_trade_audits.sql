-- 005_trade_audits.sql — Per-trade audit scores from heuristic engine.
--
-- Idempotent: tüm CREATE'ler IF NOT EXISTS ile. Migrasyon runner her seferinde
-- bu dosyayı yeniden çalıştırırsa hata vermez ama schema_migrations tablosu
-- zaten kaydı olduğu için runner bu dosyayı tekrar uygulamaz.
--
-- Şema rasyonel:
--   trade_audits.trade_id → trades.id (UUID FK, CASCADE delete)
--   UNIQUE(trade_id) → her trade için bir ses (yeniden audit overwrite)
--   notes JSONB → atr_14h, recent_low/high, candle_count gibi context

CREATE TABLE IF NOT EXISTS trade_audits (
    id BIGSERIAL PRIMARY KEY,
    trade_id UUID NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    entry_score NUMERIC(4,2) NOT NULL CHECK (entry_score BETWEEN 0 AND 10),
    sl_score NUMERIC(4,2) NOT NULL CHECK (sl_score BETWEEN 0 AND 10),
    rr_score NUMERIC(4,2) NOT NULL CHECK (rr_score BETWEEN 0 AND 10),
    overall_score NUMERIC(4,2) NOT NULL CHECK (overall_score BETWEEN 0 AND 10),
    outcome TEXT NOT NULL,
    notes JSONB,
    audited_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (trade_id)
);

CREATE INDEX IF NOT EXISTS idx_audits_audited_at ON trade_audits (audited_at DESC);
CREATE INDEX IF NOT EXISTS idx_audits_overall_score ON trade_audits (overall_score);
