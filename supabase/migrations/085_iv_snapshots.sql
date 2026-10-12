-- 085 — daily IV snapshots per screened symbol.
-- The options screen already computes iv_hv (IV vs realized vol) per
-- contract; this table turns each screen into a stored daily ATM-IV
-- print so a true IV RANK (today's IV percentile vs its own 1y history)
-- accrues over time. Until history is thick, iv_rank falls back to
-- the iv_hv ratio flag.

CREATE TABLE IF NOT EXISTS iv_snapshots (
  symbol    TEXT NOT NULL,
  as_of     DATE NOT NULL,
  atm_iv    NUMERIC(8,5),          -- median near-the-money call IV (decimal)
  hv20      NUMERIC(8,5),          -- 20d realized vol (decimal)
  iv_hv     NUMERIC(8,4),          -- atm_iv / hv20
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (symbol, as_of)
);

CREATE INDEX IF NOT EXISTS idx_iv_snap_sym ON iv_snapshots(symbol, as_of DESC);
