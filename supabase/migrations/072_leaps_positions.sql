-- LEAPS position book — the memory layer for the sequential-convexity
-- strategy. The signal engine (leaps.py) is deliberately stateless—
-- this table carries the state the regime rules need: entry level,
-- 60d pre-stall high (put invalidation), ladder tiers already fired,
-- and cooldown after a failed thesis. Human-in-the-loop: rows are
-- recorded decisions, never auto-executed orders.

CREATE TABLE IF NOT EXISTS leaps_positions (
    id              BIGSERIAL PRIMARY KEY,
    stock_symbol    TEXT NOT NULL REFERENCES stocks(symbol),
    side            TEXT NOT NULL CHECK (side IN ('CALL', 'PUT')),
    status          TEXT NOT NULL DEFAULT 'OPEN'
                    CHECK (status IN ('OPEN', 'CLOSED')),

    -- contract
    expiry          DATE NOT NULL,
    strike          NUMERIC NOT NULL,
    contracts       INTEGER NOT NULL DEFAULT 1,

    -- entry snapshot
    entry_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    entry_mid       NUMERIC,              -- premium per share at entry
    entry_spot      NUMERIC,
    entry_delta     NUMERIC,
    entry_iv        NUMERIC,
    entry_hv        NUMERIC,
    capital         NUMERIC,              -- contracts * mid * 100
    thesis_stage    TEXT,                 -- pullback_in_uptrend / ath_extension ...
    gap_score_at_entry INTEGER,
    cyclical        BOOLEAN,
    entry_hi_60d    NUMERIC,              -- pre-stall high → put invalidation
    entry_lo_60d    NUMERIC,              -- pre-wash low → call context

    -- live marks
    mark_mid        NUMERIC,
    mark_spot       NUMERIC,
    mark_at         TIMESTAMPTZ,
    unrealized_pct  NUMERIC,

    -- exit rule state
    ladder_fired    TEXT[] NOT NULL DEFAULT '{}',  -- tp1/tp2/tp3/capitulation
    exit_alert      TEXT,                 -- live actionable alert, if any
    exit_alert_at   TIMESTAMPTZ,

    -- close
    closed_at       TIMESTAMPTZ,
    close_mid       NUMERIC,
    close_reason    TEXT,                 -- climax_tp/stall_tp/capitulation_tp/
                                          -- invalidated/thesis_broken/time_stop/manual
    realized_pct    NUMERIC,

    notes           TEXT,
    meta            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_leaps_positions_symbol ON leaps_positions (stock_symbol, status);
CREATE INDEX IF NOT EXISTS idx_leaps_positions_status ON leaps_positions (status);
