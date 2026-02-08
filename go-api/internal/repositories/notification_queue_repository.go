package repositories

import (
	"database/sql"
	"fmt"
	"time"

	"github.com/trading-system/go-api/internal/database"
	"github.com/trading-system/go-api/internal/models"
)

type NotificationQueueRepository struct {
	db *sql.DB
}

func NewNotificationQueueRepository() *NotificationQueueRepository {
	return &NotificationQueueRepository{db: database.DB}
}

func (r *NotificationQueueRepository) Summary(since time.Time) ([]models.NotificationQueueSummaryRow, error) {
	query := `
		SELECT channel_type,
		       status,
		       COUNT(*) AS count
		FROM universal_notification_queue
		WHERE created_at >= $1
		GROUP BY channel_type, status
		ORDER BY channel_type, status
	`

	rows, err := r.db.Query(query, since)
	if err != nil {
		return nil, fmt.Errorf("failed to query notification queue summary: %w", err)
	}
	defer rows.Close()

	out := []models.NotificationQueueSummaryRow{}
	for rows.Next() {
		var row models.NotificationQueueSummaryRow
		if err := rows.Scan(&row.ChannelType, &row.Status, &row.Count); err != nil {
			return nil, fmt.Errorf("failed to scan summary row: %w", err)
		}
		out = append(out, row)
	}
	return out, nil
}

func (r *NotificationQueueRepository) Recent(limit int, status *string, since *time.Time) ([]models.NotificationQueueItem, error) {
	if limit <= 0 {
		limit = 50
	}
	if limit > 500 {
		limit = 500
	}

	query := `
		SELECT q.queue_id,
		       q.alert_event_id,
		       q.channel_type,
		       q.recipient,
		       COALESCE(q.user_email, '') AS user_email,
		       COALESCE(q.subject, '') AS subject,
		       q.status,
		       q.attempts,
		       q.max_attempts,
		       q.error_message,
		       q.created_at,
		       q.updated_at,
		       e.correlation_id
		FROM universal_notification_queue q
		LEFT JOIN universal_alert_events e ON e.event_id = q.alert_event_id
		WHERE ($1::text IS NULL OR q.status = $1)
		  AND ($3::timestamptz IS NULL OR q.created_at >= $3)
		ORDER BY q.created_at DESC
		LIMIT $2
	`

	rows, err := r.db.Query(query, status, limit, since)
	if err != nil {
		return nil, fmt.Errorf("failed to query recent notifications: %w", err)
	}
	defer rows.Close()

	items := []models.NotificationQueueItem{}
	for rows.Next() {
		var it models.NotificationQueueItem
		var errMsg sql.NullString
		var corr sql.NullString
		if err := rows.Scan(
			&it.QueueID,
			&it.AlertEventID,
			&it.ChannelType,
			&it.Recipient,
			&it.UserEmail,
			&it.Subject,
			&it.Status,
			&it.Attempts,
			&it.MaxAttempts,
			&errMsg,
			&it.CreatedAt,
			&it.UpdatedAt,
			&corr,
		); err != nil {
			return nil, fmt.Errorf("failed to scan notification: %w", err)
		}
		if errMsg.Valid {
			it.ErrorMessage = &errMsg.String
		}
		if corr.Valid {
			it.CorrelationID = &corr.String
		}
		items = append(items, it)
	}
	return items, nil
}

func (r *NotificationQueueRepository) ByCorrelationID(correlationID string, limit int) ([]models.NotificationQueueItem, error) {
	if limit <= 0 {
		limit = 200
	}
	if limit > 500 {
		limit = 500
	}

	query := `
		SELECT q.queue_id,
		       q.alert_event_id,
		       q.channel_type,
		       q.recipient,
		       COALESCE(q.user_email, '') AS user_email,
		       COALESCE(q.subject, '') AS subject,
		       q.status,
		       q.attempts,
		       q.max_attempts,
		       q.error_message,
		       q.created_at,
		       q.updated_at,
		       e.correlation_id
		FROM universal_notification_queue q
		JOIN universal_alert_events e ON e.event_id = q.alert_event_id
		WHERE e.correlation_id = $1
		ORDER BY q.created_at DESC
		LIMIT $2
	`

	rows, err := r.db.Query(query, correlationID, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to query notifications by correlation_id: %w", err)
	}
	defer rows.Close()

	items := []models.NotificationQueueItem{}
	for rows.Next() {
		var it models.NotificationQueueItem
		var errMsg sql.NullString
		var corr sql.NullString
		if err := rows.Scan(
			&it.QueueID,
			&it.AlertEventID,
			&it.ChannelType,
			&it.Recipient,
			&it.UserEmail,
			&it.Subject,
			&it.Status,
			&it.Attempts,
			&it.MaxAttempts,
			&errMsg,
			&it.CreatedAt,
			&it.UpdatedAt,
			&corr,
		); err != nil {
			return nil, fmt.Errorf("failed to scan notification: %w", err)
		}
		if errMsg.Valid {
			it.ErrorMessage = &errMsg.String
		}
		if corr.Valid {
			it.CorrelationID = &corr.String
		}
		items = append(items, it)
	}
	return items, nil
}
