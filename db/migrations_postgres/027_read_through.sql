-- read_through_evals — basket-level repricing events detected in
-- extended hours. One peer's earnings/guidance/commentary can reprice
-- a whole theme (e.g. 2026-10-20: SMCI guide raise + SPCX call lifted
-- APLD/CRWV/IREN/NBIS/DELL/HPE/HUT/CORZ 3-6%). The detector journals
-- the event so the morning regime and plan engines see the overnight
-- repricing instead of discovering it at the open.

CREATE TABLE IF NOT EXISTS read_through_evals (
    id          BIGSERIAL PRIMARY KEY,
    as_of       DATE NOT NULL,
    session     TEXT NOT NULL,            -- 'post' | 'pre'
    basket      TEXT NOT NULL,            -- book name or sector
    direction   TEXT NOT NULL,            -- 'up' | 'down'
    n_members   INT NOT NULL,
    n_moved     INT NOT NULL,
    max_move    NUMERIC,                  -- largest |%| mover
    leader      TEXT,                     -- the biggest mover
    members     JSONB NOT NULL,           -- [{sym, pct}]
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS read_through_evals_date_idx
    ON read_through_evals (as_of DESC);
