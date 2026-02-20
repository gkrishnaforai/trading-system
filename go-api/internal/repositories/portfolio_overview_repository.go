package repositories

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/trading-system/go-api/internal/database"
)

type PortfolioOverviewRepository struct {
	db *sql.DB
}

func NewPortfolioOverviewRepository() *PortfolioOverviewRepository {
	return &PortfolioOverviewRepository{db: database.DB}
}

// Local types to avoid import cycles; shapes must match models used elsewhere.
type DataLoadAlertEvent struct {
	AlertEventID   string           `json:"alert_event_id"`
	AlertID        string           `json:"alert_id"`
	AlertType      string           `json:"alert_type"`
	AlertName      string           `json:"alert_name"`
	Symbol         string           `json:"symbol"`
	EventType      string           `json:"event_type"`
	EventTimestamp time.Time        `json:"event_timestamp"`
	CreatedAt      time.Time        `json:"created_at"`
	UrgencyLevel   *string          `json:"urgency_level,omitempty"`
	Status         *string          `json:"status,omitempty"`
	TriggerReason  string           `json:"trigger_reason"`
	TriggerDetails *json.RawMessage `json:"trigger_details,omitempty"`
	EventData      *json.RawMessage `json:"event_data,omitempty"`
	PreviousData   *json.RawMessage `json:"previous_data,omitempty"`
}

// PortfolioOverview aggregates portfolio metadata, holdings, and recent activity for the home screen.
type PortfolioOverview struct {
	PortfolioID  string               `json:"portfolio_id"`
	Name         string               `json:"name"`
	UserID       string               `json:"user_id"`
	Holdings     []PortfolioHolding   `json:"holdings"`
	RecentAlerts []DataLoadAlertEvent `json:"recent_alerts"`
	RecentGrades []StockGradeAction   `json:"recent_grades"`
	RecentNews   []NewsArticle        `json:"recent_news"`
	WindowDays   int                  `json:"window_days"`
	GeneratedAt  time.Time            `json:"generated_at"`
}

// PortfolioHolding represents minimal holding info for overview.
type PortfolioHolding struct {
	Symbol        string   `json:"symbol"`
	Shares        float64  `json:"shares"`
	AvgCost       *float64 `json:"avg_cost,omitempty"`
	CurrentPrice  *float64 `json:"current_price,omitempty"`
	MarketValue   *float64 `json:"market_value,omitempty"`
	UnrealizedPL  *float64 `json:"unrealized_pl,omitempty"`
	UnrealizedPct *float64 `json:"unrealized_pct,omitempty"`
}

// GetOverview returns aggregated portfolio context for a home screen.
func (r *PortfolioOverviewRepository) GetOverview(portfolioID string, windowDays int, subscriptionLevel string) (*PortfolioOverview, error) {
	if windowDays <= 0 {
		windowDays = 7
	}
	since := time.Now().AddDate(0, 0, -windowDays)

	// 1) Portfolio metadata
	var name, userID string
	err := r.db.QueryRow(`SELECT name, user_id FROM portfolios WHERE id = CAST($1 AS uuid)`, portfolioID).Scan(&name, &userID)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("portfolio not found: %s", portfolioID)
		}
		return nil, fmt.Errorf("failed to query portfolio metadata: %w", err)
	}

	// 2) Holdings with latest price
	holdings, err := r.fetchHoldings(portfolioID)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch holdings: %w", err)
	}

	// 3) Recent alerts (universal_alert_events for symbols in portfolio)
	alerts, err := r.fetchRecentAlerts(portfolioID, since)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch recent alerts: %w", err)
	}

	// 4) Recent grade actions (stock_grades for symbols in portfolio)
	grades, err := r.fetchRecentGrades(portfolioID, since)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch recent grades: %w", err)
	}

	// 5) Recent news (stock_news for symbols in portfolio)
	news, err := r.fetchRecentNews(portfolioID, since, 20)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch recent news: %w", err)
	}

	return &PortfolioOverview{
		PortfolioID:  portfolioID,
		Name:         name,
		UserID:       userID,
		Holdings:     holdings,
		RecentAlerts: alerts,
		RecentGrades: grades,
		RecentNews:   news,
		WindowDays:   windowDays,
		GeneratedAt:  time.Now().UTC(),
	}, nil
}

// fetchHoldings returns minimal holding info with latest price from stocks table.
func (r *PortfolioOverviewRepository) fetchHoldings(portfolioID string) ([]PortfolioHolding, error) {
	query := `
		WITH h AS (
			SELECT symbol, shares, avg_cost
			FROM portfolio_holdings
			WHERE portfolio_id = CAST($1 AS uuid)
		)
		SELECT
			h.symbol,
			h.shares,
			h.avg_cost,
			s.current_price,
			COALESCE(h.shares * s.current_price, 0) AS market_value,
			CASE WHEN s.current_price IS NOT NULL AND h.avg_cost IS NOT NULL
				 THEN (s.current_price - h.avg_cost) * h.shares
				 ELSE NULL
			END AS unrealized_pl,
			CASE WHEN s.current_price IS NOT NULL AND h.avg_cost IS NOT NULL AND h.avg_cost <> 0
				 THEN ((s.current_price - h.avg_cost) / h.avg_cost) * 100
				 ELSE NULL
			END AS unrealized_pct
		FROM h
		LEFT JOIN stocks s ON UPPER(s.symbol) = UPPER(h.symbol)
		ORDER BY market_value DESC NULLS LAST
	`
	rows, err := r.db.Query(query, portfolioID)
	if err != nil {
		return nil, fmt.Errorf("failed to query holdings: %w", err)
	}
	defer rows.Close()

	var out []PortfolioHolding
	for rows.Next() {
		var h PortfolioHolding
		if err := rows.Scan(
			&h.Symbol, &h.Shares, &h.AvgCost, &h.CurrentPrice,
			&h.MarketValue, &h.UnrealizedPL, &h.UnrealizedPct,
		); err != nil {
			return nil, fmt.Errorf("failed to scan holding: %w", err)
		}
		out = append(out, h)
	}
	return out, nil
}

// fetchRecentAlerts returns recent alert events for portfolio symbols.
func (r *PortfolioOverviewRepository) fetchRecentAlerts(portfolioID string, since time.Time) ([]DataLoadAlertEvent, error) {
	query := `
		WITH symbols AS (
			SELECT symbol FROM portfolio_holdings WHERE portfolio_id = CAST($1 AS uuid)
		)
		SELECT
			ae.event_id AS alert_event_id,
			ae.alert_id AS alert_id,
			a.alert_type AS alert_type,
			a.alert_name AS alert_name,
			COALESCE(NULLIF(ue.entity_id, ''), ue.event_data->>'symbol') AS symbol,
			ue.event_type AS event_type,
			ue.event_timestamp AS event_timestamp,
			ae.created_at AS created_at,
			ae.urgency_level AS urgency_level,
			ae.status AS status,
			ae.trigger_reason AS trigger_reason,
			ae.trigger_details AS trigger_details,
			ue.event_data AS event_data,
			ue.previous_data AS previous_data
		FROM universal_alert_events ae
		JOIN universal_events ue ON ue.event_id = ae.universal_event_id
		JOIN universal_alerts a ON a.alert_id = ae.alert_id
		WHERE ue.event_type IN ('grade_change', 'consensus_update', 'fundamentals_update')
		  AND ue.entity_type = 'stock'
		  AND COALESCE(NULLIF(ue.entity_id, ''), ue.event_data->>'symbol') IN (SELECT symbol FROM symbols)
		  AND ae.created_at >= $2
		ORDER BY ae.created_at DESC
		LIMIT 50
	`
	rows, err := r.db.Query(query, portfolioID, since)
	if err != nil {
		return nil, fmt.Errorf("failed to query recent alerts: %w", err)
	}
	defer rows.Close()

	var out []DataLoadAlertEvent
	for rows.Next() {
		var ev DataLoadAlertEvent
		if err := rows.Scan(
			&ev.AlertEventID, &ev.AlertID, &ev.AlertType, &ev.AlertName, &ev.Symbol,
			&ev.EventType, &ev.EventTimestamp, &ev.CreatedAt, &ev.UrgencyLevel,
			&ev.Status, &ev.TriggerReason, &ev.TriggerDetails, &ev.EventData, &ev.PreviousData,
		); err != nil {
			return nil, fmt.Errorf("failed to scan alert event: %w", err)
		}
		out = append(out, ev)
	}
	return out, nil
}

// fetchRecentGrades returns recent stock grade actions for portfolio symbols.
func (r *PortfolioOverviewRepository) fetchRecentGrades(portfolioID string, since time.Time) ([]StockGradeAction, error) {
	query := `
		WITH symbols AS (
			SELECT symbol FROM portfolio_holdings WHERE portfolio_id = CAST($1 AS uuid)
		)
		SELECT id::text, symbol, grade_date::text, grading_company, previous_grade, new_grade, action, data_source, created_at
		FROM stock_grades
		WHERE UPPER(symbol) IN (SELECT UPPER(symbol) FROM symbols)
		  AND grade_date >= $2::date
		  AND action IN ('upgrade', 'downgrade', 'initiate')
		ORDER BY grade_date DESC, created_at DESC
		LIMIT 100
	`
	rows, err := r.db.Query(query, portfolioID, since.Format("2006-01-02"))
	if err != nil {
		return nil, fmt.Errorf("failed to query recent grades: %w", err)
	}
	defer rows.Close()

	var out []StockGradeAction
	for rows.Next() {
		var g StockGradeAction
		if err := rows.Scan(
			&g.ID, &g.Symbol, &g.GradeDate, &g.GradingCompany,
			&g.PreviousGrade, &g.NewGrade, &g.Action, &g.DataSource, &g.CreatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan grade action: %w", err)
		}
		out = append(out, g)
	}
	return out, nil
}

// fetchRecentNews returns recent news for portfolio symbols.
func (r *PortfolioOverviewRepository) fetchRecentNews(portfolioID string, since time.Time, limit int) ([]NewsArticle, error) {
	if limit <= 0 {
		limit = 20
	}
	query := `
		WITH symbols AS (
			SELECT symbol FROM portfolio_holdings WHERE portfolio_id = CAST($1 AS uuid)
		)
		SELECT n.title, COALESCE(n.publisher, ''), COALESCE(n.link, ''), COALESCE(n.published_date::text, ''), n.related_symbols
		FROM stock_news n
		JOIN stocks s ON s.id = n.stock_id
		WHERE UPPER(s.symbol) IN (SELECT UPPER(symbol) FROM symbols)
		  AND n.published_date >= $2
		ORDER BY n.published_date DESC NULLS LAST, n.created_at DESC
		LIMIT $3
	`
	rows, err := r.db.Query(query, portfolioID, since, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to query recent news: %w", err)
	}
	defer rows.Close()

	var out []NewsArticle
	for rows.Next() {
		var n NewsArticle
		var relatedJSON string
		if err := rows.Scan(&n.Title, &n.Publisher, &n.Link, &n.PublishedDate, &relatedJSON); err != nil {
			return nil, fmt.Errorf("failed to scan news article: %w", err)
		}
		if relatedJSON != "" {
			if err := json.Unmarshal([]byte(relatedJSON), &n.RelatedSymbols); err != nil {
				// non-fatal, ignore related_symbols on parse error
			}
		}
		out = append(out, n)
	}
	return out, nil
}
