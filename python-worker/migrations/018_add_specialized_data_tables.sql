-- Add specialized data tables for short interest, short volume, and share float
-- Migration 018: Specialized Data Tables

-- Short Interest Data Table
CREATE TABLE IF NOT EXISTS short_interest (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    short_interest BIGINT NOT NULL,
    short_ratio DECIMAL(10, 4),
    days_to_cover DECIMAL(10, 2),
    short_interest_change BIGINT,
    short_interest_change_percent DECIMAL(10, 4),
    report_date DATE NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_source VARCHAR(50) DEFAULT 'fmp',
    
    CONSTRAINT unique_short_interest_symbol_date UNIQUE (symbol, report_date)
);

-- Short Volume Data Table
CREATE TABLE IF NOT EXISTS short_volume (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    short_volume BIGINT NOT NULL,
    total_volume BIGINT NOT NULL,
    short_volume_percent DECIMAL(10, 4),
    short_exempt_volume BIGINT DEFAULT 0,
    report_date DATE NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_source VARCHAR(50) DEFAULT 'fmp',
    
    CONSTRAINT unique_short_volume_symbol_date UNIQUE (symbol, report_date)
);

-- Share Float Data Table
CREATE TABLE IF NOT EXISTS share_float (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    shares_outstanding BIGINT NOT NULL,
    shares_float BIGINT NOT NULL,
    shares_authorized BIGINT,
    shares_restricted BIGINT DEFAULT 0,
    float_percent DECIMAL(10, 4),
    insider_holding_percent DECIMAL(10, 4),
    institutional_holding_percent DECIMAL(10, 4),
    report_date DATE NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_source VARCHAR(50) DEFAULT 'fmp',
    
    CONSTRAINT unique_share_float_symbol_date UNIQUE (symbol, report_date)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_short_interest_symbol_date ON short_interest(symbol, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_short_interest_symbol ON short_interest(symbol);
CREATE INDEX IF NOT EXISTS idx_short_interest_report_date ON short_interest(report_date DESC);

CREATE INDEX IF NOT EXISTS idx_short_volume_symbol_date ON short_volume(symbol, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_short_volume_symbol ON short_volume(symbol);
CREATE INDEX IF NOT EXISTS idx_short_volume_report_date ON short_volume(report_date DESC);

CREATE INDEX IF NOT EXISTS idx_share_float_symbol_date ON share_float(symbol, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_share_float_symbol ON share_float(symbol);
CREATE INDEX IF NOT EXISTS idx_share_float_report_date ON share_float(report_date DESC);

-- Add comments for documentation
COMMENT ON TABLE short_interest IS 'Short interest data including short ratio and days to cover';
COMMENT ON TABLE short_volume IS 'Short volume data including total volume and short volume percentage';
COMMENT ON TABLE share_float IS 'Share float data including shares outstanding and float information';

COMMENT ON COLUMN short_interest.short_ratio IS 'Short interest divided by average daily share volume';
COMMENT ON COLUMN short_interest.days_to_cover IS 'Number of days needed to cover all short positions';
COMMENT ON COLUMN short_volume.short_volume_percent IS 'Short volume divided by total volume';
COMMENT ON COLUMN share_float.float_percent IS 'Shares float divided by shares outstanding';
COMMENT ON COLUMN share_float.insider_holding_percent IS 'Percentage held by insiders';
COMMENT ON COLUMN share_float.institutional_holding_percent IS 'Percentage held by institutions';

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_short_interest_updated_at BEFORE UPDATE ON short_interest
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_short_volume_updated_at BEFORE UPDATE ON short_volume
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_share_float_updated_at BEFORE UPDATE ON share_float
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
