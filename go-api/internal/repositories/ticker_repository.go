package repositories

import (
	"database/sql"
	"fmt"
	"strings"

	"github.com/trading-system/go-api/internal/database"
)

type TickerRepository struct {
	db *sql.DB
}

func NewTickerRepository() *TickerRepository {
	return &TickerRepository{
		db: database.DB,
	}
}

type Ticker struct {
	Symbol      string  `json:"symbol"`
	CompanyName *string `json:"company_name"`
	Exchange    *string `json:"exchange"`
	Sector      *string `json:"sector"`
	Industry    *string `json:"industry"`
	Country     *string `json:"country"`
	Currency    *string `json:"currency"`
	MarketCap   *int64  `json:"market_cap"`
	IsActive    *bool   `json:"is_active"`
	// Live price fields (from market_data_daily)
	CurrentPrice *float64 `json:"current_price"`
	DayChange    *float64 `json:"day_change"`
	DayChangePct *float64 `json:"day_change_pct"`
	// Optional fields (may be null)
	PERatio          *float64 `json:"pe_ratio"`
	PBRatio          *float64 `json:"pb_ratio"`
	EPS              *float64 `json:"eps"`
	DividendYield    *float64 `json:"dividend_yield"`
	Beta             *float64 `json:"beta"`
	Description      *string  `json:"description"`
	FiftyTwoWeekHigh *float64 `json:"fifty_two_week_high"`
	FiftyTwoWeekLow  *float64 `json:"fifty_two_week_low"`
	AverageVolume    *int64   `json:"average_volume"`
	EnterpriseValue  *int64   `json:"enterprise_value"`
	PriceToSales     *float64 `json:"price_to_sales"`
	ForwardPE        *float64 `json:"forward_pe"`
	PEGRatio         *float64 `json:"peg_ratio"`
	ProfitMargin     *float64 `json:"profit_margin"`
	CurrentRatio     *float64 `json:"current_ratio"`
	DebtToEquity     *float64 `json:"debt_to_equity"`
	ROE              *float64 `json:"roe"`
	ROA              *float64 `json:"roa"`
	RevenueGrowth    *float64 `json:"revenue_growth"`
	EarningsGrowth   *float64 `json:"earnings_growth"`
}

// SearchTickers searches for tickers by symbol or company name (ILIKE), returns up to limit rows (no price for performance)
func (r *TickerRepository) SearchTickers(query string, limit int) ([]Ticker, error) {
	if limit <= 0 {
		limit = 20
	}
	// Normalize query: strip spaces and ensure we have something to search
	query = strings.TrimSpace(query)
	if query == "" {
		return []Ticker{}, nil
	}
	// Use ILIKE on symbol and company_name; order by symbol match first
	sqlQuery := `
		SELECT 
			s.symbol, s.company_name, s.exchange, s.sector, s.industry, s.country, s.currency, s.market_cap, s.is_active,
			NULL, NULL, NULL,
			NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
		FROM stocks s
		WHERE (s.symbol ILIKE $1 OR s.company_name ILIKE $1)
		ORDER BY 
			CASE WHEN s.symbol ILIKE $2 THEN 1 ELSE 2 END,
			s.symbol ASC
		LIMIT $3
	`
	// Prepare patterns: prefix and contains
	prefixPattern := query + "%"
	containsPattern := "%" + query + "%"

	rows, err := r.db.Query(sqlQuery, containsPattern, prefixPattern, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to search tickers: %w", err)
	}
	defer rows.Close()

	var tickers []Ticker
	for rows.Next() {
		var t Ticker
		err := rows.Scan(
			&t.Symbol, &t.CompanyName, &t.Exchange, &t.Sector, &t.Industry, &t.Country, &t.Currency, &t.MarketCap, &t.IsActive,
			&t.CurrentPrice, &t.DayChange, &t.DayChangePct,
			&t.PERatio, &t.PBRatio, &t.EPS, &t.DividendYield, &t.Beta, &t.Description,
			&t.FiftyTwoWeekHigh, &t.FiftyTwoWeekLow, &t.AverageVolume, &t.EnterpriseValue,
			&t.PriceToSales, &t.ForwardPE, &t.PEGRatio, &t.ProfitMargin, &t.CurrentRatio,
			&t.DebtToEquity, &t.ROE, &t.ROA, &t.RevenueGrowth, &t.EarningsGrowth,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan ticker row: %w", err)
		}
		tickers = append(tickers, t)
	}
	if err = rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating ticker rows: %w", err)
	}
	return tickers, nil
}

// GetTickerBySymbol returns a single ticker by exact symbol match (no price for MVP)
func (r *TickerRepository) GetTickerBySymbol(symbol string) (*Ticker, error) {
	sqlQuery := `
		SELECT 
			s.symbol, s.company_name, s.exchange, s.sector, s.industry, s.country, s.currency, s.market_cap, s.is_active,
			NULL, NULL, NULL,
			NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
		FROM stocks s
		WHERE s.symbol = $1
		LIMIT 1
	`
	var t Ticker
	err := r.db.QueryRow(sqlQuery, strings.ToUpper(symbol)).Scan(
		&t.Symbol, &t.CompanyName, &t.Exchange, &t.Sector, &t.Industry, &t.Country, &t.Currency, &t.MarketCap, &t.IsActive,
		&t.CurrentPrice, &t.DayChange, &t.DayChangePct,
		&t.PERatio, &t.PBRatio, &t.EPS, &t.DividendYield, &t.Beta, &t.Description,
		&t.FiftyTwoWeekHigh, &t.FiftyTwoWeekLow, &t.AverageVolume, &t.EnterpriseValue,
		&t.PriceToSales, &t.ForwardPE, &t.PEGRatio, &t.ProfitMargin, &t.CurrentRatio,
		&t.DebtToEquity, &t.ROE, &t.ROA, &t.RevenueGrowth, &t.EarningsGrowth,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("ticker not found for symbol: %s", symbol)
		}
		return nil, fmt.Errorf("failed to get ticker: %w", err)
	}
	return &t, nil
}
