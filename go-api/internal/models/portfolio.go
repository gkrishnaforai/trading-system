package models

import "time"

// Portfolio represents a user's portfolio
type Portfolio struct {
	ID            string    `json:"id" db:"id"`
	UserID        string    `json:"user_id" db:"user_id"`
	Name          string    `json:"name" db:"name"`
	BaseCurrency  *string   `json:"base_currency,omitempty" db:"base_currency"`
	IsDefault     bool      `json:"is_default" db:"is_default"`
	IsArchived    bool      `json:"is_archived" db:"is_archived"`
	CreatedAt     time.Time `json:"created_at" db:"created_at"`
	UpdatedAt     time.Time `json:"updated_at" db:"updated_at"`
}

// PortfolioPosition represents a position in a portfolio.
// Storage is normalized by stock_id, but APIs still commonly use symbol.
type PortfolioPosition struct {
	ID           string     `json:"id" db:"id"`
	PortfolioID  string     `json:"portfolio_id" db:"portfolio_id"`
	StockID      string     `json:"stock_id" db:"stock_id"`
	Symbol       string     `json:"symbol" db:"symbol"`
	Quantity     float64    `json:"quantity" db:"quantity"`
	AvgPrice     float64    `json:"avg_price" db:"avg_price"`
	OpenedAt     *time.Time `json:"opened_at,omitempty" db:"opened_at"`
	CreatedAt    time.Time  `json:"created_at" db:"created_at"`
	UpdatedAt    time.Time  `json:"updated_at" db:"updated_at"`
}
