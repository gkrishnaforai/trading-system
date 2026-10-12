-- Pattern priors — empirical hit-rates per symbol × tape-pattern.
-- The classifier is deterministic + stateless, so its history is
-- replayable over past bars: every prior occurrence of
-- (state, dip_phase) yields a forward 10d/20d return sample.
-- This is the "how did this setup work on THIS stock before" table —
-- the closest honest thing to prediction: priors, not forecasts.
CREATE TABLE IF NOT EXISTS pattern_priors (
    symbol          text NOT NULL,          -- symbol or '__ALL__' pooled
    pattern_key     text NOT NULL,          -- 'pullback|turning_up', 'evt:upgrade', ...
    n               int NOT NULL,           -- sample size (state-entry days)
    hit_rate_10d    double precision,       -- fraction with ret_10d > 0
    med_ret_10d     double precision,       -- median fwd return fraction
    med_ret_20d     double precision,
    med_mae         double precision,       -- median max-adverse-excursion
    computed_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, pattern_key)
);
CREATE INDEX IF NOT EXISTS pattern_priors_key_idx
    ON pattern_priors (pattern_key);
