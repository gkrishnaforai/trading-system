package models

import "time"

// Watchlist represents a user's watchlist
type Watchlist struct {
	WatchlistID            string    `json:"watchlist_id" db:"watchlist_id"`
	UserID                 string    `json:"user_id" db:"user_id"`
	WatchlistName          string    `json:"watchlist_name" db:"watchlist_name"`
	Description            *string   `json:"description,omitempty" db:"description"`
	Tags                   *string   `json:"tags,omitempty" db:"tags"`
	IsDefault              bool      `json:"is_default" db:"is_default"`
	SubscriptionLevelRequired string `json:"subscription_level_required" db:"subscription_level_required"`
	CreatedAt              time.Time `json:"created_at" db:"created_at"`
	UpdatedAt              time.Time `json:"updated_at" db:"updated_at"`
}

// WatchlistItem represents a stock/ETF in a watchlist
type WatchlistItem struct {
	ItemID       string    `json:"item_id" db:"item_id"`
	WatchlistID  string    `json:"watchlist_id" db:"watchlist_id"`
	StockSymbol  string    `json:"stock_symbol" db:"stock_symbol"`
	AddedAt      time.Time `json:"added_at" db:"added_at"`
	Notes        *string   `json:"notes,omitempty" db:"notes"`
	Priority     int       `json:"priority" db:"priority"`
	Tags         *string   `json:"tags,omitempty" db:"tags"`
	AlertConfig  *string   `json:"alert_config,omitempty" db:"alert_config"`
}

// WatchlistWithItems represents a watchlist with its items and stock data
type WatchlistWithItems struct {
	Watchlist Watchlist        `json:"watchlist"`
	Items     []WatchlistItemWithData `json:"items"`
	Analytics *WatchlistAnalytics `json:"analytics,omitempty"`
}

// WatchlistItemWithData represents a watchlist item with current stock data
type WatchlistItemWithData struct {
	WatchlistItem
	CurrentPrice    *float64 `json:"current_price,omitempty"`
	DailyChange     *float64 `json:"daily_change,omitempty"`
	DailyChangePercent *float64 `json:"daily_change_percent,omitempty"`
	Trend            *string  `json:"trend,omitempty"` // "bullish", "bearish", "neutral"
	RiskScore        *string  `json:"risk_score,omitempty"` // "low", "medium", "high"
	EarningsDate     *string  `json:"earnings_date,omitempty"`
	Signal           *string  `json:"signal,omitempty"` // "buy", "sell", "hold"
	TrendStrength    *float64 `json:"trend_strength,omitempty"` // 0-100
	Volatility       *float64 `json:"volatility,omitempty"`
}

// WatchlistAnalytics represents watchlist-level analytics
type WatchlistAnalytics struct {
	TotalStocks      int     `json:"total_stocks"`
	AvgTrendScore    float64 `json:"avg_trend_score"`
	AvgRiskScore     float64 `json:"avg_risk_score"`
	BullishCount     int     `json:"bullish_count"`
	BearishCount     int     `json:"bearish_count"`
	NeutralCount     int     `json:"neutral_count"`
	HighRiskCount    int     `json:"high_risk_count"`
	MediumRiskCount  int     `json:"medium_risk_count"`
	LowRiskCount     int     `json:"low_risk_count"`
	SectorDistribution map[string]int `json:"sector_distribution"`
}

// MoveToPortfolioRequest represents a request to move stock from watchlist to portfolio
type MoveToPortfolioRequest struct {
	PortfolioID    string  `json:"portfolio_id" binding:"required"`
	Quantity       float64 `json:"quantity" binding:"required"`
	AvgEntryPrice  float64 `json:"avg_entry_price" binding:"required"`
	PositionType   string  `json:"position_type" binding:"required"`
	StrategyTag    *string `json:"strategy_tag,omitempty"`
	PurchaseDate   string  `json:"purchase_date" binding:"required"` // YYYY-MM-DD
	Notes          *string `json:"notes,omitempty"`
}

