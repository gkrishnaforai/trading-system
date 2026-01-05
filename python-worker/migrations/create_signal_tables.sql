-- Create signal engine tables
-- Migration for signal system architecture

-- Main signals table
CREATE TABLE IF NOT EXISTS stock_signals_snapshots (
    id SERIAL PRIMARY KEY,
    stock_symbol VARCHAR(10) NOT NULL,
    signal_date DATE NOT NULL,
    engine_name VARCHAR(50) NOT NULL,
    
    -- Signal data
    signal VARCHAR(10) NOT NULL,  -- BUY/HOLD/SELL
    confidence FLOAT NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    position_size_pct FLOAT NOT NULL,
    timeframe VARCHAR(20) NOT NULL,  -- swing/position/day
    
    -- Entry/exit levels
    entry_price_range JSONB,  -- [low, high] or null
    stop_loss FLOAT,
    take_profit JSONB,  -- [target1, target2, ...]
    
    -- Aggregated data (for 'aggregated' engine)
    consensus_signal VARCHAR(10),
    consensus_confidence FLOAT,
    recommended_engine VARCHAR(50),
    conflicts JSONB,
    
    -- Reasoning and metadata
    reasoning JSONB NOT NULL,
    metadata JSONB,
    
    -- Timestamps
    generated_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Constraints
    UNIQUE(stock_symbol, signal_date, engine_name),
    CONSTRAINT fk_signal_symbol FOREIGN KEY (stock_symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
);

-- Screener cache table
CREATE TABLE IF NOT EXISTS signal_screener_cache (
    id SERIAL PRIMARY KEY,
    screener_name VARCHAR(100) NOT NULL,
    stock_symbol VARCHAR(10) NOT NULL,
    
    -- Screener criteria
    signal VARCHAR(10) NOT NULL,
    confidence FLOAT NOT NULL,
    engine VARCHAR(50) NOT NULL,
    timeframe VARCHAR(20) NOT NULL,
    
    -- Sorting/ranking
    rank_score FLOAT NOT NULL DEFAULT 0.0,
    sector VARCHAR(50),
    market_cap BIGINT,
    
    -- Snapshot metadata
    snapshot_date DATE NOT NULL,
    generated_at TIMESTAMP DEFAULT NOW(),
    
    -- Constraints
    UNIQUE(screener_name, stock_symbol, snapshot_date),
    CONSTRAINT fk_screener_symbol FOREIGN KEY (stock_symbol) REFERENCES stocks(symbol) ON DELETE CASCADE
);

-- Blog content metadata table
CREATE TABLE IF NOT EXISTS blog_content_metadata (
    id SERIAL PRIMARY KEY,
    stock_symbol VARCHAR(10),
    blog_tier VARCHAR(10) NOT NULL CHECK (blog_tier IN ('BASIC', 'PRO', 'ELITE')),
    
    -- Content
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    summary TEXT,
    full_content TEXT NOT NULL,
    
    -- Signal context
    signal VARCHAR(10),
    confidence FLOAT,
    engines_used JSONB,
    
    -- Engagement metrics
    publish_date DATE NOT NULL,
    view_count INTEGER DEFAULT 0,
    conversion_count INTEGER DEFAULT 0,
    
    -- SEO data
    meta_description TEXT,
    keywords TEXT[],
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    CONSTRAINT fk_blog_symbol FOREIGN KEY (stock_symbol) REFERENCES stocks(symbol) ON DELETE SET NULL
);

-- Macro market data table
CREATE TABLE IF NOT EXISTS macro_market_data (
    id SERIAL PRIMARY KEY,
    data_date DATE NOT NULL UNIQUE,
    
    -- Indices
    nasdaq_close FLOAT,
    nasdaq_sma50 FLOAT,
    nasdaq_sma200 FLOAT,
    sp500_close FLOAT,
    
    -- Volatility
    vix_close FLOAT,
    vix_sma10 FLOAT,
    
    -- Rates
    fed_funds_rate FLOAT,
    treasury_10y FLOAT,
    treasury_2y FLOAT,
    yield_curve_spread FLOAT,  -- 10Y - 2Y
    
    -- Breadth
    sp500_above_50d_pct FLOAT,
    sp500_above_200d_pct FLOAT,
    advance_decline_line FLOAT,
    new_highs INTEGER,
    new_lows INTEGER,
    
    -- Futures (pre-market)
    es_futures_close FLOAT,
    nq_futures_close FLOAT,
    
    created_at TIMESTAMP DEFAULT NOW()
);

-- Sector benchmarks table
CREATE TABLE IF NOT EXISTS sector_benchmarks (
    id SERIAL PRIMARY KEY,
    sector_name VARCHAR(50) NOT NULL UNIQUE,
    
    -- Margin benchmarks
    margin_min FLOAT NOT NULL,
    margin_median FLOAT NOT NULL,
    margin_excellent FLOAT NOT NULL,
    
    -- Valuation benchmarks
    pe_low FLOAT NOT NULL,
    pe_median FLOAT NOT NULL,
    pe_high FLOAT NOT NULL,
    
    -- Growth benchmarks
    growth_min FLOAT NOT NULL,
    growth_strong FLOAT NOT NULL,
    
    -- Feature weights
    margin_weight FLOAT NOT NULL DEFAULT 0.3,
    growth_weight FLOAT NOT NULL DEFAULT 0.4,
    valuation_weight FLOAT NOT NULL DEFAULT 0.3,
    
    -- Metadata
    last_updated DATE DEFAULT CURRENT_DATE,
    data_source VARCHAR(100) DEFAULT 'manual',
    
    CONSTRAINT positive_margin CHECK (margin_min >= 0 AND margin_median > margin_min AND margin_excellent > margin_median),
    CONSTRAINT positive_pe CHECK (pe_low > 0 AND pe_median > pe_low AND pe_high > pe_median),
    CONSTRAINT positive_growth CHECK (growth_min >= 0 AND growth_strong > growth_min),
    CONSTRAINT valid_weights CHECK (margin_weight + growth_weight + valuation_weight = 1.0)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_signals_symbol_date ON stock_signals_snapshots(stock_symbol, signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_consensus ON stock_signals_snapshots(consensus_signal, consensus_confidence);
CREATE INDEX IF NOT EXISTS idx_signals_engine_date ON stock_signals_snapshots(engine_name, signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_confidence ON stock_signals_snapshots(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_signals_timeframe ON stock_signals_snapshots(timeframe, signal_date DESC);

CREATE INDEX IF NOT EXISTS idx_screener_name_date ON signal_screener_cache(screener_name, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_rank ON signal_screener_cache(screener_name, rank_score DESC);
CREATE INDEX IF NOT EXISTS idx_screener_signal ON signal_screener_cache(signal, confidence DESC);

CREATE INDEX IF NOT EXISTS idx_blog_tier_date ON blog_content_metadata(blog_tier, publish_date DESC);
CREATE INDEX IF NOT EXISTS idx_blog_slug ON blog_content_metadata(slug);
CREATE INDEX IF NOT EXISTS idx_blog_symbol ON blog_content_metadata(stock_symbol, publish_date DESC);

CREATE INDEX IF NOT EXISTS idx_macro_date ON macro_market_data(data_date DESC);

-- Insert default sector benchmarks
INSERT INTO sector_benchmarks (
    sector_name, margin_min, margin_median, margin_excellent,
    pe_low, pe_median, pe_high,
    growth_min, growth_strong,
    margin_weight, growth_weight, valuation_weight
) VALUES
    ('technology-software', 0.15, 0.22, 0.30, 20, 35, 60, 0.15, 0.40, 0.3, 0.4, 0.3),
    ('technology-semiconductors', 0.20, 0.28, 0.35, 15, 22, 30, 0.10, 0.30, 0.4, 0.3, 0.3),
    ('finance', 0.25, 0.35, 0.45, 8, 12, 18, 0.05, 0.15, 0.5, 0.2, 0.3),
    ('retail', 0.03, 0.07, 0.12, 10, 16, 25, 0.05, 0.20, 0.3, 0.4, 0.3),
    ('healthcare', 0.10, 0.18, 0.28, 15, 25, 40, 0.08, 0.25, 0.3, 0.4, 0.3),
    ('energy', 0.05, 0.12, 0.20, 8, 15, 25, 0.00, 0.15, 0.4, 0.2, 0.4),
    ('industrial', 0.08, 0.15, 0.25, 12, 18, 28, 0.05, 0.20, 0.3, 0.3, 0.4),
    ('utilities', 0.20, 0.30, 0.40, 10, 15, 20, 0.02, 0.08, 0.4, 0.2, 0.4)
ON CONFLICT (sector_name) DO NOTHING;

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
CREATE TRIGGER update_stock_signals_updated_at BEFORE UPDATE ON stock_signals_snapshots 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_blog_content_updated_at BEFORE UPDATE ON blog_content_metadata 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create view for latest signals per symbol
CREATE OR REPLACE VIEW latest_signals AS
SELECT DISTINCT ON (stock_symbol, engine_name)
    stock_symbol,
    engine_name,
    signal,
    confidence,
    position_size_pct,
    timeframe,
    reasoning,
    generated_at
FROM stock_signals_snapshots
ORDER BY stock_symbol, engine_name, signal_date DESC, generated_at DESC;

-- Create view for consensus signals
CREATE OR REPLACE VIEW consensus_signals AS
SELECT 
    stock_symbol,
    consensus_signal,
    consensus_confidence,
    recommended_engine,
    reasoning,
    generated_at
FROM stock_signals_snapshots
WHERE engine_name = 'aggregated'
ORDER BY consensus_confidence DESC;
