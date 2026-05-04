package repositories

import (
	"database/sql"
	"fmt"
	"time"

	"github.com/trading-system/go-api/internal/database"
)

type StockGradesRepository struct {
	db *sql.DB
}

type StockGradeAction struct {
	ID             string     `json:"id"`
	Symbol         string     `json:"symbol"`
	GradeDate      string     `json:"grade_date"`
	GradingCompany string     `json:"grading_company"`
	PreviousGrade  *string    `json:"previous_grade,omitempty"`
	NewGrade       string     `json:"new_grade"`
	Action         string     `json:"action"`
	DataSource     *string    `json:"data_source,omitempty"`
	CreatedAt      *time.Time `json:"created_at,omitempty"`
}

func NewStockGradesRepository() *StockGradesRepository {
	return &StockGradesRepository{db: database.DB}
}

func (r *StockGradesRepository) ListRecentActions(symbol string, days int, limit int) ([]StockGradeAction, error) {
	if days <= 0 {
		days = 7
	}
	if limit <= 0 {
		limit = 100
	}

	query := `
		SELECT
			id::text,
			symbol,
			grade_date::text,
			grading_company,
			previous_grade,
			new_grade,
			action,
			data_source,
			created_at
		FROM stock_grades
		WHERE UPPER(symbol) = UPPER($1)
			AND grade_date >= CURRENT_DATE - ($2 || ' days')::interval
			AND action IN ('upgrade', 'downgrade', 'initiate', 'maintain')
		ORDER BY grade_date DESC, created_at DESC
		LIMIT $3
	`

	rows, err := r.db.Query(query, symbol, days, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to query stock grades: %w", err)
	}
	defer rows.Close()

	out := make([]StockGradeAction, 0)
	for rows.Next() {
		var a StockGradeAction
		var prev sql.NullString
		var ds sql.NullString
		var createdAt sql.NullTime
		if err := rows.Scan(
			&a.ID,
			&a.Symbol,
			&a.GradeDate,
			&a.GradingCompany,
			&prev,
			&a.NewGrade,
			&a.Action,
			&ds,
			&createdAt,
		); err != nil {
			continue
		}
		if prev.Valid {
			v := prev.String
			a.PreviousGrade = &v
		}
		if ds.Valid {
			v := ds.String
			a.DataSource = &v
		}
		if createdAt.Valid {
			v := createdAt.Time
			a.CreatedAt = &v
		}
		out = append(out, a)
	}

	return out, nil
}

// GetLatestConsensus returns the latest consensus data for a symbol
func (r *StockGradesRepository) GetLatestConsensus(symbol string) (*map[string]interface{}, error) {
	query := `
		SELECT 
			symbol,
			strong_buy,
			buy,
			hold,
			sell,
			strong_sell,
			consensus_rating,
			consensus_score,
			total_analysts,
			last_updated
		FROM stock_grade_consensus
		WHERE UPPER(symbol) = UPPER($1)
		ORDER BY last_updated DESC
		LIMIT 1
	`

	var (
		symbolVal       string
		strongBuy       int
		buy             int
		hold            int
		sell            int
		strongSell      int
		consensusRating string
		consensusScore  float64
		totalAnalysts   int
		lastUpdated     time.Time
	)

	err := r.db.QueryRow(query, symbol).Scan(
		&symbolVal,
		&strongBuy,
		&buy,
		&hold,
		&sell,
		&strongSell,
		&consensusRating,
		&consensusScore,
		&totalAnalysts,
		&lastUpdated,
	)

	if err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to query consensus: %w", err)
	}

	consensus := map[string]interface{}{
		"symbol":           symbolVal,
		"strong_buy":       strongBuy,
		"buy":              buy,
		"hold":             hold,
		"sell":             sell,
		"strong_sell":      strongSell,
		"consensus_rating": consensusRating,
		"consensus_score":  consensusScore,
		"total_analysts":   totalAnalysts,
		"last_updated":     lastUpdated,
	}

	return &consensus, nil
}

// GetLatestPriceTargets returns the latest price targets for a symbol
func (r *StockGradesRepository) GetLatestPriceTargets(symbol string) (*map[string]interface{}, error) {
	query := `
		SELECT 
			symbol,
			target_date,
			analyst_name,
			analyst_firm,
			price_target,
			rating,
			price_when_posted,
			published_at,
			created_at
		FROM price_targets
		WHERE UPPER(symbol) = UPPER($1)
		ORDER BY target_date DESC, created_at DESC
		LIMIT 10
	`

	rows, err := r.db.Query(query, symbol)
	if err != nil {
		return nil, fmt.Errorf("failed to query price targets: %w", err)
	}
	defer rows.Close()

	var priceTargets []map[string]interface{}
	for rows.Next() {
		var (
			symbolVal       string
			targetDate      time.Time
			analystName     string
			analystFirm     string
			priceTarget     float64
			rating          sql.NullString
			priceWhenPosted sql.NullFloat64
			publishedAt     sql.NullTime
			createdAt       sql.NullTime
		)

		err := rows.Scan(
			&symbolVal,
			&targetDate,
			&analystName,
			&analystFirm,
			&priceTarget,
			&rating,
			&priceWhenPosted,
			&publishedAt,
			&createdAt,
		)
		if err != nil {
			continue
		}

		pt := map[string]interface{}{
			"symbol":       symbolVal,
			"target_date":  targetDate,
			"analyst_name": analystName,
			"analyst_firm": analystFirm,
			"price_target": priceTarget,
		}

		if rating.Valid {
			pt["rating"] = rating.String
		}

		if priceWhenPosted.Valid {
			pt["price_when_posted"] = priceWhenPosted.Float64
		}
		if publishedAt.Valid {
			pt["published_at"] = publishedAt.Time
		}
		if createdAt.Valid {
			pt["created_at"] = createdAt.Time
		}

		priceTargets = append(priceTargets, pt)
	}

	if len(priceTargets) == 0 {
		return nil, nil
	}

	result := map[string]interface{}{
		"price_targets": priceTargets,
		"count":         len(priceTargets),
	}

	return &result, nil
}
