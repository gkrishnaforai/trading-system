-- Create missing tables for data summary API
-- These tables are expected to exist but may be missing

-- Earnings Transcripts Table
CREATE TABLE IF NOT EXISTS earnings_transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL,
    transcript_date DATE NOT NULL,
    transcript_year INTEGER NOT NULL,
    quarter VARCHAR(2),
    content TEXT,
    transcript_text TEXT,
    content_type VARCHAR(50) DEFAULT 'text',
    source VARCHAR(50) DEFAULT 'fmp',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, transcript_date, quarter)
);

-- Indexes for earnings_transcripts
CREATE INDEX IF NOT EXISTS idx_earnings_transcripts_symbol ON earnings_transcripts(symbol);
CREATE INDEX IF NOT EXISTS idx_earnings_transcripts_date ON earnings_transcripts(transcript_date);
CREATE INDEX IF NOT EXISTS idx_earnings_transcripts_symbol_date ON earnings_transcripts(symbol, transcript_date);

-- Short Interest Table
CREATE TABLE IF NOT EXISTS short_interest (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL,
    short_interest_date DATE NOT NULL,
    short_interest BIGINT,
    short_percent FLOAT,
    days_to_cover FLOAT,
    avg_daily_share_volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, short_interest_date)
);

-- Indexes for short_interest
CREATE INDEX IF NOT EXISTS idx_short_interest_symbol ON short_interest(symbol);
CREATE INDEX IF NOT EXISTS idx_short_interest_date ON short_interest(short_interest_date);
CREATE INDEX IF NOT EXISTS idx_short_interest_symbol_date ON short_interest(symbol, short_interest_date);

-- Short Volume Table
CREATE TABLE IF NOT EXISTS short_volume (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL,
    short_volume_date DATE NOT NULL,
    short_volume BIGINT,
    total_volume BIGINT,
    short_volume_percent FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, short_volume_date)
);

-- Indexes for short_volume
CREATE INDEX IF NOT EXISTS idx_short_volume_symbol ON short_volume(symbol);
CREATE INDEX IF NOT EXISTS idx_short_volume_date ON short_volume(short_volume_date);
CREATE INDEX IF NOT EXISTS idx_short_volume_symbol_date ON short_volume(symbol, short_volume_date);

-- Share Float Table
CREATE TABLE IF NOT EXISTS share_float (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL,
    float_date DATE NOT NULL,
    shares_outstanding BIGINT,
    share_float BIGINT,
    float_percent FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, float_date)
);

-- Indexes for share_float
CREATE INDEX IF NOT EXISTS idx_share_float_symbol ON share_float(symbol);
CREATE INDEX IF NOT EXISTS idx_share_float_date ON share_float(float_date);
CREATE INDEX IF NOT EXISTS idx_share_float_symbol_date ON share_float(symbol, float_date);

-- Risk Factors Table
CREATE TABLE IF NOT EXISTS risk_factors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL,
    risk_date DATE NOT NULL,
    beta FLOAT,
    volatility FLOAT,
    sharpe_ratio FLOAT,
    max_drawdown FLOAT,
    var_95 FLOAT,
    risk_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, risk_date)
);

-- Indexes for risk_factors
CREATE INDEX IF NOT EXISTS idx_risk_factors_symbol ON risk_factors(symbol);
CREATE INDEX IF NOT EXISTS idx_risk_factors_date ON risk_factors(risk_date);
CREATE INDEX IF NOT EXISTS idx_risk_factors_symbol_date ON risk_factors(symbol, risk_date);

-- Comments
COMMENT ON TABLE earnings_transcripts IS 'Earnings call transcripts for analysis';
COMMENT ON TABLE short_interest IS 'Short interest data for securities';
COMMENT ON TABLE short_volume IS 'Short volume data for securities';
COMMENT ON TABLE share_float IS 'Share float and outstanding shares data';
COMMENT ON TABLE risk_factors IS 'Risk metrics and factors for securities';
