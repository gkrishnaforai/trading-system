-- Add interval + as_of_ts to indicators_daily to support both daily and intraday indicators in one table

BEGIN;

-- 1) Add new columns (default to daily interval)
ALTER TABLE indicators_daily
  ADD COLUMN IF NOT EXISTS interval TEXT NOT NULL DEFAULT '1d';

ALTER TABLE indicators_daily
  ADD COLUMN IF NOT EXISTS as_of_ts TIMESTAMPTZ;

-- 2) Backfill as_of_ts for existing daily rows
-- Use midnight UTC for now; later we can move to market close timestamp if desired.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'indicators_daily' AND column_name = 'trade_date'
  ) THEN
    EXECUTE $$
      UPDATE indicators_daily
      SET as_of_ts = (trade_date::timestamp AT TIME ZONE 'UTC')
      WHERE as_of_ts IS NULL
    $$;
  ELSIF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'indicators_daily' AND column_name = 'date'
  ) THEN
    EXECUTE $$
      UPDATE indicators_daily
      SET as_of_ts = (date::timestamp AT TIME ZONE 'UTC')
      WHERE as_of_ts IS NULL
    $$;
  ELSE
    RAISE EXCEPTION 'indicators_daily must have either trade_date or date column';
  END IF;
END $$;

-- 3) Replace primary key to include interval + as_of_ts
-- Drop old PK if present (name may vary)
DO $$
DECLARE
  pk_name text;
BEGIN
  SELECT conname
    INTO pk_name
  FROM pg_constraint
  WHERE conrelid = 'public.indicators_daily'::regclass
    AND contype = 'p'
  LIMIT 1;

  IF pk_name IS NOT NULL THEN
    EXECUTE format('ALTER TABLE indicators_daily DROP CONSTRAINT %I', pk_name);
  END IF;
END $$;

-- Ensure not-null now that backfill ran
ALTER TABLE indicators_daily
  ALTER COLUMN as_of_ts SET NOT NULL;

-- New PK supports multiple rows per day (intraday)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'indicators_daily' AND column_name = 'stock_symbol'
  ) THEN
    EXECUTE 'ALTER TABLE indicators_daily ADD CONSTRAINT indicators_daily_pkey PRIMARY KEY (stock_symbol, interval, as_of_ts)';
  ELSIF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'indicators_daily' AND column_name = 'symbol'
  ) THEN
    EXECUTE 'ALTER TABLE indicators_daily ADD CONSTRAINT indicators_daily_pkey PRIMARY KEY (symbol, interval, as_of_ts)';
  ELSE
    RAISE EXCEPTION 'indicators_daily must have either stock_symbol or symbol column';
  END IF;
END $$;

-- 4) Helpful indexes for common access patterns
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'indicators_daily' AND column_name = 'stock_symbol'
  ) THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS idx_indicators_daily_symbol_interval_asof ON indicators_daily(stock_symbol, interval, as_of_ts DESC)';
  ELSIF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'indicators_daily' AND column_name = 'symbol'
  ) THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS idx_indicators_daily_symbol_interval_asof ON indicators_daily(symbol, interval, as_of_ts DESC)';
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'indicators_daily' AND column_name = 'stock_symbol'
  ) AND EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'indicators_daily' AND column_name = 'trade_date'
  ) THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS idx_indicators_daily_symbol_trade_date ON indicators_daily(stock_symbol, trade_date DESC)';
  ELSIF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'indicators_daily' AND column_name = 'symbol'
  ) AND EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'indicators_daily' AND column_name = 'date'
  ) THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS idx_indicators_daily_symbol_trade_date ON indicators_daily(symbol, date DESC)';
  END IF;
END $$;

COMMIT;
