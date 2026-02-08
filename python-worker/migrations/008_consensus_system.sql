-- ========================================
-- CONSENSUS SYSTEM - Market Consensus Tracking
-- Migration: 008_consensus_system.sql
-- Follows SOLID: Single Responsibility for consensus management
-- ========================================

-- Stock grade consensus summary (cached from data sources)
CREATE TABLE IF NOT EXISTS stock_grade_consensus (
    symbol VARCHAR(10) PRIMARY KEY REFERENCES stocks(symbol) ON DELETE CASCADE,
    
    -- Consensus data from external sources
    strong_buy INTEGER DEFAULT 0,
    buy INTEGER DEFAULT 0,
    hold INTEGER DEFAULT 0,
    sell INTEGER DEFAULT 0,
    strong_sell INTEGER DEFAULT 0,
    consensus_rating VARCHAR(20),
    
    -- Calculated fields (both reference base columns, not each other)
    total_analysts INTEGER GENERATED ALWAYS AS (
        strong_buy + buy + hold + sell + strong_sell
    ) STORED,
    consensus_score DECIMAL(3,1) GENERATED ALWAYS AS (
        (strong_buy * 2 + buy * 1 + hold * 0 + sell * -1 + strong_sell * -2)::DECIMAL / NULLIF(strong_buy + buy + hold + sell + strong_sell, 0)
    ) STORED,
    
    -- Metadata
    data_source VARCHAR(50) DEFAULT 'unknown',
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    last_checked TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CHECK (strong_buy >= 0 AND buy >= 0 AND hold >= 0 AND sell >= 0 AND strong_sell >= 0),
    CHECK (strong_buy + buy + hold + sell + strong_sell >= 0)
);

-- Track consensus rating changes over time (for alerts and analytics)
CREATE TABLE IF NOT EXISTS stock_consensus_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    
    -- Historical consensus snapshot
    strong_buy INTEGER,
    buy INTEGER,
    hold INTEGER,
    sell INTEGER,
    strong_sell INTEGER,
    consensus_rating VARCHAR(20),
    consensus_score DECIMAL(3,1),
    total_analysts INTEGER,
    
    -- Change tracking
    previous_consensus VARCHAR(20),
    consensus_change VARCHAR(20) CHECK (consensus_change IN ('upgrade', 'downgrade', 'maintain', 'initiate')),
    consensus_score_change DECIMAL(3,1),
    
    -- Significance assessment
    significance_level INTEGER CHECK (significance_level BETWEEN 1 AND 5),
    market_impact VARCHAR(20) CHECK (market_impact IN ('LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH')),
    
    -- Metadata
    data_source VARCHAR(50) DEFAULT 'unknown',
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Consensus change events for high-priority alerts
CREATE TABLE IF NOT EXISTS consensus_change_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consensus_history_id UUID NOT NULL REFERENCES stock_consensus_history(id) ON DELETE CASCADE,
    
    -- Event details
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    event_type VARCHAR(20) NOT NULL CHECK (event_type IN ('consensus_upgrade', 'consensus_downgrade', 'consensus_initiate')),
    previous_consensus VARCHAR(20),
    new_consensus VARCHAR(20),
    consensus_change VARCHAR(20) CHECK (consensus_change IN ('upgrade', 'downgrade', 'maintain', 'initiate')),
    
    -- Significance metrics
    consensus_score DECIMAL(3,1),
    previous_score DECIMAL(3,1),
    consensus_score_change DECIMAL(3,1),
    total_analysts INTEGER,
    previous_analysts INTEGER,
    analyst_count_change INTEGER,
    
    -- Impact assessment
    significance_level INTEGER CHECK (significance_level BETWEEN 1 AND 5),
    market_impact VARCHAR(20) CHECK (market_impact IN ('LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH')),
    
    -- Processing status
    alerts_triggered BOOLEAN DEFAULT false,
    alerts_triggered_at TIMESTAMPTZ,
    alerts_generated INTEGER DEFAULT 0,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_consensus_events_symbol_date ON consensus_change_events (symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_consensus_events_type ON consensus_change_events (event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_consensus_events_processed ON consensus_change_events (alerts_triggered, created_at DESC);

-- Consensus update schedule (for automated updates)
CREATE TABLE IF NOT EXISTS consensus_update_schedule (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    
    -- Schedule configuration
    update_frequency VARCHAR(20) NOT NULL CHECK (update_frequency IN ('real_time', 'hourly', 'daily', 'weekly')),
    last_update TIMESTAMPTZ,
    next_update TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT true,
    
    -- Update preferences
    min_analyst_threshold INTEGER DEFAULT 3,
    significant_change_only BOOLEAN DEFAULT true,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(symbol)
);

-- Create indexes for consensus_update_schedule table
CREATE INDEX IF NOT EXISTS idx_consensus_schedule_next_update ON consensus_update_schedule (next_update, is_active);
CREATE INDEX IF NOT EXISTS idx_consensus_schedule_frequency ON consensus_update_schedule (update_frequency, is_active);

-- NOTE: Trigger functions and triggers created separately in fix_trigger_functions.py
-- due to migration runner's SQL parsing limitations with multi-line functions
-- Run fix_trigger_functions.py first, then migrations

-- Insert default update schedules for major stocks
INSERT INTO consensus_update_schedule (symbol, update_frequency, next_update)
SELECT symbol, 'hourly', NOW() + INTERVAL '1 hour'
FROM stocks 
WHERE symbol IN ('AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META')
ON CONFLICT (symbol) DO NOTHING;

-- Comments for documentation
COMMENT ON TABLE stock_grade_consensus IS 'Cached consensus ratings from external data sources - single source of truth for current consensus';
COMMENT ON TABLE stock_consensus_history IS 'Historical consensus changes for analytics and trend analysis';
COMMENT ON TABLE consensus_change_events IS 'High-priority consensus change events for alert processing';
COMMENT ON TABLE consensus_update_schedule IS 'Automated update schedule for consensus data';

COMMENT ON COLUMN stock_grade_consensus.consensus_score IS 'Calculated consensus score: Strong Buy=+2, Buy=+1, Hold=0, Sell=-1, Strong Sell=-2';
COMMENT ON COLUMN stock_consensus_history.significance_level IS '1=minimal, 2=low, 3=moderate, 4=significant, 5=very significant change';
COMMENT ON COLUMN consensus_change_events.analyst_count_change IS 'Change in total number of analysts covering this stock';
