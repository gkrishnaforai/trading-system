-- Pre-market session snapshots — the gap + overnight-crypto read that
-- currently goes dark between yesterday's close and the first RTH eval.
-- Two slots per session (early ≈8:25 ET, final ≈9:25 ET) let the card
-- show whether the gap firmed or faded into the open.

CREATE TABLE IF NOT EXISTS premarket_snapshots (
  date        date        NOT NULL,
  slot        text        NOT NULL,           -- 'early' | 'final'
  ts          timestamptz NOT NULL DEFAULT now(),
  qqq_pm      numeric,                        -- last pre-market price
  qqq_gap     numeric,                        -- vs prior close, frac
  spy_pm      numeric,
  spy_gap     numeric,
  smh_pm      numeric,
  smh_gap     numeric,
  btc_chg     numeric,                        -- 24h change, frac
  eth_chg     numeric,
  raw         jsonb,
  PRIMARY KEY (date, slot)
);

CREATE INDEX IF NOT EXISTS premarket_snapshots_date_idx
  ON premarket_snapshots (date DESC);
