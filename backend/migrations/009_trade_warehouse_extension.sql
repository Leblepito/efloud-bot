-- 009_trade_warehouse_extension.sql — Database Warehouse Extension for Trades (Phase 3.2)
--
-- Adds additional telemetry and excursion columns to the trades table
-- for deep post-mortem analysis.
--
-- Excursion fields:
--   mae_pct: Max Adverse Excursion % (defaults to 0.0)
--   mfe_pct: Max Favorable Excursion % (defaults to 0.0)
--
-- Telemetry fields:
--   initial_sl: Original SL set at open (to preserve zone metrics)
--   adx_value: ADX indicator value at entry time
--   atr_value: ATR indicator value at entry time
--   funding_rate: Funding rate of the contract at entry time
--   confluence_details: JSONB containing sub-scores, reasons, and HTF/MTF biases
--

ALTER TABLE trades ADD COLUMN IF NOT EXISTS mae_pct NUMERIC NOT NULL DEFAULT 0.0;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS mfe_pct NUMERIC NOT NULL DEFAULT 0.0;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS initial_sl NUMERIC;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS adx_value NUMERIC;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS atr_value NUMERIC;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS funding_rate NUMERIC;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS confluence_details JSONB;
