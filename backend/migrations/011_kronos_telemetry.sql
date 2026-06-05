-- 011_kronos_telemetry.sql — Database extension for Kronos AI commentary.
--
-- Adds kronos_comment (TEXT) and kronos_confidence (INT) columns
-- to the trades table to support persistent time-series forecast logs.

ALTER TABLE public.trades ADD COLUMN IF NOT EXISTS kronos_comment TEXT;
ALTER TABLE public.trades ADD COLUMN IF NOT EXISTS kronos_confidence INT;
