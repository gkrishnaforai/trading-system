package repositories

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"encoding/json"
	"fmt"
	"time"

	"github.com/trading-system/go-api/internal/database"
)

type PortfolioSchedule struct {
	ID                      string     `db:"id"`
	PortfolioID             string     `db:"portfolio_id"`
	UserID                  string     `db:"user_id"`
	ScheduleType            string     `db:"schedule_type"`
	ScheduleTime            string     `db:"schedule_time"`
	ScheduleDay             *int       `db:"schedule_day"`
	IsActive                bool       `db:"is_active"`
	LastRun                 *time.Time `db:"last_run"`
	NextRun                 *time.Time `db:"next_run"`
	NotificationPreferences string     `db:"notification_preferences"`
	CreatedAt               time.Time  `db:"created_at"`
	UpdatedAt               time.Time  `db:"updated_at"`
	PortfolioName           string     `db:"portfolio_name"`
	Username                string     `db:"username"`
	UserEmail               string     `db:"user_email"`
}

type ScheduleStatus string

const (
	ScheduleStatusScheduled ScheduleStatus = "scheduled"
	ScheduleStatusRunning   ScheduleStatus = "running"
	ScheduleStatusPaused    ScheduleStatus = "paused"
	ScheduleStatusError     ScheduleStatus = "error"
)

type ScheduleResponse struct {
	ID                      string          `json:"id"`
	PortfolioID             string          `json:"portfolio_id"`
	PortfolioName           string          `json:"portfolio_name"`
	UserID                  string          `json:"user_id"`
	Username                string          `json:"username"`
	UserEmail               string          `json:"user_email"`
	ScheduleType            string          `json:"schedule_type"`
	ScheduleTime            string          `json:"schedule_time"`
	ScheduleDay             *int            `json:"schedule_day"`
	IsActive                bool            `json:"is_active"`
	LastRun                 *time.Time      `json:"last_run"`
	NextRun                 *time.Time      `json:"next_run"`
	NotificationPreferences map[string]bool `json:"notification_preferences"`
	CreatedAt               time.Time       `json:"created_at"`
	UpdatedAt               time.Time       `json:"updated_at"`
	JobStatus               ScheduleStatus  `json:"job_status"`
}

type ScheduleListResponse struct {
	Schedules    []ScheduleResponse `json:"schedules"`
	TotalCount   int                `json:"total_count"`
	ActiveCount  int                `json:"active_count"`
	PausedCount  int                `json:"paused_count"`
	RunningCount int                `json:"running_count"`
}

type ScheduleOverview struct {
	SchedulerRunning  bool           `json:"scheduler_running"`
	TotalSchedules    int            `json:"total_schedules"`
	ActiveSchedules   int            `json:"active_schedules"`
	PausedSchedules   int            `json:"paused_schedules"`
	SchedulesWithRuns int            `json:"schedules_with_runs"`
	UpcomingRuns      int            `json:"upcoming_runs"`
	TypeDistribution  map[string]int `json:"type_distribution"`
	RecentRuns        []RecentRun    `json:"recent_runs"`
}

type RecentRun struct {
	ScheduleID    string    `json:"schedule_id"`
	PortfolioName string    `json:"portfolio_name"`
	LastRun       time.Time `json:"last_run"`
	IsActive      bool      `json:"is_active"`
}

type NotificationPreferences map[string]bool

// Value implements the driver.Valuer interface for NotificationPreferences
func (np NotificationPreferences) Value() (driver.Value, error) {
	if np == nil {
		return nil, nil
	}
	return json.Marshal(np)
}

// Scan implements the sql.Scanner interface for NotificationPreferences
func (np *NotificationPreferences) Scan(value interface{}) error {
	if value == nil {
		*np = make(NotificationPreferences)
		return nil
	}

	switch v := value.(type) {
	case []byte:
		return json.Unmarshal(v, np)
	case string:
		return json.Unmarshal([]byte(v), np)
	default:
		return fmt.Errorf("cannot scan %T into NotificationPreferences", value)
	}
}

type PortfolioScheduleRepository struct {
	db *sql.DB
}

func NewPortfolioScheduleRepository() *PortfolioScheduleRepository {
	return &PortfolioScheduleRepository{
		db: database.DB,
	}
}

func (r *PortfolioScheduleRepository) ListSchedules(ctx context.Context, status, portfolioID, userID string) (*ScheduleListResponse, error) {
	query := `
		SELECT 
			sa.id, sa.portfolio_id, sa.user_id, sa.schedule_type,
			sa.schedule_time, sa.schedule_day, sa.is_active,
			sa.last_run, sa.next_run, sa.notification_preferences,
			sa.created_at, sa.updated_at,
			p.name as portfolio_name, u.username, u.email as user_email
		FROM scheduled_analyses sa
		JOIN portfolios p ON sa.portfolio_id = p.id
		JOIN users u ON sa.user_id = u.id
	`

	whereConditions := []string{}
	args := []interface{}{}
	argIndex := 1

	if status != "" && status != "all" {
		if status == "active" {
			whereConditions = append(whereConditions, "sa.is_active = $"+fmt.Sprintf("%d", argIndex))
			args = append(args, true)
			argIndex++
		} else if status == "paused" {
			whereConditions = append(whereConditions, "sa.is_active = $"+fmt.Sprintf("%d", argIndex))
			args = append(args, false)
			argIndex++
		}
	}

	if portfolioID != "" {
		whereConditions = append(whereConditions, "sa.portfolio_id = $"+fmt.Sprintf("%d", argIndex))
		args = append(args, portfolioID)
		argIndex++
	}

	if userID != "" {
		whereConditions = append(whereConditions, "sa.user_id = $"+fmt.Sprintf("%d", argIndex))
		args = append(args, userID)
		argIndex++
	}

	if len(whereConditions) > 0 {
		query += " WHERE " + fmt.Sprintf("%s", whereConditions[0])
		for i := 1; i < len(whereConditions); i++ {
			query += " AND " + whereConditions[i]
		}
	}

	query += " ORDER BY sa.created_at DESC"

	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to query schedules: %w", err)
	}
	defer rows.Close()

	var schedules []PortfolioSchedule
	for rows.Next() {
		var schedule PortfolioSchedule
		err := rows.Scan(
			&schedule.ID,
			&schedule.PortfolioID,
			&schedule.UserID,
			&schedule.ScheduleType,
			&schedule.ScheduleTime,
			&schedule.ScheduleDay,
			&schedule.IsActive,
			&schedule.LastRun,
			&schedule.NextRun,
			&schedule.NotificationPreferences,
			&schedule.CreatedAt,
			&schedule.UpdatedAt,
			&schedule.PortfolioName,
			&schedule.Username,
			&schedule.UserEmail,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan schedule: %w", err)
		}
		schedules = append(schedules, schedule)
	}

	// Convert to response format
	response := &ScheduleListResponse{
		Schedules: make([]ScheduleResponse, 0),
	}

	for _, schedule := range schedules {
		// Parse notification preferences
		var prefs NotificationPreferences
		if err := json.Unmarshal([]byte(schedule.NotificationPreferences), &prefs); err != nil {
			prefs = NotificationPreferences{"push": false, "email": true}
		}

		// Determine job status (simplified since we can't access Python scheduler directly)
		jobStatus := ScheduleStatusPaused
		if schedule.IsActive {
			jobStatus = ScheduleStatusScheduled
		}

		scheduleResp := ScheduleResponse{
			ID:                      schedule.ID,
			PortfolioID:             schedule.PortfolioID,
			PortfolioName:           schedule.PortfolioName,
			UserID:                  schedule.UserID,
			Username:                schedule.Username,
			UserEmail:               schedule.UserEmail,
			ScheduleType:            schedule.ScheduleType,
			ScheduleTime:            schedule.ScheduleTime,
			ScheduleDay:             schedule.ScheduleDay,
			IsActive:                schedule.IsActive,
			LastRun:                 schedule.LastRun,
			NextRun:                 schedule.NextRun,
			NotificationPreferences: prefs,
			CreatedAt:               schedule.CreatedAt,
			UpdatedAt:               schedule.UpdatedAt,
			JobStatus:               jobStatus,
		}

		response.Schedules = append(response.Schedules, scheduleResp)
		response.TotalCount++

		if schedule.IsActive {
			response.ActiveCount++
		} else {
			response.PausedCount++
		}

		if jobStatus == ScheduleStatusRunning {
			response.RunningCount++
		}
	}

	return response, nil
}

func (r *PortfolioScheduleRepository) GetSchedule(ctx context.Context, scheduleID string) (*ScheduleResponse, error) {
	query := `
		SELECT 
			sa.id, sa.portfolio_id, sa.user_id, sa.schedule_type,
			sa.schedule_time, sa.schedule_day, sa.is_active,
			sa.last_run, sa.next_run, sa.notification_preferences,
			sa.created_at, sa.updated_at,
			p.name as portfolio_name, u.username, u.email as user_email
		FROM scheduled_analyses sa
		JOIN portfolios p ON sa.portfolio_id = p.id
		JOIN users u ON sa.user_id = u.id
		WHERE sa.id = $1
	`

	var schedule PortfolioSchedule
	err := r.db.QueryRowContext(ctx, query, scheduleID).Scan(
		&schedule.ID,
		&schedule.PortfolioID,
		&schedule.UserID,
		&schedule.ScheduleType,
		&schedule.ScheduleTime,
		&schedule.ScheduleDay,
		&schedule.IsActive,
		&schedule.LastRun,
		&schedule.NextRun,
		&schedule.NotificationPreferences,
		&schedule.CreatedAt,
		&schedule.UpdatedAt,
		&schedule.PortfolioName,
		&schedule.Username,
		&schedule.UserEmail,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("schedule not found")
		}
		return nil, fmt.Errorf("failed to get schedule: %w", err)
	}

	// Parse notification preferences
	var prefs NotificationPreferences
	if err := json.Unmarshal([]byte(schedule.NotificationPreferences), &prefs); err != nil {
		prefs = NotificationPreferences{"push": false, "email": true}
	}

	// Determine job status
	jobStatus := ScheduleStatusPaused
	if schedule.IsActive {
		jobStatus = ScheduleStatusScheduled
	}

	return &ScheduleResponse{
		ID:                      schedule.ID,
		PortfolioID:             schedule.PortfolioID,
		PortfolioName:           schedule.PortfolioName,
		UserID:                  schedule.UserID,
		Username:                schedule.Username,
		UserEmail:               schedule.UserEmail,
		ScheduleType:            schedule.ScheduleType,
		ScheduleTime:            schedule.ScheduleTime,
		ScheduleDay:             schedule.ScheduleDay,
		IsActive:                schedule.IsActive,
		LastRun:                 schedule.LastRun,
		NextRun:                 schedule.NextRun,
		NotificationPreferences: prefs,
		CreatedAt:               schedule.CreatedAt,
		UpdatedAt:               schedule.UpdatedAt,
		JobStatus:               jobStatus,
	}, nil
}

func (r *PortfolioScheduleRepository) GetScheduleOverview(ctx context.Context) (*ScheduleOverview, error) {
	// Get status counts
	var total, active, paused, hasRun, upcoming int

	err := r.db.QueryRowContext(ctx, `
		SELECT 
			COUNT(*) as total,
			COUNT(CASE WHEN is_active = true THEN 1 END) as active,
			COUNT(CASE WHEN is_active = false THEN 1 END) as paused,
			COUNT(CASE WHEN last_run IS NOT NULL THEN 1 END) as has_run,
			COUNT(CASE WHEN next_run > CURRENT_TIMESTAMP THEN 1 END) as upcoming
		FROM scheduled_analyses
	`).Scan(&total, &active, &paused, &hasRun, &upcoming)
	if err != nil {
		return nil, fmt.Errorf("failed to get status counts: %w", err)
	}

	// Get type distribution
	typeQuery := `
		SELECT schedule_type, COUNT(*) as count
		FROM scheduled_analyses
		GROUP BY schedule_type
	`

	rows, err := r.db.QueryContext(ctx, typeQuery)
	if err != nil {
		return nil, fmt.Errorf("failed to get type distribution: %w", err)
	}
	defer rows.Close()

	typeDistribution := make(map[string]int)
	for rows.Next() {
		var scheduleType string
		var count int
		if err := rows.Scan(&scheduleType, &count); err != nil {
			return nil, fmt.Errorf("failed to scan type distribution: %w", err)
		}
		typeDistribution[scheduleType] = count
	}

	// Get recent runs
	recentQuery := `
		SELECT sa.id, p.name as portfolio_name, sa.last_run, sa.is_active
		FROM scheduled_analyses sa
		JOIN portfolios p ON sa.portfolio_id = p.id
		WHERE sa.last_run IS NOT NULL
		ORDER BY sa.last_run DESC
		LIMIT 10
	`

	rows, err = r.db.QueryContext(ctx, recentQuery)
	if err != nil {
		return nil, fmt.Errorf("failed to get recent runs: %w", err)
	}
	defer rows.Close()

	var recentRuns []RecentRun
	for rows.Next() {
		var run RecentRun
		if err := rows.Scan(&run.ScheduleID, &run.PortfolioName, &run.LastRun, &run.IsActive); err != nil {
			return nil, fmt.Errorf("failed to scan recent run: %w", err)
		}
		recentRuns = append(recentRuns, run)
	}

	// Check scheduler status (simplified - would need to call Python API for real status)
	schedulerRunning := false // TODO: Call Python API to check real status

	return &ScheduleOverview{
		SchedulerRunning:  schedulerRunning,
		TotalSchedules:    total,
		ActiveSchedules:   active,
		PausedSchedules:   paused,
		SchedulesWithRuns: hasRun,
		UpcomingRuns:      upcoming,
		TypeDistribution:  typeDistribution,
		RecentRuns:        recentRuns,
	}, nil
}
