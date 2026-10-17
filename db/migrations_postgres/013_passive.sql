-- Passive-investor surface — model ETF book + journaled tilt suggestions.
-- The tilts are journaled (not executed) so they can be graded later —
-- accountability for the passive layer, same contract as board receipts.
CREATE TABLE IF NOT EXISTS passive_books (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    weights     JSONB NOT NULL,        -- {"VTI": 60, "VXUS": 20, ...}
    note        TEXT,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS passive_tilts (
    as_of       DATE NOT NULL,
    posture     TEXT,
    matched     TEXT,                  -- posture rule that fired
    tilt        JSONB NOT NULL,        -- suggested weights that day
    reason      TEXT,
    PRIMARY KEY (as_of)
);
