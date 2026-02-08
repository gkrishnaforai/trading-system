-- ========================================
-- STOCK GRADES SYSTEM - Data Source Independent
-- Migration: 007_stock_grades_system.sql
-- Follows SOLID principles: Single Responsibility, Data Source Abstraction
-- ========================================

-- Drop existing FMP-specific table if exists
DROP TABLE IF EXISTS fmp_stock_grades CASCADE;

-- Create data source agnostic stock_grades table
CREATE TABLE IF NOT EXISTS stock_grades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    grade_date DATE NOT NULL,
    grading_company VARCHAR(100) NOT NULL,
    previous_grade VARCHAR(20),
    new_grade VARCHAR(20) NOT NULL,
    action VARCHAR(20) NOT NULL CHECK (action IN ('upgrade', 'downgrade', 'maintain', 'initiate', 'suspend')),
    
    -- Data source tracking (for analytics, not business logic)
    data_source VARCHAR(50) DEFAULT 'unknown',
    source_id VARCHAR(100),  -- External system ID for deduplication
    
    -- Market context at time of grade
    price_at_grade DECIMAL(10,2),
    volume_at_grade BIGINT,
    market_cap_at_grade BIGINT,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    UNIQUE(symbol, grading_company, grade_date, data_source),
    CHECK (grade_date <= CURRENT_DATE)
);

-- Data source mapping table for vendor-agnostic processing
CREATE TABLE IF NOT EXISTS data_source_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_source VARCHAR(50) NOT NULL,
    external_field VARCHAR(100) NOT NULL,
    internal_field VARCHAR(100) NOT NULL,
    mapping_type VARCHAR(20) NOT NULL CHECK (mapping_type IN ('grade', 'action', 'company')),
    external_value VARCHAR(100),
    internal_value VARCHAR(100),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(data_source, external_field, external_value)
);

-- Firm ranking table for alert filtering
CREATE TABLE IF NOT EXISTS analyst_firm_rankings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firm_name VARCHAR(100) UNIQUE NOT NULL,
    ranking INTEGER NOT NULL,
    tier VARCHAR(20) NOT NULL CHECK (tier IN ('Tier 1', 'Tier 2', 'Tier 3', 'Tier 4')),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Grade change events for event sourcing and audit trail
CREATE TABLE IF NOT EXISTS grade_change_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_grade_id UUID NOT NULL REFERENCES stock_grades(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    
    -- Event details
    event_type VARCHAR(20) NOT NULL CHECK (event_type IN ('upgrade', 'downgrade', 'initiate', 'suspend', 'maintain')),
    grading_company VARCHAR(100) NOT NULL,
    previous_grade VARCHAR(20),
    new_grade VARCHAR(20) NOT NULL,
    grade_date DATE NOT NULL,
    
    -- Market context
    price_at_grade DECIMAL(10,2),
    volume_at_grade BIGINT,
    market_cap_at_grade BIGINT,
    
    -- Processing status
    alerts_processed BOOLEAN DEFAULT false,
    alerts_processed_at TIMESTAMPTZ,
    alerts_generated INTEGER DEFAULT 0,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default firm rankings
INSERT INTO analyst_firm_rankings (firm_name, ranking, tier) VALUES
('Goldman Sachs', 1, 'Tier 1'),
('Morgan Stanley', 2, 'Tier 1'),
('J.P. Morgan', 3, 'Tier 1'),
('Bank of America', 4, 'Tier 1'),
('Wells Fargo', 5, 'Tier 2'),
('Citigroup', 6, 'Tier 2'),
('UBS', 7, 'Tier 2'),
('Credit Suisse', 8, 'Tier 2'),
('Barclays', 9, 'Tier 3'),
('Deutsche Bank', 10, 'Tier 3')
ON CONFLICT (firm_name) DO NOTHING;

-- Insert default FMP mappings
INSERT INTO data_source_mappings (data_source, external_field, internal_field, mapping_type, external_value, internal_value) VALUES
('fmp', 'new_grade', 'new_grade', 'grade', 'Overweight', 'Buy'),
('fmp', 'new_grade', 'new_grade', 'grade', 'Underweight', 'Sell'),
('fmp', 'new_grade', 'new_grade', 'grade', 'Equal-Weight', 'Hold'),
('fmp', 'new_grade', 'new_grade', 'grade', 'Market Perform', 'Hold'),
('fmp', 'action', 'action', 'action', 'upgrade', 'upgrade'),
('fmp', 'action', 'action', 'action', 'downgrade', 'downgrade'),
('fmp', 'action', 'action', 'action', 'maintain', 'maintain'),
('fmp', 'grading_company', 'grading_company', 'company', 'Wells Fargo', 'Wells Fargo'),
('fmp', 'grading_company', 'grading_company', 'company', 'Goldman Sachs', 'Goldman Sachs'),
('fmp', 'grading_company', 'grading_company', 'company', 'Morgan Stanley', 'Morgan Stanley'),
('fmp', 'grading_company', 'grading_company', 'company', 'J.P. Morgan', 'J.P. Morgan'),
('fmp', 'grading_company', 'grading_company', 'company', 'Bank of America', 'Bank of America')
ON CONFLICT (data_source, external_field, external_value) DO NOTHING;

-- NOTE: Trigger functions are created separately in fix_trigger_functions.py
-- due to migration runner's SQL parsing limitations with multi-line functions

-- Comments for documentation
COMMENT ON TABLE stock_grades IS 'Data source agnostic stock grades table - single source of truth for analyst ratings';
COMMENT ON TABLE data_source_mappings IS 'Maps external data source values to internal standardized format';
COMMENT ON TABLE analyst_firm_rankings IS 'Ranking system for analyst firms to enable tier-based filtering';
COMMENT ON TABLE grade_change_events IS 'Event sourcing table for all grade changes - enables audit trail and replay';

COMMENT ON COLUMN stock_grades.symbol IS 'Foreign key to stocks.symbol - ensures data integrity';
COMMENT ON COLUMN stock_grades.data_source IS 'Tracks original data source for analytics, not business logic';
COMMENT ON COLUMN stock_grades.source_id IS 'External system ID for deduplication across data sources';
