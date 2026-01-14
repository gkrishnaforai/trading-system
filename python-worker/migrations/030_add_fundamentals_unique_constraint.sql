-- Add unique constraint to fundamentals_snapshots for ON CONFLICT operations
-- This fixes the error: "there is no unique or exclusion constraint matching the ON CONFLICT specification"

-- Add unique constraint on (symbol, as_of_date) for fundamentals_snapshots
ALTER TABLE fundamentals_snapshots 
ADD CONSTRAINT fundamentals_snapshots_symbol_date_unique 
UNIQUE (symbol, as_of_date);

-- Add index for better performance (regular CREATE INDEX, not CONCURRENTLY)
CREATE INDEX IF NOT EXISTS idx_fundamentals_snapshots_symbol_as_of_date 
ON fundamentals_snapshots (symbol, as_of_date);
