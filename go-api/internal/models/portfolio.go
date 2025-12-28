package models

import "time"

// Portfolio represents a user's portfolio
type Portfolio struct {
	PortfolioID   string    `json:"portfolio_id" db:"portfolio_id"`
	UserID        string    `json:"user_id" db:"user_id"`
	PortfolioName string    `json:"portfolio_name" db:"portfolio_name"`
	Notes         *string   `json:"notes,omitempty" db:"notes"`
	CreatedAt     time.Time `json:"created_at" db:"created_at"`
	UpdatedAt     time.Time `json:"updated_at" db:"updated_at"`
}

// Holding represents a position in a portfolio
type Holding struct {
	HoldingID      string    `json:"holding_id" db:"holding_id"`
	PortfolioID    string    `json:"portfolio_id" db:"portfolio_id"`
	StockSymbol    string    `json:"stock_symbol" db:"stock_symbol"`
	Quantity       float64   `json:"quantity" db:"quantity"`
	AvgEntryPrice  float64   `json:"avg_entry_price" db:"avg_entry_price"`
	PositionType   string    `json:"position_type" db:"position_type"`
	StrategyTag    *string   `json:"strategy_tag,omitempty" db:"strategy_tag"`
	Notes          *string   `json:"notes,omitempty" db:"notes"`
	PurchaseDate   time.Time `json:"purchase_date" db:"purchase_date"`
	CreatedAt      time.Time `json:"created_at" db:"created_at"`
	UpdatedAt      time.Time `json:"updated_at" db:"updated_at"`
}

