-- 108_tailwinds_review.sql — weekly re-grade support.
-- review() periodically asks whether each journaled channel still
-- plausibly moves revenue (analyst-style: live | noise | dead) and
-- stamps reviewed_at. 'noise' status = real news but no plausible
-- revenue path (kept for audit, excluded from card/bonus).

ALTER TABLE tailwinds ADD COLUMN IF NOT EXISTS reviewed_at timestamptz;
ALTER TABLE tailwinds ADD COLUMN IF NOT EXISTS review_note text;
