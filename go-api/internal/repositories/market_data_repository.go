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
	Title         string   `json:"title"`
	Publisher     string   `json:"publisher"`
	Link          string   `json:"link"`
	PublishedDate string   `json:"published_date"`
	RelatedSymbols []string `json:"related_symbols"`
}

type EarningsData struct {
	EarningsDate   string   `json:"earnings_date"`
	EPSEstimate    *float64 `json:"eps_estimate"`
	EPSActual      *float64 `json:"eps_actual"`
	RevenueEstimate *float64 `json:"revenue_estimate"`
	RevenueActual  *float64 `json:"revenue_actual"`
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
	Sector *string        `json:"sector"`
	Industry *string      `json:"industry"`
	Peers  []IndustryPeer `json:"peers"`
}

func (r *MarketDataRepository) GetLatestFundamentals(symbol string) (*FundamentalData, error) {
	query := `
		SELECT fundamental_data
		FROM raw_market_data
		WHERE stock_symbol = ?
		AND fundamental_data IS NOT NULL
		ORDER BY date DESC
		LIMIT 1
	`

	var fundamentalJSON sql.NullString
	err := r.db.QueryRow(query, symbol).Scan(&fundamentalJSON)
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("fundamentals not found for symbol: %s", symbol)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get fundamentals: %w", err)
	}

	if !fundamentalJSON.Valid {
		return nil, fmt.Errorf("no fundamental data available")
	}

	var fundamental FundamentalData
	if err := json.Unmarshal([]byte(fundamentalJSON.String), &fundamental); err != nil {
		return nil, fmt.Errorf("failed to parse fundamental data: %w", err)
	}

	return &fundamental, nil
}

func (r *MarketDataRepository) GetLatestNews(symbol string, limit int) ([]NewsArticle, error) {
	query := `
		SELECT news_metadata
		FROM raw_market_data
		WHERE stock_symbol = ?
		AND news_metadata IS NOT NULL
		ORDER BY date DESC
		LIMIT 1
	`

	var newsJSON sql.NullString
	err := r.db.QueryRow(query, symbol).Scan(&newsJSON)
	if err == sql.ErrNoRows {
		return []NewsArticle{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get news: %w", err)
	}

	if !newsJSON.Valid {
		return []NewsArticle{}, nil
	}

	var news []NewsArticle
	if err := json.Unmarshal([]byte(newsJSON.String), &news); err != nil {
		return nil, fmt.Errorf("failed to parse news data: %w", err)
	}

	// Limit results
	if len(news) > limit {
		news = news[:limit]
	}

	return news, nil
}

func (r *MarketDataRepository) GetEarnings(symbol string, limit int) ([]EarningsData, error) {
	query := `
		SELECT earnings_date, eps_estimate, eps_actual, revenue_estimate, revenue_actual, surprise_percentage
		FROM earnings_data
		WHERE stock_symbol = ?
		ORDER BY earnings_date DESC
		LIMIT ?
	`

	rows, err := r.db.Query(query, symbol, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to query earnings: %w", err)
	}
	defer rows.Close()

	var earnings []EarningsData
	for rows.Next() {
		var e EarningsData
		var epsEst, epsAct, revEst, revAct, surprise sql.NullFloat64
		err := rows.Scan(&e.EarningsDate, &epsEst, &epsAct, &revEst, &revAct, &surprise)
		if err != nil {
			continue
		}
		if epsEst.Valid {
			e.EPSEstimate = &epsEst.Float64
		}
		if epsAct.Valid {
			e.EPSActual = &epsAct.Float64
		}
		if revEst.Valid {
			e.RevenueEstimate = &revEst.Float64
		}
		if revAct.Valid {
			e.RevenueActual = &revAct.Float64
		}
		if surprise.Valid {
			e.SurprisePercentage = &surprise.Float64
		}
		earnings = append(earnings, e)
	}

	return earnings, nil
}

func (r *MarketDataRepository) GetIndustryPeers(symbol string) (*IndustryPeersData, error) {
	// First get sector/industry from fundamentals
	fundamentals, err := r.GetLatestFundamentals(symbol)
	if err == nil && fundamentals.Sector != nil && fundamentals.Industry != nil {
		// Get peers from industry_peers table
		query := `
			SELECT peer_symbol, peer_name, peer_market_cap, sector, industry
			FROM industry_peers
			WHERE stock_symbol = ?
			ORDER BY peer_market_cap DESC
			LIMIT 10
		`

		rows, err := r.db.Query(query, symbol)
		if err != nil {
			return &IndustryPeersData{
				Sector:   fundamentals.Sector,
				Industry: fundamentals.Industry,
				Peers:   []IndustryPeer{},
			}, nil
		}
		defer rows.Close()

		var peers []IndustryPeer
		for rows.Next() {
			var p IndustryPeer
			var marketCap sql.NullFloat64
			var sector, industry sql.NullString
			err := rows.Scan(&p.Symbol, &p.Name, &marketCap, &sector, &industry)
			if err != nil {
				continue
			}
			if marketCap.Valid {
				p.MarketCap = &marketCap.Float64
			}
			if sector.Valid {
				p.Sector = &sector.String
			}
			if industry.Valid {
				p.Industry = &industry.String
			}
			peers = append(peers, p)
		}

		return &IndustryPeersData{
			Sector:   fundamentals.Sector,
			Industry: fundamentals.Industry,
			Peers:   peers,
		}, nil
	}

	// Fallback: try to get from fundamental_data JSON
	query := `
		SELECT fundamental_data
		FROM raw_market_data
		WHERE stock_symbol = ?
		AND fundamental_data IS NOT NULL
		ORDER BY date DESC
		LIMIT 1
	`

	var fundamentalJSON sql.NullString
	err = r.db.QueryRow(query, symbol).Scan(&fundamentalJSON)
	if err == sql.ErrNoRows || !fundamentalJSON.Valid {
		return &IndustryPeersData{}, nil
	}

	var fundamentalMap map[string]interface{}
	if err := json.Unmarshal([]byte(fundamentalJSON.String), &fundamentalMap); err != nil {
		return &IndustryPeersData{}, nil
	}

	result := &IndustryPeersData{}
	if sector, ok := fundamentalMap["sector"].(string); ok {
		result.Sector = &sector
	}
	if industry, ok := fundamentalMap["industry"].(string); ok {
		result.Industry = &industry
	}
	if peersData, ok := fundamentalMap["industry_peers"].(map[string]interface{}); ok {
		if peersList, ok := peersData["peers"].([]interface{}); ok {
			for _, p := range peersList {
				if peerMap, ok := p.(map[string]interface{}); ok {
					peer := IndustryPeer{}
					if symbol, ok := peerMap["symbol"].(string); ok {
						peer.Symbol = symbol
					}
					if name, ok := peerMap["name"].(string); ok {
						peer.Name = name
					}
					if marketCap, ok := peerMap["market_cap"].(float64); ok {
						peer.MarketCap = &marketCap
					}
					result.Peers = append(result.Peers, peer)
				}
			}
		}
	}

	return result, nil
}

type VolumeDataPoint struct {
	Date   string  `json:"date"`
	Volume int64   `json:"volume"`
	Price  float64 `json:"price"`
}

func (r *MarketDataRepository) GetVolumeData(symbol string, days int) ([]VolumeDataPoint, error) {
	query := `
		SELECT date, volume, close
		FROM raw_market_data
		WHERE stock_symbol = ?
		ORDER BY date DESC
		LIMIT ?
	`

	rows, err := r.db.Query(query, symbol, days)
	if err != nil {
		return nil, fmt.Errorf("failed to query volume data: %w", err)
	}
	defer rows.Close()

	var volumeData []VolumeDataPoint
	for rows.Next() {
		var v VolumeDataPoint
		var date string
		err := rows.Scan(&date, &v.Volume, &v.Price)
		if err != nil {
			continue
		}
		v.Date = date
		volumeData = append(volumeData, v)
	}

	// Reverse to get chronological order
	for i, j := 0, len(volumeData)-1; i < j; i, j = i+1, j-1 {
		volumeData[i], volumeData[j] = volumeData[j], volumeData[i]
	}

	return volumeData, nil
}

