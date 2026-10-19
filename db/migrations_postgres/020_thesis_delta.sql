-- 020 · thesis delta layer — status transitions + change evidence.
-- status_dir: 'new' | 'up' | 'down' | 'flat' (rank-compared vs the
-- prior nightly eval). hyp_changes: which legs moved (e.g.
-- unknown→on_track = a "want confirmed" item just confirmed).
-- status_since: day the current status started — age of the read.

ALTER TABLE symbol_thesis
    ADD COLUMN IF NOT EXISTS prev_status TEXT,
    ADD COLUMN IF NOT EXISTS status_dir TEXT,
    ADD COLUMN IF NOT EXISTS hyp_changes JSONB,
    ADD COLUMN IF NOT EXISTS status_since DATE,
    ADD COLUMN IF NOT EXISTS checked_at TIMESTAMPTZ;
