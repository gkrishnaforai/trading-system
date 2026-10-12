-- Trade ledger: manual journal of real trades across horizons.
-- A trade links to the setup_signal that spawned it so the learning loop
-- can compare actual fills and exits against hypothetical signal outcomes.

CREATE TABLE IF NOT EXISTS trades (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          text NOT NULL,
    trade_type      text NOT NULL DEFAULT 'swing',
    status          text NOT NULL DEFAULT 'open',
    signal_id       uuid REFERENCES setup_signals(id),
    entry_date      date NOT NULL,
    entry_price     double precision NOT NULL,
    shares          double precision NOT NULL,
    initial_stop    double precision,
    target_1        double precision,
    target_2        double precision,
    setup_type      text,
    regime_snapshot jsonb DEFAULT '{}',
    thesis          text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    closed_at       timestamptz,
    realized_pl     double precision
);

CREATE INDEX IF NOT EXISTS idx_trades_status ON trades (status, symbol);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades (symbol, entry_date DESC);

CREATE TABLE IF NOT EXISTS trade_exits (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id    uuid NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    exit_date   date NOT NULL,
    price       double precision NOT NULL,
    qty         double precision NOT NULL,
    reason      text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trade_exits_trade ON trade_exits (trade_id, exit_date);
