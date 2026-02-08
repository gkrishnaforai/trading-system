package repositories

import (
	"context"
	"database/sql"
	"fmt"

	"github.com/trading-system/go-api/internal/database"
)

type DataPreviewRepository struct {
	db *sql.DB
}

func NewDataPreviewRepository() *DataPreviewRepository {
	return &DataPreviewRepository{db: database.DB}
}

type PreviewQuerySpec struct {
	Table     string
	Columns   []string
	SymbolCol string
	OrderBy   string
	WhereExpr string
}

func (r *DataPreviewRepository) ResolveSpec(ctx context.Context, candidates []PreviewQuerySpec) (PreviewQuerySpec, error) {
	for _, c := range candidates {
		ok, err := r.specIsQueryable(ctx, c)
		if err != nil {
			return PreviewQuerySpec{}, err
		}
		if ok {
			return c, nil
		}
	}
	return PreviewQuerySpec{}, fmt.Errorf("no compatible preview spec found")
}

func (r *DataPreviewRepository) specIsQueryable(ctx context.Context, spec PreviewQuerySpec) (bool, error) {
	var regclass sql.NullString
	if err := r.db.QueryRowContext(ctx, "SELECT to_regclass($1)", "public."+spec.Table).Scan(&regclass); err != nil {
		return false, fmt.Errorf("failed to check table existence: %w", err)
	}
	if !regclass.Valid || regclass.String == "" {
		return false, nil
	}

	colsToCheck := make([]string, 0, 1+len(spec.Columns))
	colsToCheck = append(colsToCheck, spec.SymbolCol)
	for _, c := range spec.Columns {
		colsToCheck = append(colsToCheck, c)
	}

	for _, col := range colsToCheck {
		if col == "*" {
			continue
		}
		if containsSpace(col) || containsParen(col) {
			continue
		}

		var exists bool
		if err := r.db.QueryRowContext(
			ctx,
			"SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=$1 AND column_name=$2)",
			spec.Table,
			col,
		).Scan(&exists); err != nil {
			return false, fmt.Errorf("failed to check column existence: %w", err)
		}
		if !exists {
			return false, nil
		}
	}

	return true, nil
}

func (r *DataPreviewRepository) Fetch(ctx context.Context, spec PreviewQuerySpec, symbol string, limit int, offset int, allColumns bool) ([]map[string]any, error) {
	if limit <= 0 {
		limit = 50
	}
	if limit > 500 {
		limit = 500
	}
	if offset < 0 {
		offset = 0
	}

	cols := "*"
	if !allColumns && len(spec.Columns) > 0 {
		cols = joinColumns(spec.Columns)
	}

	where := fmt.Sprintf("UPPER(%s) = UPPER($1)", spec.SymbolCol)
	if spec.WhereExpr != "" {
		where = fmt.Sprintf("(%s) AND (%s)", where, spec.WhereExpr)
	}

	orderBy := spec.OrderBy
	if orderBy == "" {
		orderBy = spec.SymbolCol + " ASC"
	}

	query := fmt.Sprintf(
		"SELECT %s FROM %s WHERE %s ORDER BY %s LIMIT $2 OFFSET $3",
		cols,
		spec.Table,
		where,
		orderBy,
	)

	rows, err := r.db.QueryContext(ctx, query, symbol, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("failed to query preview data: %w", err)
	}
	defer rows.Close()

	return scanRowsToMaps(rows)
}

func scanRowsToMaps(rows *sql.Rows) ([]map[string]any, error) {
	cols, err := rows.Columns()
	if err != nil {
		return nil, err
	}

	out := make([]map[string]any, 0)
	for rows.Next() {
		vals := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range vals {
			ptrs[i] = &vals[i]
		}

		if err := rows.Scan(ptrs...); err != nil {
			return nil, err
		}

		m := make(map[string]any, len(cols))
		for i, c := range cols {
			v := vals[i]
			if b, ok := v.([]byte); ok {
				m[c] = string(b)
			} else {
				m[c] = v
			}
		}
		out = append(out, m)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

func joinColumns(cols []string) string {
	if len(cols) == 0 {
		return "*"
	}

	out := ""
	for i, c := range cols {
		if i > 0 {
			out += ", "
		}
		out += c
	}
	return out
}

func containsSpace(s string) bool {
	for _, ch := range s {
		if ch == ' ' || ch == '\t' || ch == '\n' {
			return true
		}
	}
	return false
}

func containsParen(s string) bool {
	for _, ch := range s {
		if ch == '(' || ch == ')' {
			return true
		}
	}
	return false
}
