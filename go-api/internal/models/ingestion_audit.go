package models

import (
	"encoding/json"
	"time"
)

// DataLoadAlertEvent is a joined view of universal_alert_events + universal_events (+ minimal alert info)
// used by the operator UX to show alerts generated during a data-load run.
type DataLoadAlertEvent struct {
	AlertEventID   string           `json:"alert_event_id" db:"alert_event_id"`
	AlertID        string           `json:"alert_id" db:"alert_id"`
	AlertType      string           `json:"alert_type" db:"alert_type"`
	AlertName      string           `json:"alert_name" db:"alert_name"`
	Symbol         string           `json:"symbol" db:"symbol"`
	EventType      string           `json:"event_type" db:"event_type"`
	EventTimestamp time.Time        `json:"event_timestamp" db:"event_timestamp"`
	CreatedAt      time.Time        `json:"created_at" db:"created_at"`
	UrgencyLevel   *string          `json:"urgency_level,omitempty" db:"urgency_level"`
	Status         *string          `json:"status,omitempty" db:"status"`
	TriggerReason  string           `json:"trigger_reason" db:"trigger_reason"`
	TriggerDetails *json.RawMessage `json:"trigger_details,omitempty" db:"trigger_details"`
	EventData      *json.RawMessage `json:"event_data,omitempty" db:"event_data"`
	PreviousData   *json.RawMessage `json:"previous_data,omitempty" db:"previous_data"`
}

type PortfolioSymbolAlertSummary struct {
	Symbol        string     `json:"symbol" db:"symbol"`
	AlertCount    int        `json:"alert_count" db:"alert_count"`
	LatestAlertAt *time.Time `json:"latest_alert_at,omitempty" db:"latest_alert_at"`
}

// DataIngestionRun maps to data_ingestion_runs.
type DataIngestionRun struct {
	RunID       string          `json:"run_id" db:"run_id"`
	StartedAt   time.Time       `json:"started_at" db:"started_at"`
	FinishedAt  *time.Time      `json:"finished_at,omitempty" db:"finished_at"`
	Status      string          `json:"status" db:"status"`
	Environment *string         `json:"environment,omitempty" db:"environment"`
	GitSHA      *string         `json:"git_sha,omitempty" db:"git_sha"`
	Metadata    json.RawMessage `json:"metadata" db:"metadata"`
}

// DataIngestionEvent maps to data_ingestion_events.
type DataIngestionEvent struct {
	ID               int64           `json:"id" db:"id"`
	RunID            string          `json:"run_id" db:"run_id"`
	EventTS          time.Time       `json:"event_ts" db:"event_ts"`
	Level            string          `json:"level" db:"level"`
	Provider         *string         `json:"provider,omitempty" db:"provider"`
	Operation        string          `json:"operation" db:"operation"`
	Symbol           *string         `json:"symbol,omitempty" db:"symbol"`
	DurationMS       *int            `json:"duration_ms,omitempty" db:"duration_ms"`
	RecordsIn        *int            `json:"records_in,omitempty" db:"records_in"`
	RecordsSaved     *int            `json:"records_saved,omitempty" db:"records_saved"`
	Message          *string         `json:"message,omitempty" db:"message"`
	ErrorType        *string         `json:"error_type,omitempty" db:"error_type"`
	ErrorMessage     *string         `json:"error_message,omitempty" db:"error_message"`
	RootCauseType    *string         `json:"root_cause_type,omitempty" db:"root_cause_type"`
	RootCauseMessage *string         `json:"root_cause_message,omitempty" db:"root_cause_message"`
	Context          json.RawMessage `json:"context" db:"context"`
}
