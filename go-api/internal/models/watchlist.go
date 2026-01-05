package models

import "time"

// Watchlist represents a user's watchlist
type Watchlist struct {
	ID          string    `json:"id" db:"id"`
	UserID      string    `json:"user_id" db:"user_id"`
	Name        string    `json:"name" db:"name"`
	Description *string   `json:"description,omitempty" db:"description"`
	IsDefault   bool      `json:"is_default" db:"is_default"`
	IsArchived  bool      `json:"is_archived" db:"is_archived"`
	CreatedAt   time.Time `json:"created_at" db:"created_at"`
	UpdatedAt   time.Time `json:"updated_at" db:"updated_at"`
}

// WatchlistStock represents a stock in a watchlist.
// Storage is normalized by stock_id; symbol is joined for API responses.
type WatchlistStock struct {
	ID          string    `json:"id" db:"id"`
	WatchlistID string    `json:"watchlist_id" db:"watchlist_id"`
	StockID     string    `json:"stock_id" db:"stock_id"`
	Symbol      string    `json:"symbol" db:"symbol"`
	AddedAt     time.Time `json:"added_at" db:"added_at"`
	CreatedAt   time.Time `json:"created_at" db:"created_at"`
	UpdatedAt   time.Time `json:"updated_at" db:"updated_at"`
}

// WatchlistWithItems represents a watchlist with its items and stock data
type WatchlistWithItems struct {
	Watchlist Watchlist                `json:"watchlist"`
	Items     []WatchlistStockWithData `json:"items"`
	Analytics *WatchlistAnalytics      `json:"analytics,omitempty"`
}

// WatchlistStockWithData represents a watchlist stock with current stock data
type WatchlistStockWithData struct {
	WatchlistStock
	CurrentPrice       *float64 `json:"current_price,omitempty"`
	DailyChange        *float64 `json:"daily_change,omitempty"`
	DailyChangePercent *float64 `json:"daily_change_percent,omitempty"`
	Trend              *string  `json:"trend,omitempty"`      // "bullish", "bearish", "neutral"
	RiskScore          *string  `json:"risk_score,omitempty"` // "low", "medium", "high"
	EarningsDate       *string  `json:"earnings_date,omitempty"`
	Signal             *string  `json:"signal,omitempty"`         // "buy", "sell", "hold"
	TrendStrength      *float64 `json:"trend_strength,omitempty"` // 0-100
	Volatility         *float64 `json:"volatility,omitempty"`
}

// WatchlistAnalytics represents watchlist-level analytics
type WatchlistAnalytics struct {
	TotalStocks        int            `json:"total_stocks"`
	AvgTrendScore      float64        `json:"avg_trend_score"`
	AvgRiskScore       float64        `json:"avg_risk_score"`
	BullishCount       int            `json:"bullish_count"`
	BearishCount       int            `json:"bearish_count"`
	NeutralCount       int            `json:"neutral_count"`
	HighRiskCount      int            `json:"high_risk_count"`
	MediumRiskCount    int            `json:"medium_risk_count"`
	LowRiskCount       int            `json:"low_risk_count"`
	SectorDistribution map[string]int `json:"sector_distribution"`
}

// MoveToPortfolioRequest represents a request to move stock from watchlist to portfolio
type MoveToPortfolioRequest struct {
	PortfolioID   string  `json:"portfolio_id" binding:"required"`
	Quantity      float64 `json:"quantity" binding:"required"`
	AvgEntryPrice float64 `json:"avg_entry_price" binding:"required"`
	PositionType  string  `json:"position_type" binding:"required"`
	StrategyTag   *string `json:"strategy_tag,omitempty"`
	PurchaseDate  string  `json:"purchase_date" binding:"required"` // YYYY-MM-DD
	Notes         *string `json:"notes,omitempty"`
}
