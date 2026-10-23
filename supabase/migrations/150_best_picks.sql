-- 150_best_picks.sql — best_picks_evals: the journal every candidate
-- from the best-picks engine writes to. One row per (as_of, section,
-- symbol): gated names too (score NULL, gate name kept) so the outcome
-- grader can measure what the vetoes rejected, not only what scored.
-- Pillar breakdown, fired-rule notes and the evaluated ctx are kept
-- verbatim — the walk-forward validation contract in best_picks.yaml
-- depends on the point-in-time snapshot, not a reconstructed one.
--
-- NOTE: identical DDL lives in db/migrations_postgres/034_best_picks.sql
-- — that tree is NOT scanned at runtime (run_migrations prefers
-- supabase/migrations); this copy is the one that auto-applies.

-- python-worker AND go-api both apply this tree at boot and the
-- filename is only recorded AFTER the transaction commits — a
-- concurrent boot races this file (IF NOT EXISTS does not guard
-- against an in-flight create). Serialize the two runners on a
-- transaction-scoped advisory lock: loser waits, then its
-- IF NOT EXISTS / ON CONFLICT statements no-op cleanly.
SELECT pg_advisory_xact_lock(715150);

CREATE TABLE IF NOT EXISTS best_picks_evals (
    id            BIGSERIAL PRIMARY KEY,
    as_of         DATE         NOT NULL,
    section       TEXT         NOT NULL,  -- growth_swing | long_term |
                                          -- compounder_3_5y
    symbol        TEXT         NOT NULL,
    score         NUMERIC(6,1),           -- raw, unbounded (can exceed
                                          -- 100 via adjust legs);
                                          -- NULL when gated
    tier          TEXT         NOT NULL,  -- A|B|C|X (X = rejected/gated)
    lane          TEXT         NOT NULL,  -- pick | watch | excluded —
                                          -- the selection outcome
    label         TEXT,                   -- tier label: deploy|core|
                                          -- starter|watch|reject
    routing       JSONB,                  -- routing labels applied:
                                          -- cyclical_review|thin_tape|
                                          -- research|unverified_fundamentals
    gate          TEXT,                   -- matched gate name when gated
    reason        TEXT,                   -- rendered gate/tier why
    pillars       JSONB,                  -- pillar → capped points
    hits          JSONB,                  -- fired rule notes (audit)
    missing       JSONB,                  -- absent/None inputs the eval
                                          -- encountered
    ctx_snapshot  JSONB,                  -- the evaluated ctx — the
                                          -- point-in-time record the
                                          -- backtest grades against
    rules_version TEXT,                   -- spec version + content hash
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (as_of, section, symbol)
);

CREATE INDEX IF NOT EXISTS best_picks_evals_asof_idx
    ON best_picks_evals (as_of DESC, section, tier);
CREATE INDEX IF NOT EXISTS best_picks_evals_symbol_idx
    ON best_picks_evals (symbol, as_of DESC);

-- the engine's scheduled pass — after the evening momentum +
-- fundamentals refreshes so the eval reads today's data
INSERT INTO job_definitions (name, label, cron, enabled)
VALUES ('best-picks', 'Best picks — 3-lane selection', '40 22 * * *',
        true)
ON CONFLICT (name) DO NOTHING;
