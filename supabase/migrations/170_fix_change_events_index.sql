-- 170: restore the unique index fundamentals_change_events lost in the
-- 136-drop/161-restore cycle. The upsert's ON CONFLICT (stock_symbol,
-- as_of_date, event_type, event_key) has been erroring since — every
-- insert failed, so dedupe is belt-and-suspenders before the index.

SELECT pg_advisory_xact_lock(715170);

-- keep the newest row per conflict key, drop older dupes
DELETE FROM fundamentals_change_events a
USING fundamentals_change_events b
WHERE a.stock_symbol = b.stock_symbol
  AND a.as_of_date  = b.as_of_date
  AND a.event_type  = b.event_type
  AND a.event_key   = b.event_key
  AND a.id < b.id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_fundamentals_change_events_symbol_asof_type_key
ON fundamentals_change_events(stock_symbol, as_of_date, event_type, event_key);

CREATE INDEX IF NOT EXISTS idx_fundamentals_change_events_symbol_created
ON fundamentals_change_events(stock_symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_fundamentals_change_events_symbol_asof
ON fundamentals_change_events(stock_symbol, as_of_date DESC);
