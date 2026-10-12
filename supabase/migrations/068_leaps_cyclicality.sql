-- 068: per-symbol cyclicality for the LEAPS cycle engine.
-- Cyclical names (memory/storage etc.) get full CALL→PUT→CALL
-- rotation; structural growers require fundamental deterioration
-- before a put is sanctioned. source: 'human' wins over 'agent';
-- 'seed' rows are the original hand-picked set.
CREATE TABLE IF NOT EXISTS leaps_cyclicality (
    symbol      text PRIMARY KEY,
    cyclical    boolean NOT NULL,
    source      text NOT NULL DEFAULT 'agent',  -- human|agent|seed
    confidence  text,                            -- high|medium|low
    rationale   text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- seed the known commodity-cycle names so they don't need an
-- agent call on first screen
INSERT INTO leaps_cyclicality (symbol, cyclical, source, confidence,
                               rationale)
VALUES ('MU',   true, 'seed', 'high', 'DRAM/NAND memory cycle'),
       ('SNDK', true, 'seed', 'high', 'NAND flash cycle'),
       ('STX',  true, 'seed', 'high', 'HDD storage cycle'),
       ('WDC',  true, 'seed', 'high', 'HDD/NAND storage cycle'),
       ('SIMO', true, 'seed', 'medium', 'NAND controller attach to flash cycle'),
       ('OLED', true, 'seed', 'medium', 'OLED materials capex cycle')
ON CONFLICT (symbol) DO NOTHING;
