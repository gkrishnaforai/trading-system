-- 236_conviction_why.sql — explainability contract on The List.
--
-- Every suggestion row must carry its reasoning, not just the call.
-- `why` is the canonical block from app.support.why.explain:
-- {verdict, summary, basis[], drivers[], counter[], coverage,
--  refs[], rule} — journaled fields only, counter required on
-- investable direction.

ALTER TABLE conviction_snapshots
  ADD COLUMN IF NOT EXISTS why jsonb;
