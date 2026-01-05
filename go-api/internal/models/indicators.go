package models

import "time"

// AggregatedIndicators represents technical indicators for a stock
type AggregatedIndicators struct {
	ID                int       `json:"id" db:"id"`
	StockID           string    `json:"stock_id,omitempty" db:"stock_id"`
	StockSymbol       string    `json:"stock_symbol" db:"-"`
	Date              time.Time `json:"date" db:"date"`
	MA7               *float64  `json:"ma7,omitempty" db:"ma7"`
	MA21              *float64  `json:"ma21,omitempty" db:"ma21"`
	SMA50             *float64  `json:"sma50,omitempty" db:"sma50"`
	EMA20             *float64  `json:"ema20,omitempty" db:"ema20"`
	EMA50             *float64  `json:"ema50,omitempty" db:"ema50"`
	SMA200            *float64  `json:"sma200,omitempty" db:"sma200"`
	ATR               *float64  `json:"atr,omitempty" db:"atr"`
	MACD              *float64  `json:"macd,omitempty" db:"macd"`
	MACDSignal        *float64  `json:"macd_signal,omitempty" db:"macd_signal"`
	MACDHistogram     *float64  `json:"macd_histogram,omitempty" db:"macd_histogram"`
	RSI               *float64  `json:"rsi,omitempty" db:"rsi"`
	BBUpper           *float64  `json:"bb_upper,omitempty" db:"bb_upper"`
	BBMiddle          *float64  `json:"bb_middle,omitempty" db:"bb_middle"`
	BBLower           *float64  `json:"bb_lower,omitempty" db:"bb_lower"`
	LongTermTrend     *string   `json:"long_term_trend,omitempty" db:"long_term_trend"`
	MediumTermTrend   *string   `json:"medium_term_trend,omitempty" db:"medium_term_trend"`
	Signal            *string   `json:"signal,omitempty" db:"signal"`
	PullbackZoneLower *float64  `json:"pullback_zone_lower,omitempty" db:"pullback_zone_lower"`
	PullbackZoneUpper *float64  `json:"pullback_zone_upper,omitempty" db:"pullback_zone_upper"`
	MomentumScore     *float64  `json:"momentum_score,omitempty" db:"momentum_score"`
	Volume            *int64    `json:"volume,omitempty" db:"volume"`
	VolumeMA          *float64  `json:"volume_ma,omitempty" db:"volume_ma"`
	Timestamp         time.Time `json:"timestamp" db:"timestamp"`
}

// PortfolioSignal represents a trading signal for a portfolio
type PortfolioSignal struct {
	SignalID                  string    `json:"signal_id" db:"signal_id"`
	PortfolioID               string    `json:"portfolio_id" db:"portfolio_id"`
	StockID                   string    `json:"stock_id,omitempty" db:"stock_id"`
	StockSymbol               string    `json:"stock_symbol" db:"-"`
	Date                      time.Time `json:"date" db:"date"`
	SignalType                string    `json:"signal_type" db:"signal_type"`
	SuggestedAllocation       *float64  `json:"suggested_allocation,omitempty" db:"suggested_allocation"`
	StopLoss                  *float64  `json:"stop_loss,omitempty" db:"stop_loss"`
	ConfidenceScore           *float64  `json:"confidence_score,omitempty" db:"confidence_score"`
	SubscriptionLevelRequired string    `json:"subscription_level_required" db:"subscription_level_required"`
	CreatedAt                 time.Time `json:"created_at" db:"created_at"`
}
