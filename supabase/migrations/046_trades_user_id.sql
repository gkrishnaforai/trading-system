-- Tag ledger rows by owner so backtest/simulated trades stay separate
-- from real manual trades. Default keeps existing rows as 'manual'.

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS user_id text NOT NULL DEFAULT 'manual';

CREATE INDEX IF NOT EXISTS idx_trades_user_status ON trades (user_id, status);
