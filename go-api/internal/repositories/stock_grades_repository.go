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
			AND action IN ('upgrade', 'downgrade', 'initiate')
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
