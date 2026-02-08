package handlers

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/repositories"
)

type NotificationQueueHandler struct {
	repo *repositories.NotificationQueueRepository
}

func NewNotificationQueueHandler(repo *repositories.NotificationQueueRepository) *NotificationQueueHandler {
	return &NotificationQueueHandler{repo: repo}
}

// GET /api/v1/notifications/queue/summary?window_hours=24
func (h *NotificationQueueHandler) Summary(c *gin.Context) {
	var since time.Time
	var sincePtr *time.Time
	if v := c.Query("since"); v != "" {
		parsed, err := time.Parse(time.RFC3339, v)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "since must be RFC3339 timestamp"})
			return
		}
		since = parsed
		sincePtr = &since
	}

	windowHours := 24
	if v := c.Query("window_hours"); v != "" {
		if parsed, err := parseInt(v); err == nil && parsed > 0 {
			windowHours = parsed
		}
	}
	if sincePtr == nil {
		since = time.Now().Add(-time.Duration(windowHours) * time.Hour)
		sincePtr = &since
	}

	rows, err := h.repo.Summary(*sincePtr)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "window_hours": windowHours, "rows": rows, "count": len(rows)})
}

// GET /api/v1/notifications/queue/recent?limit=100&status=pending
func (h *NotificationQueueHandler) Recent(c *gin.Context) {
	limit := 100
	if v := c.Query("limit"); v != "" {
		if parsed, err := parseInt(v); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	var status *string
	if v := c.Query("status"); v != "" {
		vv := v
		status = &vv
	}
	var since *time.Time
	if v := c.Query("since"); v != "" {
		parsed, err := time.Parse(time.RFC3339, v)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "since must be RFC3339 timestamp"})
			return
		}
		since = &parsed
	}

	items, err := h.repo.Recent(limit, status, since)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "items": items, "count": len(items)})
}

// GET /api/v1/notifications/queue/by-correlation/:correlation_id?limit=200
func (h *NotificationQueueHandler) ByCorrelationID(c *gin.Context) {
	corr := c.Param("correlation_id")
	if corr == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "correlation_id is required"})
		return
	}
	limit := 200
	if v := c.Query("limit"); v != "" {
		if parsed, err := parseInt(v); err == nil && parsed > 0 {
			limit = parsed
		}
	}

	items, err := h.repo.ByCorrelationID(corr, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "correlation_id": corr, "items": items, "count": len(items)})
}
