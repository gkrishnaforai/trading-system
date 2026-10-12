-- Hedge book — the portfolio's insurance program. Index/ETF put
-- spreads journaled with structure + cost— marked daily— the
-- monetization ladder fires alerts as option value realizes.
-- Advisory only — the human executes, the system remembers.
CREATE TABLE IF NOT EXISTS hedge_positions (
    id            bigserial PRIMARY KEY,
    as_of         date NOT NULL,
    instrument    text NOT NULL,           -- e.g. 'QQQ put spread'
    underlier     text NOT NULL,           -- 'QQQ'
    expiry        date NOT NULL,
    long_strike   numeric NOT NULL,        -- the protective put we own
    short_strike  numeric NOT NULL,        -- the put we sold (cost offset)
    qty           int NOT NULL DEFAULT 1,
    cost          numeric NOT NULL,        -- net debit paid (insurance cost)
    notional      numeric,                 -- covered notional ≈ qty×100×spot
    spot_at_entry numeric,
    vix_at_entry  numeric,
    regime_note   text,                    -- why the hedge was staged
    status        text NOT NULL DEFAULT 'open',   -- open|trimmed|closed
    mark_value    numeric,                 -- latest mid of the spread
    mark_at       timestamptz,
    spot_mark     numeric,
    realized_pct  numeric,                 -- of max payoff (width)
    trim_events   jsonb DEFAULT '[]',      -- ladder fills {date, pct, mid}
    closed_at     timestamptz,
    close_reason  text,
    created_at    timestamptz DEFAULT now(),
    updated_at    timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS hedge_status_idx ON hedge_positions (status);

-- annual budget ledger lives in engine_weights['hedge:budget']:
-- {year, cap_pct, spent} — spend caps adapt to the regime read.
