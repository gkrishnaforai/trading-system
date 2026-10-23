-- 036_lev_positions.sql (db-tree mirror of supabase 152) — position ledger + spec-version registry
-- for the 3x-semis swing detector.
--
-- lev_etf_positions: deterministic paper positions. The detector
-- opens a 'system' row on every actionable trigger and manages it
-- per the spec's exit contract (T1/T2 partials, breakeven->T1
-- trail, invalidation, time stop). realized_r IS the grading ledger
-- — the answer to 'does the complete entry/exit system pay'.
-- 'manual' source rows can track the user's real fills later.
--
-- lev_spec_versions: one row per spec version seen — the learning
-- lab's substrate. Journal + positions carry rules_version; join
-- them here to grade which POLICY ITERATION produced the outcomes.

SELECT pg_advisory_xact_lock(715152);

CREATE TABLE IF NOT EXISTS lev_spec_versions (
    version     TEXT PRIMARY KEY,          -- lev_swings.v1.4
    spec        JSONB NOT NULL,            -- full YAML snapshot
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lev_etf_positions (
    id           BIGSERIAL PRIMARY KEY,
    etf          TEXT        NOT NULL,     -- SOXS | SOXL
    source       TEXT        NOT NULL DEFAULT 'system', -- system|manual
    opened_as_of DATE        NOT NULL,
    entry_px     NUMERIC(12,2) NOT NULL,
    stop_px      NUMERIC(12,2) NOT NULL,
    trail_stop   NUMERIC(12,2),            -- ratcheted protective stop
    t1_px        NUMERIC(12,2),            -- 1.5R partial level
    t2_px        NUMERIC(12,2),            -- 2R partial level
    risk_px      NUMERIC(12,2) NOT NULL,   -- entry - stop
    shares       INTEGER,
    risk_usd     NUMERIC(14,2),
    idx_entry    NUMERIC(12,2),            -- index close at open
    idx_stop     NUMERIC(12,2),            -- index invalidation level
    high_water   NUMERIC(12,2),            -- best ETF px seen (trail)
    partials     INTEGER     NOT NULL DEFAULT 0,
    bars_held    INTEGER     NOT NULL DEFAULT 0,
    banked_r     NUMERIC(8,3) NOT NULL DEFAULT 0,
    state        TEXT        NOT NULL DEFAULT 'open',
    closed_as_of DATE,
    exit_px      NUMERIC(12,2),
    exit_reason  TEXT,                     -- stop|t2|time_stop|thesis|manual
    realized_r   NUMERIC(8,3),
    pnl          NUMERIC(14,2),
    spec         TEXT,                     -- rules_version at open
    notes        JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS lev_etf_pos_open_idx
    ON lev_etf_positions (etf, state);
