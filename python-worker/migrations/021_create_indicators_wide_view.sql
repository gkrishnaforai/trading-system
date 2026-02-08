-- Create indicators_wide_view to maintain backward compatibility
-- This view aggregates narrow rows back to wide format for existing queries

CREATE OR REPLACE VIEW indicators_wide_view AS
SELECT 
    symbol,
    date,
    MAX(CASE WHEN indicator_name = 'sma_50' THEN indicator_value END) as sma_50,
    MAX(CASE WHEN indicator_name = 'sma_200' THEN indicator_value END) as sma_200,
    MAX(CASE WHEN indicator_name = 'ema_20' THEN indicator_value END) as ema_20,
    MAX(CASE WHEN indicator_name = 'rsi_14' THEN indicator_value END) as rsi_14,
    MAX(CASE WHEN indicator_name = 'macd' THEN indicator_value END) as macd,
    MAX(CASE WHEN indicator_name = 'macd_signal' THEN indicator_value END) as macd_signal,
    MAX(CASE WHEN indicator_name = 'macd_hist' THEN indicator_value END) as macd_hist,
    MAX(CASE WHEN indicator_name = 'atr' THEN indicator_value END) as atr,
    MAX(CASE WHEN indicator_name = 'bb_width' THEN indicator_value END) as bb_width,
    MAX(CASE WHEN indicator_name = 'signal' THEN indicator_value END) as signal,
    MAX(CASE WHEN indicator_name = 'confidence_score' THEN indicator_value END) as confidence_score,
    MAX(data_source) as data_source,
    MAX(created_at) as created_at
FROM indicators_daily
GROUP BY symbol, date;

-- Create indexes for the view
CREATE INDEX IF NOT EXISTS idx_indicators_wide_view_symbol_date ON indicators_wide_view(symbol, date);

-- Add comment
COMMENT ON VIEW indicators_wide_view IS 'Wide format view of indicators_daily for backward compatibility with existing queries';
