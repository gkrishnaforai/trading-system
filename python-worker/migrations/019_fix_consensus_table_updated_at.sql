-- Fix stock_grade_consensus table to add missing updated_at column
-- This fixes the trigger error: record "new" has no field "updated_at"

ALTER TABLE stock_grade_consensus 
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Create index on updated_at for better performance
CREATE INDEX IF NOT EXISTS idx_stock_grade_consensus_updated_at ON stock_grade_consensus(updated_at DESC);

-- Add comment
COMMENT ON COLUMN stock_grade_consensus.updated_at IS 'Last update timestamp for the consensus record';
