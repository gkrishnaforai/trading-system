package repositories

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	"github.com/trading-system/go-api/internal/database"
	"github.com/trading-system/go-api/internal/models"
)

type ScheduleRepository struct {
	db *sql.DB
}

func NewScheduleRepository() *ScheduleRepository {
	return &ScheduleRepository{db: database.DB}
}

func (r *ScheduleRepository) List(limit int) ([]models.Schedule, error) {
	if limit <= 0 {
		limit = 200
	}
	if limit > 1000 {
		limit = 1000
	}
	query := `
		SELECT schedule_id, kind, portfolio_id, profile, cron_expression, timezone, enabled,
		       config, next_run_at, last_run_at, last_run_id, created_at, updated_at
		FROM schedules
		ORDER BY created_at DESC
		LIMIT $1
	`
	rows, err := r.db.Query(query, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to list schedules: %w", err)
	}
	defer rows.Close()

	out := []models.Schedule{}
	for rows.Next() {
		var s models.Schedule
		var cfg []byte
		var next sql.NullTime
		var last sql.NullTime
		var lastRun sql.NullString
		if err := rows.Scan(
			&s.ScheduleID,
			&s.Kind,
			&s.PortfolioID,
			&s.Profile,
			&s.CronExpression,
			&s.Timezone,
			&s.Enabled,
			&cfg,
			&next,
			&last,
			&lastRun,
			&s.CreatedAt,
			&s.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan schedule: %w", err)
		}
		if len(cfg) == 0 {
			s.Config = json.RawMessage("{}")
		} else {
			s.Config = json.RawMessage(cfg)
		}
		if next.Valid {
			t := next.Time
			s.NextRunAt = &t
		}
		if last.Valid {
			t := last.Time
			s.LastRunAt = &t
		}
		if lastRun.Valid {
			v := lastRun.String
			s.LastRunID = &v
		}
		out = append(out, s)
	}
	return out, nil
}

func (r *ScheduleRepository) Get(scheduleID string) (*models.Schedule, error) {
	query := `
		SELECT schedule_id, kind, portfolio_id, profile, cron_expression, timezone, enabled,
		       config, next_run_at, last_run_at, last_run_id, created_at, updated_at
		FROM schedules
		WHERE schedule_id = CAST($1 AS uuid)
	`
	var s models.Schedule
	var cfg []byte
	var next sql.NullTime
	var last sql.NullTime
	var lastRun sql.NullString
	if err := r.db.QueryRow(query, scheduleID).Scan(
		&s.ScheduleID,
		&s.Kind,
		&s.PortfolioID,
		&s.Profile,
		&s.CronExpression,
		&s.Timezone,
		&s.Enabled,
		&cfg,
		&next,
		&last,
		&lastRun,
		&s.CreatedAt,
		&s.UpdatedAt,
	); err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("schedule not found")
		}
		return nil, fmt.Errorf("failed to get schedule: %w", err)
	}
	if len(cfg) == 0 {
		s.Config = json.RawMessage("{}")
	} else {
		s.Config = json.RawMessage(cfg)
	}
	if next.Valid {
		t := next.Time
		s.NextRunAt = &t
	}
	if last.Valid {
		t := last.Time
		s.LastRunAt = &t
	}
	if lastRun.Valid {
		v := lastRun.String
		s.LastRunID = &v
	}
	return &s, nil
}

func (r *ScheduleRepository) Create(s *models.Schedule) error {
	if s == nil {
		return fmt.Errorf("schedule is nil")
	}
	cfg := []byte("{}")
	if len(s.Config) > 0 {
		cfg = []byte(s.Config)
	}
	query := `
		INSERT INTO schedules (kind, portfolio_id, profile, cron_expression, timezone, enabled, config, next_run_at)
		VALUES ($1, CAST($2 AS uuid), $3, $4, $5, $6, $7::jsonb, $8)
		RETURNING schedule_id, created_at, updated_at
	`
	var next any
	if s.NextRunAt != nil {
		next = *s.NextRunAt
	} else {
		next = nil
	}
	if err := r.db.QueryRow(query, s.Kind, s.PortfolioID, s.Profile, s.CronExpression, s.Timezone, s.Enabled, string(cfg), next).
		Scan(&s.ScheduleID, &s.CreatedAt, &s.UpdatedAt); err != nil {
		return fmt.Errorf("failed to create schedule: %w", err)
	}
	return nil
}

func (r *ScheduleRepository) Update(scheduleID string, updates map[string]any) error {
	if scheduleID == "" {
		return fmt.Errorf("schedule_id is required")
	}
	if len(updates) == 0 {
		return nil
	}

	setParts := []string{}
	args := []any{}

	allowed := map[string]bool{
		"kind":            true,
		"portfolio_id":    true,
		"profile":         true,
		"cron_expression": true,
		"timezone":        true,
		"enabled":         true,
		"config":          true,
		"next_run_at":     true,
		"last_run_at":     true,
		"last_run_id":     true,
	}

	for k, v := range updates {
		if !allowed[k] {
			continue
		}
		if k == "portfolio_id" {
			setParts = append(setParts, fmt.Sprintf("%s = CAST($%d AS uuid)", k, len(args)+1))
			args = append(args, v)
			continue
		}
		if k == "config" {
			setParts = append(setParts, fmt.Sprintf("%s = $%d::jsonb", k, len(args)+1))
			args = append(args, v)
			continue
		}
		if k == "last_run_id" {
			setParts = append(setParts, fmt.Sprintf("%s = CAST($%d AS uuid)", k, len(args)+1))
			args = append(args, v)
			continue
		}
		setParts = append(setParts, fmt.Sprintf("%s = $%d", k, len(args)+1))
		args = append(args, v)
	}

	if len(setParts) == 0 {
		return nil
	}

	args = append(args, scheduleID)
	query := fmt.Sprintf("UPDATE schedules SET %s WHERE schedule_id = CAST($%d AS uuid)", join(setParts, ", "), len(args))
	_, err := r.db.Exec(query, args...)
	if err != nil {
		return fmt.Errorf("failed to update schedule: %w", err)
	}
	return nil
}

func (r *ScheduleRepository) Delete(scheduleID string) error {
	_, err := r.db.Exec(`DELETE FROM schedules WHERE schedule_id = CAST($1 AS uuid)`, scheduleID)
	if err != nil {
		return fmt.Errorf("failed to delete schedule: %w", err)
	}
	return nil
}

type DueSchedule struct {
	Schedule models.Schedule
}

func (r *ScheduleRepository) WithTx(fn func(tx *sql.Tx) error) error {
	tx, err := r.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit()
}

func (r *ScheduleRepository) GetDueForUpdate(tx *sql.Tx, now time.Time, limit int) ([]models.Schedule, error) {
	if limit <= 0 {
		limit = 25
	}
	if limit > 200 {
		limit = 200
	}
	query := `
		SELECT schedule_id, kind, portfolio_id, profile, cron_expression, timezone, enabled,
		       config, next_run_at, last_run_at, last_run_id, created_at, updated_at
		FROM schedules
		WHERE enabled = TRUE
		  AND next_run_at IS NOT NULL
		  AND next_run_at <= $1
		ORDER BY next_run_at ASC
		LIMIT $2
		FOR UPDATE SKIP LOCKED
	`
	rows, err := tx.Query(query, now, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to query due schedules: %w", err)
	}
	defer rows.Close()

	out := []models.Schedule{}
	for rows.Next() {
		var s models.Schedule
		var cfg []byte
		var next sql.NullTime
		var last sql.NullTime
		var lastRun sql.NullString
		if err := rows.Scan(
			&s.ScheduleID,
			&s.Kind,
			&s.PortfolioID,
			&s.Profile,
			&s.CronExpression,
			&s.Timezone,
			&s.Enabled,
			&cfg,
			&next,
			&last,
			&lastRun,
			&s.CreatedAt,
			&s.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("failed to scan due schedule: %w", err)
		}
		if len(cfg) == 0 {
			s.Config = json.RawMessage("{}")
		} else {
			s.Config = json.RawMessage(cfg)
		}
		if next.Valid {
			t := next.Time
			s.NextRunAt = &t
		}
		if last.Valid {
			t := last.Time
			s.LastRunAt = &t
		}
		if lastRun.Valid {
			v := lastRun.String
			s.LastRunID = &v
		}
		out = append(out, s)
	}
	return out, nil
}

func (r *ScheduleRepository) UpdateAfterTick(tx *sql.Tx, scheduleID string, lastRunAt time.Time, nextRunAt time.Time, lastRunID string) error {
	query := `
		UPDATE schedules
		SET last_run_at = $1,
		    next_run_at = $2,
		    last_run_id = CAST($3 AS uuid)
		WHERE schedule_id = CAST($4 AS uuid)
	`
	_, err := tx.Exec(query, lastRunAt, nextRunAt, lastRunID, scheduleID)
	if err != nil {
		return fmt.Errorf("failed to update schedule after tick: %w", err)
	}
	return nil
}

func (r *ScheduleRepository) DisableTx(tx *sql.Tx, scheduleID string) error {
	_, err := tx.Exec(
		`UPDATE schedules SET enabled = FALSE WHERE schedule_id = CAST($1 AS uuid)`,
		scheduleID,
	)
	if err != nil {
		return fmt.Errorf("failed to disable schedule: %w", err)
	}
	return nil
}

func join(parts []string, sep string) string {
	out := ""
	for i, p := range parts {
		if i > 0 {
			out += sep
		}
		out += p
	}
	return out
}
