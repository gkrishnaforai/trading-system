-- Morning regime horizons — the 1-month and 3-month scenario layers.
-- horizon_1m / horizon_3m: scenario trees (base/bull/bear/stress +
-- observable triggers + key catalysts), journaled daily.
-- spy_ret_60d / qqq_ret_60d + regime_3m_correct: the 3-month grade.
ALTER TABLE morning_regime_snapshots
    ADD COLUMN IF NOT EXISTS horizon_1m jsonb,
    ADD COLUMN IF NOT EXISTS horizon_3m jsonb,
    ADD COLUMN IF NOT EXISTS spy_ret_60d double precision,
    ADD COLUMN IF NOT EXISTS qqq_ret_60d double precision,
    ADD COLUMN IF NOT EXISTS regime_3m_correct boolean;
