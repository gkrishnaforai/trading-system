-- Fix workflow tables schema issues
-- Add missing columns and fix column names

-- Add updated_at to workflow_stage_executions (missing from migration 016)
ALTER TABLE workflow_stage_executions ADD COLUMN updated_at TIMESTAMP;

-- Update existing rows to set updated_at
UPDATE workflow_stage_executions SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL;

-- Fix data_fetch_audit: Add timestamp column alias (some code might use 'timestamp' instead of 'fetch_timestamp')
-- Note: fetch_timestamp is the correct column name, but we'll ensure compatibility
-- The column already exists as fetch_timestamp, so we just need to make sure queries use the right name

