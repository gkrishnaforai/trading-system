package models

import "time"

// Portfolio represents a user's portfolio
type Portfolio struct {
	ID           string    `json:"id" db:"id"`
	UserID       string    `json:"user_id" db:"user_id"`
	Name         string    `json:"name" db:"name"`
	BaseCurrency *string   `json:"base_currency,omitempty" db:"base_currency"`
	IsDefault    bool      `json:"is_default" db:"is_default"`
	IsArchived   bool      `json:"is_archived" db:"is_archived"`
	CreatedAt    time.Time `json:"created_at" db:"created_at"`
	UpdatedAt    time.Time `json:"updated_at" db:"updated_at"`
}

// PortfolioPosition represents a position in a portfolio.
// Storage is normalized by stock_id, but APIs still commonly use symbol.
type PortfolioPosition struct {
	ID          string     `json:"id" db:"id"`
	PortfolioID string     `json:"portfolio_id" db:"portfolio_id"`
	StockID     string     `json:"stock_id" db:"stock_id"`
	Symbol      string     `json:"symbol" db:"symbol"`
	Quantity    float64    `json:"quantity" db:"quantity"`
	AvgPrice    float64    `json:"avg_price" db:"avg_price"`
	OpenedAt    *time.Time `json:"opened_at,omitempty" db:"opened_at"`
	CreatedAt   time.Time  `json:"created_at" db:"created_at"`
	UpdatedAt   time.Time  `json:"updated_at" db:"updated_at"`

	// Read-only projections from symbol_fair_values (latest fair_value_v2_runs
	// per symbol). Nil when no fair-value run exists for the symbol yet.
	FairValue       *float64   `json:"fair_value,omitempty"`
	FairValueRegime *string    `json:"fair_value_regime,omitempty"`
	FairValueAsOf   *time.Time `json:"fair_value_as_of,omitempty"`
	FairValueBear   *float64   `json:"fair_value_bear,omitempty"`
	FairValueBull   *float64   `json:"fair_value_bull,omitempty"`
}
