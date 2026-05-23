-- 008_tp2_nullable.sql — Allow trades.tp2 to be NULL (PR #S5.5)
--
-- SMC v2 single-target setups produce Position with tp2=None. PR #S5
-- widened the dataclass type but the DB constraint `tp2 NUMERIC NOT NULL`
-- (from 001_init.sql) would reject the INSERT. This migration drops the
-- NOT NULL constraint.
--
-- Metadata-only change: instant, no table rewrite, no AccessExclusiveLock
-- contention (Postgres ALTER COLUMN DROP NOT NULL is just a catalog flip).
-- Existing rows unaffected.
--
-- Rollback: ALTER TABLE trades ALTER COLUMN tp2 SET NOT NULL;
-- (only works if there are no NULL rows; safe pre-v2-rollout)

ALTER TABLE trades ALTER COLUMN tp2 DROP NOT NULL;
