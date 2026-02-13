package handlers

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/trading-system/go-api/internal/models"
	"github.com/trading-system/go-api/internal/repositories"
	"github.com/trading-system/go-api/internal/services"
)

type ScheduleHandler struct {
	repo      *repositories.ScheduleRepository
	scheduler *services.SchedulerService
	auditRepo *repositories.IngestionAuditRepository
}

func NewScheduleHandler(repo *repositories.ScheduleRepository, scheduler *services.SchedulerService, auditRepo *repositories.IngestionAuditRepository) *ScheduleHandler {
	return &ScheduleHandler{repo: repo, scheduler: scheduler, auditRepo: auditRepo}
}

func (h *ScheduleHandler) List(c *gin.Context) {
	items, err := h.repo.List(200)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "schedules": items, "count": len(items)})
}

func (h *ScheduleHandler) Get(c *gin.Context) {
	id := c.Param("schedule_id")
	if _, err := uuid.Parse(id); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "schedule_id must be a valid UUID"})
		return
	}
	item, err := h.repo.Get(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "schedule": item})
}

type CreateScheduleRequest struct {
	Kind           string         `json:"kind"`
	PortfolioID    string         `json:"portfolio_id"`
	Profile        string         `json:"profile"`
	CronExpression string         `json:"cron_expression"`
	Timezone       string         `json:"timezone"`
	Enabled        *bool          `json:"enabled"`
	Config         map[string]any `json:"config"`
}

func (h *ScheduleHandler) Create(c *gin.Context) {
	var req CreateScheduleRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if _, err := uuid.Parse(req.PortfolioID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "portfolio_id must be a valid UUID"})
		return
	}
	kind := strings.TrimSpace(strings.ToLower(req.Kind))
	if kind == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "kind is required"})
		return
	}
	cronExpr := strings.TrimSpace(req.CronExpression)
	if cronExpr == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "cron_expression is required"})
		return
	}
	tz := strings.TrimSpace(req.Timezone)
	if tz == "" {
		tz = "UTC"
	}
	enabled := true
	if req.Enabled != nil {
		enabled = *req.Enabled
	}

	next, err := h.scheduler.NextRunAt(cronExpr, tz, time.Now().UTC())
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	cfgBytes := []byte("{}")
	if req.Config != nil {
		b, _ := jsonMarshal(req.Config)
		if len(b) > 0 {
			cfgBytes = b
		}
	}

	s := &models.Schedule{
		Kind:           kind,
		PortfolioID:    req.PortfolioID,
		Profile:        strings.TrimSpace(req.Profile),
		CronExpression: cronExpr,
		Timezone:       tz,
		Enabled:        enabled,
		Config:         cfgBytes,
		NextRunAt:      &next,
	}
	if err := h.repo.Create(s); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, gin.H{"success": true, "schedule": s})
}

type UpdateScheduleRequest struct {
	Kind           *string        `json:"kind"`
	PortfolioID    *string        `json:"portfolio_id"`
	Profile        *string        `json:"profile"`
	CronExpression *string        `json:"cron_expression"`
	Timezone       *string        `json:"timezone"`
	Enabled        *bool          `json:"enabled"`
	Config         map[string]any `json:"config"`
}

func (h *ScheduleHandler) Update(c *gin.Context) {
	id := c.Param("schedule_id")
	if _, err := uuid.Parse(id); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "schedule_id must be a valid UUID"})
		return
	}
	current, err := h.repo.Get(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	var req UpdateScheduleRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	updates := map[string]any{}
	cronExpr := current.CronExpression
	tz := current.Timezone
	if req.Kind != nil {
		updates["kind"] = strings.TrimSpace(strings.ToLower(*req.Kind))
	}
	if req.PortfolioID != nil {
		if _, err := uuid.Parse(*req.PortfolioID); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "portfolio_id must be a valid UUID"})
			return
		}
		updates["portfolio_id"] = strings.TrimSpace(*req.PortfolioID)
	}
	if req.Profile != nil {
		updates["profile"] = strings.TrimSpace(*req.Profile)
	}
	if req.CronExpression != nil {
		cronExpr = strings.TrimSpace(*req.CronExpression)
		updates["cron_expression"] = cronExpr
	}
	if req.Timezone != nil {
		tz = strings.TrimSpace(*req.Timezone)
		if tz == "" {
			tz = "UTC"
		}
		updates["timezone"] = tz
	}
	if req.Enabled != nil {
		updates["enabled"] = *req.Enabled
	}
	if req.Config != nil {
		b, _ := jsonMarshal(req.Config)
		updates["config"] = string(b)
	}

	// Recompute next_run_at if cron or timezone changed.
	if req.CronExpression != nil || req.Timezone != nil {
		next, err := h.scheduler.NextRunAt(cronExpr, tz, time.Now().UTC())
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		updates["next_run_at"] = next
	}

	if err := h.repo.Update(id, updates); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	updated, _ := h.repo.Get(id)
	c.JSON(http.StatusOK, gin.H{"success": true, "schedule": updated})
}

func (h *ScheduleHandler) Delete(c *gin.Context) {
	id := c.Param("schedule_id")
	if _, err := uuid.Parse(id); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "schedule_id must be a valid UUID"})
		return
	}
	if err := h.repo.Delete(id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true})
}

func (h *ScheduleHandler) RunNow(c *gin.Context) {
	id := c.Param("schedule_id")
	if _, err := uuid.Parse(id); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "schedule_id must be a valid UUID"})
		return
	}
	item, err := h.repo.Get(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	runID, err := h.scheduler.RunOnce(*item)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "run_id": runID, "error": err.Error()})
		return
	}
	c.JSON(http.StatusAccepted, gin.H{"success": true, "run_id": runID})
}

func (h *ScheduleHandler) MakeDueNow(c *gin.Context) {
	id := c.Param("schedule_id")
	if _, err := uuid.Parse(id); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "schedule_id must be a valid UUID"})
		return
	}
	// Set next_run_at slightly in the past so the next tick will pick it up.
	when := time.Now().UTC().Add(-5 * time.Second)
	if err := h.repo.Update(id, map[string]any{"next_run_at": when}); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"success": false, "error": err.Error()})
		return
	}
	item, _ := h.repo.Get(id)
	c.JSON(http.StatusOK, gin.H{"success": true, "schedule": item})
}

func (h *ScheduleHandler) ListRuns(c *gin.Context) {
	id := c.Param("schedule_id")
	if _, err := uuid.Parse(id); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "schedule_id must be a valid UUID"})
		return
	}
	if h.auditRepo == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "audit repository not configured"})
		return
	}
	limit := 50
	if v := c.Query("limit"); v != "" {
		if parsed, err := parseInt(v); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	runs, err := h.auditRepo.ListRunsByScheduleID(id, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"success": true, "schedule_id": id, "runs": runs, "count": len(runs)})
}

func jsonMarshal(v any) ([]byte, error) {
	b, err := json.Marshal(v)
	if err != nil {
		return []byte("{}"), err
	}
	if len(b) == 0 {
		return []byte("{}"), nil
	}
	return b, nil
}
