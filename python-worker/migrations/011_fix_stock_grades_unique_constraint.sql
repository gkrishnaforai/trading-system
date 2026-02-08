-- Fix stock grades unique constraint to prevent duplicates
-- Migration: 011_fix_stock_grades_unique_constraint.sql

-- Drop existing unique constraint
ALTER TABLE stock_grades DROP CONSTRAINT IF EXISTS stock_grades_symbol_grading_company_grade_date_data_source_source_id_key;

-- Add new unique constraint without source_id (since it's often NULL)
ALTER TABLE stock_grades ADD CONSTRAINT stock_grades_unique_grading 
UNIQUE(symbol, grading_company, grade_date, data_source);

-- Clean up existing duplicates by keeping the most recent record
WITH ranked_grades AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY symbol, grading_company, grade_date, data_source 
               ORDER BY created_at DESC, updated_at DESC
           ) as rn
    FROM stock_grades
)
DELETE FROM stock_grades 
WHERE id IN (SELECT id FROM ranked_grades WHERE rn > 1);

COMMENT ON CONSTRAINT stock_grades_unique_grading ON stock_grades IS 
'Prevents duplicate analyst grades for the same symbol, company, date, and data source';
