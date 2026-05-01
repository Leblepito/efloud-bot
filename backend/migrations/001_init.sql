-- 001_init.sql — Initial schema for efloud-bot persistence layer.
--
-- Idempotent: tüm CREATE'ler IF NOT EXISTS ile. Migrasyon runner her seferinde
-- bu dosyayı yeniden çalıştırırsa hata vermez ama schema_migrations tablosu
-- zaten kaydı olduğu için runner bu dosyayı tekrar uygulamaz.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ─────────────────────────────────────────────────────────────────
-- trades — Açık + kapalı pozisyon kayıtları
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry NUMERIC NOT NULL,
    exit NUMERIC,
    sl NUMERIC NOT NULL,
    tp1 NUMERIC NOT NULL,
    tp2 NUMERIC NOT NULL,
    size NUMERIC NOT NULL,
    pnl_usdt NUMERIC,
    pnl_pct NUMERIC,
    reason TEXT,
    confluence INT,
    binance_order_id TEXT,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_trades_opened_at ON trades (opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_symbol_open
    ON trades (symbol)
    WHERE closed_at IS NULL;

-- ─────────────────────────────────────────────────────────────────
-- equity_history — Periyodik bakiye snapshot'ları
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS equity_history (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    balance NUMERIC NOT NULL,
    open_positions_count INT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity_history (ts DESC);

-- ─────────────────────────────────────────────────────────────────
-- audit_log — Bot lifecycle ve manuel müdahale kayıtları
-- ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event TEXT NOT NULL,
    payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts DESC);
