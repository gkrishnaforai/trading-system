-- daily_puts + daily_put_outcomes — the short-side twin of
-- daily_calls: journaled put calls from the leap_put-ready board,
-- graded by first-touch of stop (stock rallies) vs target (stock
-- drops). ret_* are put-side: a -8% drop records +8.

CREATE TABLE IF NOT EXISTS daily_puts (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    call_date   date NOT NULL,
    rank        integer NOT NULL,
    symbol      text NOT NULL,
    score       double precision,
    entry_px    double precision,
    stop_px     double precision,
    target_px   double precision,
    rr          double precision,
    state       text,
    dip_phase   text,
    evidence    jsonb NOT NULL DEFAULT '[]',
    created_at  timestamptz DEFAULT now(),
    UNIQUE (call_date, symbol)
);

CREATE TABLE IF NOT EXISTS daily_put_outcomes (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    call_id       bigint NOT NULL UNIQUE REFERENCES daily_puts(id),
    call_date     date NOT NULL,
    symbol        text NOT NULL,
    entry_px      double precision,
    stop_px       double precision,
    target_px     double precision,
    eod_close     double precision,
    ret_eod       double precision,
    ret_5d        double precision,
    ret_10d       double precision,
    ret_20d       double precision,
    mfe           double precision,
    mae           double precision,
    resolution    text NOT NULL DEFAULT 'open',
    resolved_date date,
    days_held     integer,
    graded_at     timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS daily_puts_date_idx ON daily_puts (call_date DESC);
CREATE INDEX IF NOT EXISTS daily_put_outcomes_date_idx ON daily_put_outcomes (call_date DESC);
