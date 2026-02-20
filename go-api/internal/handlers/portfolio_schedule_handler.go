package handlers

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/trading-system/go-api/internal/repositories"
)

type PortfolioScheduleHandler struct {
	repo *repositories.PortfolioScheduleRepository
}

func NewPortfolioScheduleHandler(repo *repositories.PortfolioScheduleRepository) *PortfolioScheduleHandler {
	return &PortfolioScheduleHandler{repo: repo}
}

// Request/Response models
type ScheduleCreateRequest struct {
	PortfolioID             string          `json:"portfolio_id" binding:"required"`
	ScheduleType            string          `json:"schedule_type" binding:"required,oneof=daily weekly monthly"`
	ScheduleTime            string          `json:"schedule_time" binding:"required"` // HH:MM format
	ScheduleDay             *int            `json:"schedule_day,omitempty"`
	NotificationPreferences map[string]bool `json:"notification_preferences"`
}

type ScheduleUpdateRequest struct {
	ScheduleType            string          `json:"schedule_type,omitempty" binding:"omitempty,oneof=daily weekly monthly"`
	ScheduleTime            string          `json:"schedule_time,omitempty"`
	ScheduleDay             *int            `json:"schedule_day,omitempty"`
	NotificationPreferences map[string]bool `json:"notification_preferences,omitempty"`
	IsActive                *bool           `json:"is_active,omitempty"`
}

type ToggleResponse struct {
	Success  bool   `json:"success"`
	Message  string `json:"message"`
	IsActive bool   `json:"is_active"`
}

type DeleteResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
}

// ListSchedules handles GET /api/v1/portfolio-schedules/list
func (h *PortfolioScheduleHandler) ListSchedules(c *gin.Context) {
	status := c.Query("status")
	portfolioID := c.Query("portfolio_id")
	userID := c.Query("user_id")

	response, err := h.repo.ListSchedules(c.Request.Context(), status, portfolioID, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, response)
}

// GetSchedule handles GET /api/v1/portfolio-schedules/{schedule_id}
func (h *PortfolioScheduleHandler) GetSchedule(c *gin.Context) {
	scheduleID := c.Param("schedule_id")

	// Validate UUID
	if _, err := uuid.Parse(scheduleID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid schedule ID format"})
		return
	}

	schedule, err := h.repo.GetSchedule(c.Request.Context(), scheduleID)
	if err != nil {
		if err.Error() == "schedule not found" {
			c.JSON(http.StatusNotFound, gin.H{"error": "Schedule not found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, schedule)
}

// CreateSchedule handles POST /api/v1/portfolio-schedules/
func (h *PortfolioScheduleHandler) CreateSchedule(c *gin.Context) {
	var req ScheduleCreateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Validate time format
	if _, err := time.Parse("15:04", req.ScheduleTime); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid time format. Use HH:MM"})
		return
	}

	// Set default notification preferences if not provided
	if req.NotificationPreferences == nil {
		req.NotificationPreferences = map[string]bool{"push": false, "email": true}
	}

	// Get user_id from portfolio (would need to query this)
	// For now, we'll need to call Python API to create the schedule
	// since Go API doesn't have direct access to user_id from portfolio

	// Call Python API to create schedule
	pythonResp, err := h.callPythonAPI("POST", "/api/v1/portfolio-schedules/", req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create schedule: " + err.Error()})
		return
	}

	c.JSON(http.StatusCreated, pythonResp)
}

// UpdateSchedule handles PUT /api/v1/portfolio-schedules/{schedule_id}
func (h *PortfolioScheduleHandler) UpdateSchedule(c *gin.Context) {
	scheduleID := c.Param("schedule_id")

	// Validate UUID
	if _, err := uuid.Parse(scheduleID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid schedule ID format"})
		return
	}

	var req ScheduleUpdateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Validate time format if provided
	if req.ScheduleTime != "" {
		if _, err := time.Parse("15:04", req.ScheduleTime); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid time format. Use HH:MM"})
			return
		}
	}

	// Call Python API to update schedule
	pythonResp, err := h.callPythonAPI("PUT", "/api/v1/portfolio-schedules/"+scheduleID, req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update schedule: " + err.Error()})
		return
	}

	c.JSON(http.StatusOK, pythonResp)
}

// DeleteSchedule handles DELETE /api/v1/portfolio-schedules/{schedule_id}
func (h *PortfolioScheduleHandler) DeleteSchedule(c *gin.Context) {
	scheduleID := c.Param("schedule_id")

	// Validate UUID
	if _, err := uuid.Parse(scheduleID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid schedule ID format"})
		return
	}

	// Call Python API to delete schedule
	pythonResp, err := h.callPythonAPI("DELETE", "/api/v1/portfolio-schedules/"+scheduleID, nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to delete schedule: " + err.Error()})
		return
	}

	c.JSON(http.StatusOK, pythonResp)
}

// ToggleSchedule handles POST /api/v1/portfolio-schedules/{schedule_id}/toggle
func (h *PortfolioScheduleHandler) ToggleSchedule(c *gin.Context) {
	scheduleID := c.Param("schedule_id")

	// Validate UUID
	if _, err := uuid.Parse(scheduleID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid schedule ID format"})
		return
	}

	// Call Python API to toggle schedule
	pythonResp, err := h.callPythonAPI("POST", "/api/v1/portfolio-schedules/"+scheduleID+"/toggle", nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to toggle schedule: " + err.Error()})
		return
	}

	c.JSON(http.StatusOK, pythonResp)
}

// GetScheduleOverview handles GET /api/v1/portfolio-schedules/status/overview
func (h *PortfolioScheduleHandler) GetScheduleOverview(c *gin.Context) {
	// Get overview from Go database
	overview, err := h.repo.GetScheduleOverview(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Get scheduler running status from Python API
	schedulerStatus, err := h.getPythonSchedulerStatus()
	if err == nil {
		overview.SchedulerRunning = schedulerStatus
	}

	c.JSON(http.StatusOK, overview)
}

// Helper function to call Python API
func (h *PortfolioScheduleHandler) callPythonAPI(method, endpoint string, data interface{}) (interface{}, error) {
	// This would make an HTTP call to the Python Worker API
	// For now, we'll return a placeholder response
	// In a real implementation, you'd use http.Client to call the Python API

	// Placeholder - implement actual HTTP call to Python API
	return gin.H{"success": true, "message": "Operation delegated to Python API"}, nil
}

// Helper function to get Python scheduler status
func (h *PortfolioScheduleHandler) getPythonSchedulerStatus() (bool, error) {
	// This would call the Python API to get scheduler status
	// For now, return false as placeholder
	return false, nil
}
