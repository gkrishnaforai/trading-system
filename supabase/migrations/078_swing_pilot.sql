-- Swing pilot — the paper-trading engine that tests the flag system's
-- calls with real simulated trades, then writes corrections back.
--
-- swing_pilot_trades : every paper trade (version log — never updated
--                      except mark/exit fields; the full lifecycle is
--                      auditable: why entered, how it decayed, why out)
-- engine_weights     : live correction layer the flag engine READS —
--                      pilot-learn writes, daily_board applies
-- engine_weights_log : append-only history of every learned weight
--                      (the 'version table' for how the engine's
--                      opinions changed over time)
CREATE TABLE IF NOT EXISTS swing_pilot_trades (
    id            serial PRIMARY KEY,
    symbol        text NOT NULL,
    entry_date    date NOT NULL,
    entry_px      double precision NOT NULL,
    stop_px       double precision NOT NULL,
    target_px     double precision NOT NULL,
    pattern_key   text NOT NULL,          -- 'pullback|turning_up'
    evidence      jsonb,                  -- state/phase/fund/prior/alerts at entry
    status        text NOT NULL DEFAULT 'open',   -- open|closed
    exit_date     date,
    exit_px       double precision,
    exit_reason   text,                   -- target|stop|momentum_decay|climax|timeout
    ret_pct       double precision,
    mfe_pct       double precision,       -- max favorable/adverse excursion
    mae_pct       double precision,
    hold_days     int,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pilot_open_idx
    ON swing_pilot_trades (status) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS pilot_sym_idx ON swing_pilot_trades (symbol);

CREATE TABLE IF NOT EXISTS engine_weights (
    key          text PRIMARY KEY,        -- 'dip:still_falling', 'gate:pullback|turning_up', ...
    value        jsonb NOT NULL,          -- {"adj":-4} | {"enabled":false} | ...
    n            int,                     -- trades behind the weight
    win_rate     double precision,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS engine_weights_log (
    id        serial PRIMARY KEY,
    key       text NOT NULL,
    value     jsonb NOT NULL,
    n         int,
    win_rate  double precision,
    logged_at timestamptz NOT NULL DEFAULT now()
);
