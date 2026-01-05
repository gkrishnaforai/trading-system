package repositories

import (
	"database/sql"
	"encoding/json"
	"fmt"

	"github.com/trading-system/go-api/internal/database"
)

type MarketDataRepository struct {
	db *sql.DB
}

func (r *MarketDataRepository) GetLatestFundamentalsSnapshot(symbol string) (map[string]interface{}, error) {
	query := `
        SELECT payload
        FROM fundamentals_snapshots
        WHERE stock_symbol = $1
        ORDER BY as_of_date DESC
        LIMIT 1
    `

	var payloadBytes []byte
	err := r.db.QueryRow(query, symbol).Scan(&payloadBytes)
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("fundamentals not found for symbol: %s", symbol)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get fundamentals: %w", err)
	}

	if len(payloadBytes) == 0 {
		return nil, fmt.Errorf("fundamentals not found for symbol: %s", symbol)
	}

	var payload map[string]interface{}
	if err := json.Unmarshal(payloadBytes, &payload); err != nil {
		return nil, fmt.Errorf("failed to parse fundamentals payload: %w", err)
	}

	return payload, nil
}

func NewMarketDataRepository() *MarketDataRepository {
	return &MarketDataRepository{
		db: database.DB,
	}
}

type FundamentalData struct {
	MarketCap       *float64 `json:"market_cap"`
	PERatio         *float64 `json:"pe_ratio"`
	ForwardPE       *float64 `json:"forward_pe"`
	DividendYield   *float64 `json:"dividend_yield"`
	EPS             *float64 `json:"eps"`
	Revenue         *float64 `json:"revenue"`
	ProfitMargin    *float64 `json:"profit_margin"`
	DebtToEquity    *float64 `json:"debt_to_equity"`
	CurrentRatio    *float64 `json:"current_ratio"`
	Sector          *string  `json:"sector"`
	Industry        *string  `json:"industry"`
	EnterpriseValue *float64 `json:"enterprise_value"`
	BookValue       *float64 `json:"book_value"`
	PriceToBook     *float64 `json:"price_to_book"`
	PEGRatio        *float64 `json:"peg_ratio"`
	RevenueGrowth   *float64 `json:"revenue_growth"`
	EarningsGrowth  *float64 `json:"earnings_growth"`
}

type NewsArticle struct {
	Title          string   `json:"title"`
	Publisher      string   `json:"publisher"`
	Link           string   `json:"link"`
	PublishedDate  string   `json:"published_date"`
	RelatedSymbols []string `json:"related_symbols"`
}

type EarningsData struct {
	EarningsDate       string   `json:"earnings_date"`
	EPSEstimate        *float64 `json:"eps_estimate"`
	EPSActual          *float64 `json:"eps_actual"`
	RevenueEstimate    *float64 `json:"revenue_estimate"`
	RevenueActual      *float64 `json:"revenue_actual"`
	SurprisePercentage *float64 `json:"surprise_percentage"`
}

type IndustryPeer struct {
	Symbol    string   `json:"symbol"`
	Name      string   `json:"name"`
	MarketCap *float64 `json:"market_cap"`
	Sector    *string  `json:"sector"`
	Industry  *string  `json:"industry"`
}

type IndustryPeersData struct {
	Sector   *string        `json:"sector"`
	Industry *string        `json:"industry"`
	Peers    []IndustryPeer `json:"peers"`
}

func (r *MarketDataRepository) GetLatestFundamentals(symbol string) (*FundamentalData, error) {
	// Normalized schema stores core company metadata on stocks; richer fundamentals are in stock_financials.
	// For now we populate what we can from stocks and return the rest as nil.
	query := `
		SELECT market_cap, sector, industry
		FROM stocks
		WHERE symbol = $1
		LIMIT 1
	`

	var marketCap sql.NullInt64
	var sector sql.NullString
	var industry sql.NullString
	err := r.db.QueryRow(query, symbol).Scan(&marketCap, &sector, &industry)
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("fundamentals not found for symbol: %s", symbol)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get fundamentals: %w", err)
	}

	fd := &FundamentalData{}
	if marketCap.Valid {
		v := float64(marketCap.Int64)
		fd.MarketCap = &v
	}
	if sector.Valid {
		fd.Sector = &sector.String
	}
	if industry.Valid {
		fd.Industry = &industry.String
	}
	return fd, nil
}

func (r *MarketDataRepository) GetLatestNews(symbol string, limit int) ([]NewsArticle, error) {
	if limit <= 0 {
		limit = 10
	}

	query := `
		SELECT n.title, COALESCE(n.publisher, ''), COALESCE(n.url, ''), COALESCE(n.published_at::text, ''), n.related_symbols
		FROM stock_news n
		JOIN stocks s ON s.id = n.stock_id
		WHERE s.symbol = $1
		ORDER BY n.published_at DESC NULLS LAST, n.created_at DESC
		LIMIT $2
	`

	rows, err := r.db.Query(query, symbol, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to get news: %w", err)
	}
	defer rows.Close()

	articles := make([]NewsArticle, 0)
	for rows.Next() {
		var a NewsArticle
		var related sql.NullString
		if err := rows.Scan(&a.Title, &a.Publisher, &a.Link, &a.PublishedDate, &related); err != nil {
			continue
		}
		// related_symbols is stored as JSONB; treat as opaque when scanning via database/sql.
		// We keep RelatedSymbols empty for now.
		a.RelatedSymbols = []string{}
		articles = append(articles, a)
	}

	return articles, nil
}

func (r *MarketDataRepository) GetEarnings(symbol string, limit int) ([]EarningsData, error) {
	// Earnings is not yet modeled in the normalized baseline.
	return []EarningsData{}, nil
}

func (r *MarketDataRepository) GetIndustryPeers(symbol string) (*IndustryPeersData, error) {
	// Industry peers is not yet modeled in the normalized baseline.
	// We return sector/industry if available from stocks table, but no peers.
	fundamentals, err := r.GetLatestFundamentals(symbol)
	if err != nil {
		return &IndustryPeersData{Peers: []IndustryPeer{}}, nil
	}
	return &IndustryPeersData{Sector: fundamentals.Sector, Industry: fundamentals.Industry, Peers: []IndustryPeer{}}, nil
}

type VolumeDataPoint struct {
	Date   string  `json:"date"`
	Volume int64   `json:"volume"`
	Price  float64 `json:"price"`
}

func (r *MarketDataRepository) GetVolumeData(symbol string, days int) ([]VolumeDataPoint, error) {
	if days <= 0 {
		days = 30
	}
	query := `
		SELECT m.date::text, COALESCE(m.volume, 0) as volume, COALESCE(m.close_price, 0) as close
		FROM stock_market_metrics m
		JOIN stocks s ON s.id = m.stock_id
		WHERE s.symbol = $1
		ORDER BY m.date DESC
		LIMIT $2
	`

	rows, err := r.db.Query(query, symbol, days)
	if err != nil {
		return nil, fmt.Errorf("failed to query volume data: %w", err)
	}
	defer rows.Close()

	var volumeData []VolumeDataPoint
	for rows.Next() {
		var v VolumeDataPoint
		var d string
		err := rows.Scan(&d, &v.Volume, &v.Price)
		if err != nil {
			continue
		}
		v.Date = d
		volumeData = append(volumeData, v)
	}

	// Reverse to get chronological order
	for i, j := 0, len(volumeData)-1; i < j; i, j = i+1, j-1 {
		volumeData[i], volumeData[j] = volumeData[j], volumeData[i]
	}

	return volumeData, nil
}
