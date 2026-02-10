-- Fix upsert contract: ON CONFLICT (stock_id, engine_name) requires a unique/exclusion constraint

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'uq_stock_signals_stock_engine'
  ) THEN
    ALTER TABLE stock_signals
      ADD CONSTRAINT uq_stock_signals_stock_engine UNIQUE (stock_id, engine_name);
  END IF;
END $$;
