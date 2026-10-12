-- 067: 5x Scout — small-cap multibagger hunter ($1-30B zone).
-- Separate engine from rule_breakers: RB catches names already
-- accelerating; this finds PLTR-2022 fingerprints — platform GM,
-- moderate-but-accelerating rev, hidden fast segment, fortress
-- balance sheet, beaten-down price — BEFORE the repricing.

CREATE TABLE IF NOT EXISTS smallcap_members (
    symbol        text PRIMARY KEY,
    tier          text NOT NULL DEFAULT 'watch',  -- watch|inflecting|runner
    checklist     jsonb NOT NULL DEFAULT '{}',
    promoted_at   timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS smallcap_snapshots (
    id            bigserial,
    symbol        text NOT NULL REFERENCES smallcap_members(symbol)
                  ON DELETE CASCADE,
    as_of         date NOT NULL,
    rev_growth    double precision,
    eps_growth    double precision,
    rev_streak    integer,
    gross_margin  double precision,
    gross_margin_prev double precision,
    op_margin     double precision,
    fcf_margin    double precision,
    cash          double precision,
    total_debt    double precision,
    net_cash      boolean,
    dd52w         double precision,   -- drawdown from 52w high (frac)
    vs_sma200     double precision,   -- price/sma200 - 1 (frac)
    market_cap    double precision,
    price         double precision,
    segments      jsonb,              -- product-line mix + yoy
    hidden_engine jsonb,              -- segments growing >40% YoY
    gates_met     integer NOT NULL DEFAULT 0,
    gates_detail  jsonb NOT NULL DEFAULT '{}',
    sc_score      double precision,
    grade         text,
    PRIMARY KEY (symbol, as_of)
);
CREATE INDEX IF NOT EXISTS idx_sc_snap_sym
    ON smallcap_snapshots (symbol, as_of DESC);
