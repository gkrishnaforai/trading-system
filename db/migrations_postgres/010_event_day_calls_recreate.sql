-- Recreate event_day_calls — migration 136 dropped it as "dead" but
-- app/signals/event_day.py still writes the event-day judge's calls
-- and grades them at EOD; calendar.py attaches them to macro events.
-- Combined 095 (create) + 096 (v2 columns) schema.
CREATE TABLE IF NOT EXISTS event_day_calls (
    id           bigserial PRIMARY KEY,
    as_of        date NOT NULL,
    event_name   text NOT NULL,
    event_kind   text NOT NULL,            -- nfp | cpi | ppi | pce | fomc
    verdict      text NOT NULL,            -- green | red | choppy
    confidence   int,
    thesis       text,
    premarket_spy double precision,        -- % move vs prior close
    context      jsonb,
    judge        text,                     -- 'llm:<model>' | 'rules'
    spy_ret_1d   double precision,         -- graded: realized day return
    correct      boolean,
    graded_at    timestamptz,
    probs        jsonb,
    regime_read  text,
    qqq_lean     text,
    qqq_note     text,
    qqq_ret_1d   double precision,
    qqq_correct  boolean,
    print_data   jsonb,
    brier        double precision,
    debrief      text,
    created_at   timestamptz DEFAULT now(),
    UNIQUE (as_of, event_kind)
);
CREATE INDEX IF NOT EXISTS event_day_calls_date_idx
    ON event_day_calls (as_of DESC);
