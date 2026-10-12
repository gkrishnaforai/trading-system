-- 076: Fundamental health flag — the fundamental-axis counterpart to
-- momentum_state (which is the tape axis). Distilled from the flywheel
-- metrics we already compute (rev/eps growth + accel, margin slope,
-- beat streak, estimate revisions, fwd P/E) into one canonical state:
--   accelerating | growing | slowing | declining | deteriorating
--   cyclical | watch | unknown
-- plus a separate risk level and an alert level derived from what
-- CHANGED vs the previous snapshot — so screens can show not just
-- "how is this company" but "did it get better or worse this week."

ALTER TABLE stocks
    ADD COLUMN IF NOT EXISTS fundamental_state      VARCHAR(20),
    ADD COLUMN IF NOT EXISTS fundamental_risk       VARCHAR(12),
    ADD COLUMN IF NOT EXISTS fundamental_detail     JSONB,
    ADD COLUMN IF NOT EXISTS fundamental_updated_at TIMESTAMPTZ;

-- per-refresh snapshot — the diff source for "what changed" + alert level
CREATE TABLE IF NOT EXISTS fundamental_snapshots (
    symbol          VARCHAR(10) NOT NULL,
    as_of           DATE NOT NULL,
    state           VARCHAR(20),
    risk            VARCHAR(12),
    metrics         JSONB,          -- rev_growth, rev_accel, eps_growth,
                                    -- eps_accel, gm_now, gm_slope,
                                    -- beat_streak, est_revision_pct, fwd_pe
    PRIMARY KEY (symbol, as_of)
);

CREATE INDEX IF NOT EXISTS stocks_fund_state ON stocks(fundamental_state);
