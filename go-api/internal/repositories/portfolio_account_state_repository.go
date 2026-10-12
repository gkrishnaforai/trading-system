package repositories

import (
	"database/sql"
	"encoding/json"
	"fmt"

	"github.com/trading-system/go-api/internal/database"
)

type PortfolioAccountStateRepository struct{ db *sql.DB }

func NewPortfolioAccountStateRepository() *PortfolioAccountStateRepository {
	return &PortfolioAccountStateRepository{db: database.DB}
}

func (r *PortfolioAccountStateRepository) Latest(portfolioID string) (map[string]any, error) {
	var raw string
	err := r.db.QueryRow(`SELECT jsonb_build_object(
		'account_state_id', account_state_id, 'portfolio_id', portfolio_id,
		'as_of', as_of, 'account_equity', account_equity, 'settled_cash', settled_cash,
		'unsettled_cash', unsettled_cash, 'buying_power', buying_power,
		'portfolio_heat', portfolio_heat, 'source', source,
		'reconciliation_status', reconciliation_status, 'missing_fields', missing_fields
	)::text FROM portfolio_account_states WHERE portfolio_id=$1 ORDER BY as_of DESC LIMIT 1`, portfolioID).Scan(&raw)
	if err == sql.ErrNoRows {
		return map[string]any{}, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to load account state: %w", err)
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		return nil, fmt.Errorf("failed to decode account state: %w", err)
	}
	return result, nil
}

func (r *PortfolioAccountStateRepository) Save(portfolioID string, values map[string]any) (map[string]any, error) {
	missing := []string{}
	for _, field := range []string{"account_equity", "settled_cash", "buying_power"} {
		if values[field] == nil {
			missing = append(missing, field)
		}
	}
	status, _ := values["reconciliation_status"].(string)
	if status == "" {
		if len(missing) > 0 {
			status = "UNRECONCILED"
		} else {
			status = "RECONCILED"
		}
	}
	missingJSON, _ := json.Marshal(missing)

	var raw string
	err := r.db.QueryRow(`INSERT INTO portfolio_account_states
		(portfolio_id, account_equity, settled_cash, unsettled_cash, buying_power,
		 portfolio_heat, source, reconciliation_status, missing_fields)
		VALUES ($1,$2,$3,$4,$5,$6,COALESCE($7,'manual_ui'),$8,CAST($9 AS jsonb))
		RETURNING jsonb_build_object(
			'account_state_id', account_state_id, 'portfolio_id', portfolio_id,
			'as_of', as_of, 'account_equity', account_equity,
			'settled_cash', settled_cash, 'unsettled_cash', unsettled_cash,
			'buying_power', buying_power, 'portfolio_heat', portfolio_heat,
			'source', source, 'reconciliation_status', reconciliation_status,
			'missing_fields', missing_fields
		)::text`,
		portfolioID,
		values["account_equity"], values["settled_cash"], values["unsettled_cash"],
		values["buying_power"], values["portfolio_heat"], values["source"],
		status, string(missingJSON),
	).Scan(&raw)
	if err != nil {
		return nil, fmt.Errorf("failed to save account state: %w", err)
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		return nil, fmt.Errorf("failed to decode saved account state: %w", err)
	}
	return result, nil
}
