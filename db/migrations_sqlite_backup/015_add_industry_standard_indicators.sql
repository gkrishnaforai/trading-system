-- Add industry-standard moving averages and crossover flags
-- Based on what traders and institutions actually use

-- Add SMA100 (intermediate trend)
ALTER TABLE aggregated_indicators ADD COLUMN sma100 REAL;

-- Add EMA pairs for entry timing
ALTER TABLE aggregated_indicators ADD COLUMN ema12 REAL;  -- MACD base
ALTER TABLE aggregated_indicators ADD COLUMN ema26 REAL;  -- MACD base

-- Add crossover flags (industry standard)
ALTER TABLE aggregated_indicators ADD COLUMN ema9_above_ema21 BOOLEAN DEFAULT 0;  -- Fast momentum
ALTER TABLE aggregated_indicators ADD COLUMN ema20_above_ema50 BOOLEAN DEFAULT 0;  -- Swing trend
ALTER TABLE aggregated_indicators ADD COLUMN ema12_above_ema26 BOOLEAN DEFAULT 0;  -- MACD base
ALTER TABLE aggregated_indicators ADD COLUMN sma50_above_sma200 BOOLEAN DEFAULT 0;  -- Golden Cross
ALTER TABLE aggregated_indicators ADD COLUMN price_above_sma200 BOOLEAN DEFAULT 0;  -- Long-term bullish bias

-- Add RSI zones (industry standard interpretation)
ALTER TABLE aggregated_indicators ADD COLUMN rsi_zone TEXT CHECK(rsi_zone IN ('oversold', 'weak', 'healthy', 'overbought'));

-- Add volume confirmation flags
ALTER TABLE aggregated_indicators ADD COLUMN volume_above_average BOOLEAN DEFAULT 0;
ALTER TABLE aggregated_indicators ADD COLUMN volume_spike BOOLEAN DEFAULT 0;  -- Volume > 1.5x average

-- Add MACD momentum flags
ALTER TABLE aggregated_indicators ADD COLUMN macd_above_signal BOOLEAN DEFAULT 0;
ALTER TABLE aggregated_indicators ADD COLUMN macd_histogram_positive BOOLEAN DEFAULT 0;

-- Add price structure flags (higher highs, higher lows)
ALTER TABLE aggregated_indicators ADD COLUMN higher_highs BOOLEAN DEFAULT 0;
ALTER TABLE aggregated_indicators ADD COLUMN higher_lows BOOLEAN DEFAULT 0;

-- Create indexes for fast screening
CREATE INDEX IF NOT EXISTS idx_screener_price_above_200 ON aggregated_indicators(price_above_sma200, date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_golden_cross ON aggregated_indicators(sma50_above_sma200, date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_ema20_above_50 ON aggregated_indicators(ema20_above_ema50, date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_rsi_zone ON aggregated_indicators(rsi_zone, date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_volume_confirmed ON aggregated_indicators(volume_above_average, date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_macd_bullish ON aggregated_indicators(macd_above_signal, macd_histogram_positive, date DESC);

-- Composite index for best-practice buy signal
CREATE INDEX IF NOT EXISTS idx_screener_best_practice_buy ON aggregated_indicators(
    price_above_sma200,
    sma50_above_sma200,
    ema20_above_ema50,
    macd_above_signal,
    rsi_zone,
    volume_above_average,
    date DESC
);

