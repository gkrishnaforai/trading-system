package models

import (
	"encoding/json"
	"time"
)

type Schedule struct {
	ScheduleID     string          `json:"schedule_id" db:"schedule_id"`
	Kind           string          `json:"kind" db:"kind"`
	PortfolioID    string          `json:"portfolio_id" db:"portfolio_id"`
	Profile        string          `json:"profile" db:"profile"`
	CronExpression string          `json:"cron_expression" db:"cron_expression"`
	Timezone       string          `json:"timezone" db:"timezone"`
	Enabled        bool            `json:"enabled" db:"enabled"`
	Config         json.RawMessage `json:"config" db:"config"`
	NextRunAt      *time.Time      `json:"next_run_at" db:"next_run_at"`
	LastRunAt      *time.Time      `json:"last_run_at" db:"last_run_at"`
	LastRunID      *string         `json:"last_run_id" db:"last_run_id"`
	CreatedAt      time.Time       `json:"created_at" db:"created_at"`
	UpdatedAt      time.Time       `json:"updated_at" db:"updated_at"`
}
