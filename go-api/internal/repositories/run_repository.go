package repositories

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/trading-system/go-api/internal/database"
	"github.com/trading-system/go-api/internal/models"
)

type RunRepository struct {
	db *sql.DB
}

func NewRunRepository() *RunRepository {
	return &RunRepository{db: database.DB}
}

// CreateRun creates a durable run record and returns the run_id.
// If runID is empty, a new UUID will be generated.
func (r *RunRepository) CreateRun(runID string, status string, metadata map[string]any) (string, error) {
	if runID == "" {
		runID = fmt.Sprintf("%d", time.Now().UnixNano())
	}
	metaBytes, err := json.Marshal(metadata)
	if err != nil {
		return "", fmt.Errorf("failed to marshal metadata: %w", err)
	}
	query := `
		INSERT INTO data_ingestion_runs (run_id, started_at, status, metadata)
		VALUES (CAST($1 AS uuid), NOW(), $2, CAST($3 AS jsonb))
		ON CONFLICT (run_id) DO NOTHING
	`
	_, err = r.db.Exec(query, runID, status, string(metaBytes))
	if err != nil {
		return "", fmt.Errorf("failed to insert run: %w", err)
	}
	return runID, nil
}

// UpdateRunStatus updates the run status and optionally finished_at.
func (r *RunRepository) UpdateRunStatus(runID string, status string, finishedAt *time.Time) error {
	query := `
		UPDATE data_ingestion_runs
		SET status = $2, finished_at = COALESCE($3, finished_at)
		WHERE run_id = CAST($1 AS uuid)
	`
	_, err := r.db.Exec(query, runID, status, finishedAt)
	if err != nil {
		return fmt.Errorf("failed to update run status: %w", err)
	}
	return nil
}

// GetRun returns the run record (metadata, status, timestamps).
func (r *RunRepository) GetRun(runID string) (*models.DataIngestionRun, error) {
	query := `
		SELECT run_id, started_at, finished_at, status, metadata
		FROM data_ingestion_runs
		WHERE run_id = CAST($1 AS uuid)
	`
	var run models.DataIngestionRun
	var metaJSON string
	err := r.db.QueryRow(query, runID).Scan(
		&run.RunID, &run.StartedAt, &run.FinishedAt, &run.Status, &metaJSON,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("run not found: %s", runID)
		}
		return nil, fmt.Errorf("failed to get run: %w", err)
	}
	if metaJSON != "" {
		run.Metadata = json.RawMessage(metaJSON)
	}
	return &run, nil
}

// ListRuns returns recent runs.
func (r *RunRepository) ListRuns(limit int) ([]models.DataIngestionRun, error) {
	if limit <= 0 {
		limit = 20
	}
	query := `
		SELECT run_id, started_at, finished_at, status, metadata
		FROM data_ingestion_runs
		ORDER BY started_at DESC
		LIMIT $1
	`
	rows, err := r.db.Query(query, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to list runs: %w", err)
	}
	defer rows.Close()

	var out []models.DataIngestionRun
	for rows.Next() {
		var run models.DataIngestionRun
		var metaJSON string
		if err := rows.Scan(
			&run.RunID, &run.StartedAt, &run.FinishedAt, &run.Status, &metaJSON,
		); err != nil {
			return nil, fmt.Errorf("failed to scan run: %w", err)
		}
		if metaJSON != "" {
			run.Metadata = json.RawMessage(metaJSON)
		}
		out = append(out, run)
	}
	return out, nil
}
