-- engine_weights_log was appended to 078 AFTER prod had already
-- applied that file — the runner keys on filename, so the appended
-- CREATE never ran there. New file = guaranteed apply everywhere.
-- Fully idempotent: no-op where the table already exists.
CREATE TABLE IF NOT EXISTS engine_weights_log (
    id        serial PRIMARY KEY,
    key       text NOT NULL,
    value     jsonb NOT NULL,
    n         int,
    win_rate  double precision,
    logged_at timestamptz NOT NULL DEFAULT now()
);
