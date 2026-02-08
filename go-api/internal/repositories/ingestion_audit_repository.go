package repositories

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/lib/pq"
	"github.com/trading-system/go-api/internal/database"
	"github.com/trading-system/go-api/internal/models"
)

type IngestionAuditRepository struct {
	db *sql.DB
}

func NewIngestionAuditRepository() *IngestionAuditRepository {
	return &IngestionAuditRepository{db: database.DB}
}

func (r *IngestionAuditRepository) CreateRun(runID string, status string, metadata map[string]any) error {
	b, err := json.Marshal(metadata)
	if err != nil {
		return fmt.Errorf("failed to marshal metadata: %w", err)
	}

	query := `
		INSERT INTO data_ingestion_runs (run_id, started_at, status, metadata)
		VALUES (CAST($1 AS uuid), NOW(), $2, CAST($3 AS jsonb))
		ON CONFLICT (run_id) DO NOTHING
	`
	_, err = r.db.Exec(query, runID, status, string(b))
	if err != nil {
		return fmt.Errorf("failed to insert run: %w", err)
	}
	return nil
}

func (r *IngestionAuditRepository) PatchRunMetadata(runID string, metadataPatch map[string]any) error {
	b, err := json.Marshal(metadataPatch)
	if err != nil {
		return fmt.Errorf("failed to marshal metadata patch: %w", err)
	}

	query := `
		UPDATE data_ingestion_runs
		SET metadata = COALESCE(metadata, '{}'::jsonb) || CAST($2 AS jsonb)
		WHERE run_id = CAST($1 AS uuid)
	`
	_, err = r.db.Exec(query, runID, string(b))
	if err != nil {
		return fmt.Errorf("failed to patch run metadata: %w", err)
	}
	return nil
}

func (r *IngestionAuditRepository) RequestCancel(runID string) error {
	return r.PatchRunMetadata(runID, map[string]any{"cancel_requested_at": time.Now().UTC().Format(time.RFC3339)})
}

func (r *IngestionAuditRepository) IsCancelRequested(runID string) (bool, error) {
	query := `
		SELECT COALESCE(metadata->>'cancel_requested_at','')
		FROM data_ingestion_runs
		WHERE run_id = CAST($1 AS uuid)
	`
	var s string
	if err := r.db.QueryRow(query, runID).Scan(&s); err != nil {
		if err == sql.ErrNoRows {
			return false, fmt.Errorf("run not found")
		}
		return false, fmt.Errorf("failed to check cancel flag: %w", err)
	}
	return s != "", nil
}

func (r *IngestionAuditRepository) CreateEvent(
	runID string,
	level string,
	operation string,
	symbol *string,
	provider *string,
	message *string,
	errorMessage *string,
	context map[string]any,
	durationMS *int,
) error {
	ctxJSON := "{}"
	if context != nil {
		b, err := json.Marshal(context)
		if err != nil {
			return fmt.Errorf("failed to marshal event context: %w", err)
		}
		ctxJSON = string(b)
	}

	query := `
		INSERT INTO data_ingestion_events (
			run_id, event_ts, level, provider, operation, symbol,
			duration_ms, message, error_message, context
		) VALUES (
			CAST($1 AS uuid), NOW(), $2, $3, $4, $5,
			$6, $7, $8, CAST($9 AS jsonb)
		)
	`
	_, err := r.db.Exec(query, runID, level, provider, operation, symbol, durationMS, message, errorMessage, ctxJSON)
	if err != nil {
		return fmt.Errorf("failed to insert ingestion event: %w", err)
	}
	return nil
}

func (r *IngestionAuditRepository) UpdateRunStatus(runID string, status string, metadataPatch map[string]any) error {
	b, err := json.Marshal(metadataPatch)
	if err != nil {
		return fmt.Errorf("failed to marshal metadata patch: %w", err)
	}

	query := `
		UPDATE data_ingestion_runs
		SET finished_at = NOW(),
			status = $2,
			metadata = COALESCE(metadata, '{}'::jsonb) || CAST($3 AS jsonb)
		WHERE run_id = CAST($1 AS uuid)
	`
	_, err = r.db.Exec(query, runID, status, string(b))
	if err != nil {
		return fmt.Errorf("failed to update run: %w", err)
	}
	return nil
}

func (r *IngestionAuditRepository) GetRun(runID string) (*models.DataIngestionRun, error) {
	query := `
		SELECT run_id, started_at, finished_at, status, environment, git_sha, metadata
		FROM data_ingestion_runs
		WHERE run_id = CAST($1 AS uuid)
	`
	var run models.DataIngestionRun
	if err := r.db.QueryRow(query, runID).Scan(
		&run.RunID,
		&run.StartedAt,
		&run.FinishedAt,
		&run.Status,
		&run.Environment,
		&run.GitSHA,
		&run.Metadata,
	); err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("run not found")
		}
		return nil, fmt.Errorf("failed to get run: %w", err)
	}
	return &run, nil
}

func (r *IngestionAuditRepository) ListRunsByPortfolio(portfolioID string, limit int) ([]models.DataIngestionRun, error) {
	if limit <= 0 {
		limit = 20
	}
	query := `
		SELECT run_id, started_at, finished_at, status, environment, git_sha, metadata
		FROM data_ingestion_runs
		WHERE COALESCE(metadata->>'portfolio_id','') = $1
		ORDER BY started_at DESC
		LIMIT $2
	`
	rows, err := r.db.Query(query, portfolioID, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to list runs: %w", err)
	}
	defer rows.Close()

	var runs []models.DataIngestionRun
	for rows.Next() {
		var run models.DataIngestionRun
		if err := rows.Scan(
			&run.RunID,
			&run.StartedAt,
			&run.FinishedAt,
			&run.Status,
			&run.Environment,
			&run.GitSHA,
			&run.Metadata,
		); err != nil {
			return nil, fmt.Errorf("failed to scan run: %w", err)
		}
		runs = append(runs, run)
	}
	return runs, nil
}

func (r *IngestionAuditRepository) ListEvents(runID string, limit int) ([]models.DataIngestionEvent, error) {
	if limit <= 0 {
		limit = 200
	}
	query := `
		SELECT id, run_id, event_ts, level, provider, operation, symbol,
			duration_ms, records_in, records_saved, message,
			error_type, error_message, root_cause_type, root_cause_message, context
		FROM data_ingestion_events
		WHERE run_id = CAST($1 AS uuid)
		ORDER BY event_ts DESC
		LIMIT $2
	`
	rows, err := r.db.Query(query, runID, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to list events: %w", err)
	}
	defer rows.Close()

	var events []models.DataIngestionEvent
	for rows.Next() {
		var ev models.DataIngestionEvent
		if err := rows.Scan(
			&ev.ID,
			&ev.RunID,
			&ev.EventTS,
			&ev.Level,
			&ev.Provider,
			&ev.Operation,
			&ev.Symbol,
			&ev.DurationMS,
			&ev.RecordsIn,
			&ev.RecordsSaved,
			&ev.Message,
			&ev.ErrorType,
			&ev.ErrorMessage,
			&ev.RootCauseType,
			&ev.RootCauseMessage,
			&ev.Context,
		); err != nil {
			return nil, fmt.Errorf("failed to scan event: %w", err)
		}
		events = append(events, ev)
	}
	return events, nil
}

func (r *IngestionAuditRepository) FailedSymbolsForRun(runID string) ([]string, error) {
	query := `
		SELECT DISTINCT symbol
		FROM data_ingestion_events
		WHERE run_id = CAST($1 AS uuid)
			AND symbol IS NOT NULL
			AND error_message IS NOT NULL
	`
	rows, err := r.db.Query(query, runID)
	if err != nil {
		return nil, fmt.Errorf("failed to query failed symbols: %w", err)
	}
	defer rows.Close()

	var symbols []string
	for rows.Next() {
		var s sql.NullString
		if err := rows.Scan(&s); err != nil {
			return nil, fmt.Errorf("failed to scan symbol: %w", err)
		}
		if s.Valid {
			symbols = append(symbols, s.String)
		}
	}
	return symbols, nil
}

func (r *IngestionAuditRepository) SymbolsForPortfolio(portfolioID string) ([]string, error) {
	query := `
		SELECT DISTINCT s.symbol
		FROM portfolio_positions pp
		JOIN stocks s ON s.id = pp.stock_id
		WHERE pp.portfolio_id = CAST($1 AS uuid)
		ORDER BY s.symbol
	`
	rows, err := r.db.Query(query, portfolioID)
	if err != nil {
		return nil, fmt.Errorf("failed to query portfolio symbols: %w", err)
	}
	defer rows.Close()

	out := make([]string, 0)
	for rows.Next() {
		var s string
		if err := rows.Scan(&s); err != nil {
			return nil, fmt.Errorf("failed to scan portfolio symbol: %w", err)
		}
		if s != "" {
			out = append(out, s)
		}
	}
	return out, nil
}

func (r *IngestionAuditRepository) PortfolioSymbolsAlertSummary(symbols []string, since time.Time) ([]models.PortfolioSymbolAlertSummary, error) {
	if len(symbols) == 0 {
		return []models.PortfolioSymbolAlertSummary{}, nil
	}

	query := `
		SELECT
			COALESCE(NULLIF(ue.entity_id, ''), ue.event_data->>'symbol') AS symbol,
			COUNT(1) AS alert_count,
			MAX(ae.created_at) AS latest_alert_at
		FROM universal_alert_events ae
		JOIN universal_events ue ON ue.event_id = ae.universal_event_id
		WHERE (
			ue.entity_id = ANY($1)
			OR (ue.event_data->>'symbol') = ANY($1)
		)
			AND ae.created_at >= $2
		GROUP BY 1
		ORDER BY latest_alert_at DESC
	`

	rows, err := r.db.Query(query, pq.Array(symbols), since)
	if err != nil {
		return nil, fmt.Errorf("failed to summarize portfolio symbol alerts: %w", err)
	}
	defer rows.Close()

	out := make([]models.PortfolioSymbolAlertSummary, 0)
	for rows.Next() {
		var row models.PortfolioSymbolAlertSummary
		if err := rows.Scan(&row.Symbol, &row.AlertCount, &row.LatestAlertAt); err != nil {
			return nil, fmt.Errorf("failed to scan portfolio symbol alert summary: %w", err)
		}
		out = append(out, row)
	}

	return out, nil
}

func (r *IngestionAuditRepository) ListAlertEventsForSymbol(symbol string, since time.Time, limit int) ([]models.DataLoadAlertEvent, error) {
	if limit <= 0 {
		limit = 200
	}

	query := `
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
		WHERE (
			ue.entity_id = $1
			OR (ue.event_data->>'symbol') = $1
		)
			AND ae.created_at >= $2
		ORDER BY ae.created_at DESC
		LIMIT $3
	`

	rows, err := r.db.Query(query, symbol, since, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to list alert events for symbol: %w", err)
	}
	defer rows.Close()

	out := make([]models.DataLoadAlertEvent, 0)
	for rows.Next() {
		var row models.DataLoadAlertEvent
		if err := rows.Scan(
			&row.AlertEventID,
			&row.AlertID,
			&row.AlertType,
			&row.AlertName,
			&row.Symbol,
			&row.EventType,
			&row.EventTimestamp,
			&row.CreatedAt,
			&row.UrgencyLevel,
			&row.Status,
			&row.TriggerReason,
			&row.TriggerDetails,
			&row.EventData,
			&row.PreviousData,
		); err != nil {
			return nil, fmt.Errorf("failed to scan alert event row: %w", err)
		}
		out = append(out, row)
	}

	return out, nil
}

func (r *IngestionAuditRepository) ListRunAlertEvents(runID string, symbols []string, since time.Time, limit int) ([]models.DataLoadAlertEvent, error) {
	if limit <= 0 {
		limit = 200
	}

	// Note: some universal_events (especially older ingestion-time emitters) may not
	// populate entity_id. Fall back to event_data->>'symbol' so run alert-events works.
	query := `
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
		WHERE (
			ue.entity_id = ANY($1)
			OR (ue.event_data->>'symbol') = ANY($1)
		)
			AND ae.created_at >= $2
		ORDER BY ae.created_at DESC
		LIMIT $3
	`

	rows, err := r.db.Query(query, pq.Array(symbols), since, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to list run alert events: %w", err)
	}
	defer rows.Close()

	out := make([]models.DataLoadAlertEvent, 0)
	for rows.Next() {
		var row models.DataLoadAlertEvent
		if err := rows.Scan(
			&row.AlertEventID,
			&row.AlertID,
			&row.AlertType,
			&row.AlertName,
			&row.Symbol,
			&row.EventType,
			&row.EventTimestamp,
			&row.CreatedAt,
			&row.UrgencyLevel,
			&row.Status,
			&row.TriggerReason,
			&row.TriggerDetails,
			&row.EventData,
			&row.PreviousData,
		); err != nil {
			return nil, fmt.Errorf("failed to scan alert event row: %w", err)
		}
		out = append(out, row)
	}

	return out, nil
}
