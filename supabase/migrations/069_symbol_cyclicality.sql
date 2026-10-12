-- 069: promote cyclicality to a first-class symbol property on the
-- `stocks` master table — the base every engine reads. Cyclical names
-- (memory/storage, commodities, shipping, autos) get cycle-rotation
-- logic in LEAPS and cycle-aware interpretation in research; structural
-- growers require fundamental deterioration before counter-trend
-- trades. source: 'human' always wins over 'agent'; 'seed' rows are
-- the hand-picked commodity-cycle set.
ALTER TABLE stocks
    ADD COLUMN IF NOT EXISTS cyclical              boolean,
    ADD COLUMN IF NOT EXISTS cyclical_source       varchar(10),
    ADD COLUMN IF NOT EXISTS cyclical_confidence   varchar(10),
    ADD COLUMN IF NOT EXISTS cyclical_rationale    text,
    ADD COLUMN IF NOT EXISTS cyclical_updated_at   timestamptz;

CREATE INDEX IF NOT EXISTS idx_stocks_cyclical
    ON stocks (cyclical) WHERE cyclical IS NOT NULL;

-- migrate the LEAPS-era table, then drop it
INSERT INTO stocks (symbol, cyclical, cyclical_source,
                    cyclical_confidence, cyclical_rationale,
                    cyclical_updated_at)
SELECT symbol, cyclical, source, confidence, rationale, updated_at
FROM leaps_cyclicality
ON CONFLICT (symbol) DO UPDATE SET
    cyclical             = EXCLUDED.cyclical,
    cyclical_source      = EXCLUDED.cyclical_source,
    cyclical_confidence  = EXCLUDED.cyclical_confidence,
    cyclical_rationale   = EXCLUDED.cyclical_rationale,
    cyclical_updated_at  = EXCLUDED.cyclical_updated_at;

DROP TABLE IF EXISTS leaps_cyclicality;
