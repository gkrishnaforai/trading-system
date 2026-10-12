package repositories

import (
	"database/sql"
	"encoding/json"
	"fmt"

	"github.com/trading-system/go-api/internal/database"
)

// PortfolioAgentHistoryRepository exposes read-only review snapshots to UI clients.
type PortfolioAgentHistoryRepository struct{ db *sql.DB }

func NewPortfolioAgentHistoryRepository() *PortfolioAgentHistoryRepository {
	return &PortfolioAgentHistoryRepository{db: database.DB}
}

const snapshotJSON = `
jsonb_build_object(
  'snapshot_id', s.snapshot_id,
  'portfolio_id', s.portfolio_id,
  'as_of', s.as_of,
  'account_equity', s.account_equity,
  'settled_cash', s.settled_cash,
  'unsettled_cash', s.unsettled_cash,
  'buying_power', s.buying_power,
  'invested_value', s.invested_value,
  'portfolio_heat', s.portfolio_heat,
  'price_freshness', s.price_freshness,
  'reconciliation_status', s.reconciliation_status,
  'missing_fields', s.missing_fields,
  'source', s.source,
  'created_at', s.created_at,
  'positions', COALESCE((
    SELECT jsonb_agg(jsonb_build_object(
      'symbol', p.symbol, 'quantity', p.quantity,
      'average_entry_price', p.average_entry_price,
      'current_price', p.current_price, 'current_value', p.current_value,
      'unrealized_pnl', p.unrealized_pnl,
      'unrealized_pnl_pct', p.unrealized_pnl_pct,
      'sector', p.sector, 'industry', p.industry,
      'stop_price', p.stop_price, 'target_price', p.target_price,
      'status', p.status, 'price_as_of', p.price_as_of,
      'action', d.action, 'decision_confidence', d.decision_confidence,
      'risk_status', d.risk_status, 'risk_allowed', d.risk_allowed,
      'setup_type', d.setup_type, 'reasons', d.reasons, 'vetoes', d.vetoes
    ) ORDER BY p.symbol)
    FROM portfolio_agent_position_states p
    LEFT JOIN LATERAL (
      SELECT d.*
      FROM portfolio_agent_decisions d
      WHERE d.decision_id = p.decision_id
         OR (d.portfolio_id = s.portfolio_id AND d.symbol = p.symbol
             AND d.created_at >= s.created_at
             AND d.created_at <= s.created_at + INTERVAL '1 hour')
      ORDER BY CASE WHEN d.decision_id = p.decision_id THEN 0 ELSE 1 END, d.created_at
      LIMIT 1
    ) d ON TRUE
    WHERE p.snapshot_id = s.snapshot_id
  ), '[]'::jsonb)
)::text
`

func (r *PortfolioAgentHistoryRepository) ListSnapshots(portfolioID string, limit int) ([]map[string]any, error) {
	if limit <= 0 || limit > 100 {
		limit = 30
	}
	rows, err := r.db.Query(`SELECT `+snapshotJSON+` FROM portfolio_agent_snapshots s WHERE s.portfolio_id = $1 ORDER BY s.as_of DESC LIMIT $2`, portfolioID, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to list portfolio snapshots: %w", err)
	}
	defer rows.Close()
	return scanSnapshotRows(rows)
}

func (r *PortfolioAgentHistoryRepository) GetSnapshot(portfolioID, snapshotID string) (map[string]any, error) {
	var raw string
	err := r.db.QueryRow(`SELECT `+snapshotJSON+` FROM portfolio_agent_snapshots s WHERE s.portfolio_id = $1 AND s.snapshot_id = $2`, portfolioID, snapshotID).Scan(&raw)
	if err == sql.ErrNoRows {
		return nil, fmt.Errorf("portfolio snapshot not found")
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get portfolio snapshot: %w", err)
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		return nil, fmt.Errorf("failed to decode portfolio snapshot: %w", err)
	}
	return result, nil
}

func scanSnapshotRows(rows *sql.Rows) ([]map[string]any, error) {
	result := make([]map[string]any, 0)
	for rows.Next() {
		var raw string
		if err := rows.Scan(&raw); err != nil {
			return nil, fmt.Errorf("failed to scan portfolio snapshot: %w", err)
		}
		var item map[string]any
		if err := json.Unmarshal([]byte(raw), &item); err != nil {
			return nil, fmt.Errorf("failed to decode portfolio snapshot: %w", err)
		}
		result = append(result, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return result, nil
}
