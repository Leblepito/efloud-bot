-- 007_smc_v2_telemetry.sql — SMC v2 telemetry columns on trades (PR #S5)
--
-- Adds 4 nullable telemetry columns for post-mortem analysis of v2 trades.
-- All columns NULLABLE; historical rows (pre-PR-#S5) remain NULL.
-- Idempotent via IF NOT EXISTS — safe to re-run.
--
-- Field semantics (mirrors Position dataclass in engine/lifecycle.py +
-- exchange/__init__.py):
--   entry_setup_source: "FVG_PULLBACK" | "OTE_RETRACE" | "V1_LEGACY" | NULL
--   tp1_target_type:    "LIQUIDITY"    | "FVG_NEAR"    | "RR_PROJECTION" | NULL
--   tp2_target_type:    "FVG_FAR"      | "FIB_EXT"     | "NONE"          | NULL
--   bars_to_pullback:   int bars elapsed AWAITING_PULLBACK → IN_ZONE | NULL

ALTER TABLE trades ADD COLUMN IF NOT EXISTS entry_setup_source TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS tp1_target_type    TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS tp2_target_type    TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS bars_to_pullback   INT;
