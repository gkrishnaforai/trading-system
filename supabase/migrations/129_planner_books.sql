-- 129 — planner_books: journaled capital-planner proposals.
-- The accepted book's positions live as trade_plans rows (thesis
-- carries [book#N])— this table is the provenance record — capital,
-- target, regime stance, and the full proposal payload for replay.
CREATE TABLE IF NOT EXISTS planner_books (
    id          serial PRIMARY KEY,
    as_of       date        NOT NULL DEFAULT CURRENT_DATE,
    capital     numeric     NOT NULL,
    target_pct  numeric     NOT NULL,
    risk_pct    numeric     NOT NULL,
    stance      text,
    regime      text,
    payload     jsonb       NOT NULL,
    status      text        NOT NULL DEFAULT 'proposed',  -- proposed|accepted|closed
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_planner_books_status
    ON planner_books (status, as_of DESC);
