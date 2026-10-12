-- Trajectory + business-quality legs on the flywheel.
--   surprise_trend   slope of recent beats (newest - oldest), not just streak
--   rev_breadth_30d  was computed in _estimates but never persisted
--   roic / roe       annual key-metrics — the standalone Business Quality leg
ALTER TABLE symbol_flywheel
    ADD COLUMN IF NOT EXISTS surprise_trend  double precision,
    ADD COLUMN IF NOT EXISTS rev_breadth_30d double precision,
    ADD COLUMN IF NOT EXISTS roic            double precision,
    ADD COLUMN IF NOT EXISTS roe             double precision;
