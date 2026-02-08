package models

import "time"

type NotificationQueueItem struct {
	QueueID        string     `json:"queue_id"`
	AlertEventID   string     `json:"alert_event_id"`
	ChannelType    string     `json:"channel_type"`
	Recipient      string     `json:"recipient"`
	UserEmail      string     `json:"user_email"`
	Subject        string     `json:"subject"`
	Status         string     `json:"status"`
	Attempts       int        `json:"attempts"`
	MaxAttempts    int        `json:"max_attempts"`
	ErrorMessage   *string    `json:"error_message,omitempty"`
	CreatedAt      time.Time  `json:"created_at"`
	UpdatedAt      time.Time  `json:"updated_at"`
	CorrelationID  *string    `json:"correlation_id,omitempty"`
}

type NotificationQueueSummaryRow struct {
	ChannelType string `json:"channel_type"`
	Status      string `json:"status"`
	Count       int    `json:"count"`
}
