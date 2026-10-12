-- Event-day calls — versioned macro-event judgments.
-- On scheduled event days (NFP/CPI/PPI/PCE/FOMC), the engine gathers
-- the full regime context and produces a green/red/choppy read —
-- LLM-assisted when configured, deterministic fallback when not.
-- Graded at EOD against realized SPY so each event KIND accrues its
-- own track record (jobs days vs FOMC days behave differently).
CREATE TABLE IF NOT EXISTS event_day_calls (
    id           bigserial PRIMARY KEY,
    as_of        date NOT NULL,
    event_name   text NOT NULL,
    event_kind   text NOT NULL,            -- nfp | cpi | ppi | pce | fomc
    verdict      text NOT NULL,            -- green | red | choppy
    confidence   int,
    thesis       text,
    premarket_spy double precision,        -- % move vs prior close
    context      jsonb,                    -- the full input bundle
    judge        text,                     -- 'llm:<model>' | 'rules'
    spy_ret_1d   double precision,         -- graded: realized day return
    correct      boolean,
    graded_at    timestamptz,
    created_at   timestamptz DEFAULT now(),
    UNIQUE (as_of, event_kind)
);
CREATE INDEX IF NOT EXISTS event_day_calls_date_idx
    ON event_day_calls (as_of DESC);
