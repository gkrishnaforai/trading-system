-- Extended-hours sessions — post-market and pre-market share the same
-- table; session distinguishes the two boards for the same day.

ALTER TABLE afterhours_moves
    ADD COLUMN IF NOT EXISTS session text NOT NULL DEFAULT 'post';

ALTER TABLE afterhours_moves DROP CONSTRAINT IF EXISTS afterhours_moves_pkey;
ALTER TABLE afterhours_moves
    ADD PRIMARY KEY (symbol, as_of_date, session);
