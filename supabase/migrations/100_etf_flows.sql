-- ETF AUM snapshots → derived fund flows.
-- No vendor publishes free daily flow history— the mechanical truth is
--   flow ≈ ΔAUM − (AUM_prev × daily_return)
-- i.e. the AUM change NOT explained by market movement = net
-- creations/redemptions. Snapshot AUM daily, flows accrue over time.
CREATE TABLE IF NOT EXISTS etf_aum_snapshots (
    id         bigserial PRIMARY KEY,
    snap_date  date NOT NULL,
    symbol     text NOT NULL,
    aum        double precision,      -- assets under management, $
    nav        double precision,      -- net asset value
    shares     double precision,      -- aum/nav — implied shares out
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (snap_date, symbol)
);
CREATE INDEX IF NOT EXISTS etf_aum_sym_date_idx
    ON etf_aum_snapshots (symbol, snap_date DESC);
