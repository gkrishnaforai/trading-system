-- thesis_change_events — the journaled history of thesis movement.
--
-- symbol_thesis keeps only the LATEST transition (prev_status /
-- status_since / hyp_changes); this table is the timeline: every
-- coverage start, status transition and material leg change as a
-- self-contained row carrying the evidence snapshot that produced it.
-- The alert_items row links back via alert_id — "which event paged me".
--
-- event_kind:
--   coverage_start      first eval for a symbol — history anchor, never alerts
--   status_transition   top-line status_dir up/down — alerts
--   leg_change          flat top status but a CORE hypothesis moved —
--                       the quiet deterioration/confirmation the rollup hides
--
-- Flat days with only optional-leg shuffles journal nothing — the
-- timeline is changes, not a heartbeat.
--
-- fv_delta_pct / priced_in are declared now so the Phase-2
-- assumption-delta engine doesn't need an ALTER later.

CREATE TABLE IF NOT EXISTS thesis_change_events (
    id           BIGSERIAL PRIMARY KEY,
    symbol       TEXT NOT NULL,
    as_of        DATE NOT NULL,
    event_kind   TEXT NOT NULL,      -- coverage_start | status_transition | leg_change
    archetype    TEXT,
    prev_status  TEXT,
    status       TEXT NOT NULL,
    status_dir   TEXT,               -- up | down | new | flat
    score        NUMERIC,
    hyp_changes  JSONB,              -- [{id, archetype, from, to}]
    veto_fired   JSONB,              -- {id, flag, cap, fatal, evidence}
    evidence     JSONB,              -- per changed hypothesis: checks + notes
    drivers      JSONB,              -- open driver_commitments at eval time
    fv_delta_pct NUMERIC,            -- Phase-2+; null in Phase 1
    priced_in    TEXT,               -- Phase-2+; null in Phase 1
    alert_id     UUID,               -- the alert_items row this event emitted
    detail       JSONB,              -- unresolved / recovery / coverage detail
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, as_of, event_kind, prev_status, status)
);

CREATE INDEX IF NOT EXISTS idx_tce_symbol_date
    ON thesis_change_events (symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_tce_date
    ON thesis_change_events (as_of DESC);
CREATE INDEX IF NOT EXISTS idx_tce_kind
    ON thesis_change_events (event_kind, as_of DESC);

-- prev_status NULL doesn't dedupe in a plain UNIQUE — partial index so
-- a symbol can only start coverage once per day.
CREATE UNIQUE INDEX IF NOT EXISTS uq_tce_coverage_start
    ON thesis_change_events (symbol, as_of)
    WHERE event_kind = 'coverage_start';

-- Baseline anchor: symbols already tracked when this table shipped get
-- a coverage_start row at their current status — the timeline starts
-- non-empty instead of pretending history began today. detail.baseline
-- marks it as a backfill anchor, not a detected change.
INSERT INTO thesis_change_events (symbol, as_of, event_kind, archetype,
                                  prev_status, status, status_dir, score,
                                  hyp_changes, evidence, detail)
SELECT t.symbol, t.as_of, 'coverage_start', t.archetype, NULL,
       t.status, 'flat', t.score, '[]'::jsonb, '[]'::jsonb,
       jsonb_build_object('baseline', true)
FROM symbol_thesis t
WHERE NOT EXISTS (
    SELECT 1 FROM thesis_change_events e
    WHERE e.symbol = t.symbol AND e.event_kind = 'coverage_start');

-- Baseline anchor: symbols already tracked when this table shipped get
-- a coverage_start row at their current status — the timeline starts
-- non-empty instead of pretending history began today. detail.baseline
-- marks it as a backfill anchor, not a detected change.
INSERT INTO thesis_change_events (symbol, as_of, event_kind, archetype,
                                  prev_status, status, status_dir, score,
                                  hyp_changes, evidence, detail)
SELECT t.symbol, t.as_of, 'coverage_start', t.archetype, NULL,
       t.status, 'flat', t.score, '[]'::jsonb, '[]'::jsonb,
       jsonb_build_object('baseline', true)
FROM symbol_thesis t
WHERE NOT EXISTS (
    SELECT 1 FROM thesis_change_events e
    WHERE e.symbol = t.symbol AND e.event_kind = 'coverage_start');
