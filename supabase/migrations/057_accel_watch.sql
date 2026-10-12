-- Acceleration watch — per-run growth streaks for every scored symbol.
-- rev/eps_streak = consecutive quarters where the YoY growth rate improved—
-- *_decel = consecutive declines. Snapshots let the API detect streak
-- breaks (was >=2, now <2 = thesis dead) across candidate runs.

CREATE TABLE IF NOT EXISTS accel_watch (
    id          bigserial PRIMARY KEY,
    run_id      uuid NOT NULL,
    symbol      text NOT NULL,
    rev_streak  int NOT NULL DEFAULT 0,
    eps_streak  int NOT NULL DEFAULT 0,
    rev_decel   int NOT NULL DEFAULT 0,
    eps_decel   int NOT NULL DEFAULT 0,
    rev_path    numeric[],
    eps_path    numeric[],
    verdict     text,
    price       numeric,
    in_portfolio boolean DEFAULT false,
    in_watchlist boolean DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_accel_watch_run ON accel_watch (run_id);
CREATE INDEX IF NOT EXISTS idx_accel_watch_sym ON accel_watch (symbol, run_id);
