package handlers

import (
	"context"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/trading-system/go-api/internal/repositories"
	"github.com/trading-system/go-api/internal/services"
)

type PortfolioRebalanceRunHandler struct {
	auditRepo   *repositories.IngestionAuditRepository
	jobQueue    *services.RedisStreamJobQueue
	useJobQueue bool
}

func NewPortfolioRebalanceRunHandler(auditRepo *repositories.IngestionAuditRepository, jobQueue *services.RedisStreamJobQueue, useJobQueue bool) *PortfolioRebalanceRunHandler {
	return &PortfolioRebalanceRunHandler{auditRepo: auditRepo, jobQueue: jobQueue, useJobQueue: useJobQueue}
}

type CreatePortfolioRebalanceRunRequest struct {
	Profile    string   `json:"profile"`
	TargetDate string   `json:"target_date"`
	Symbols    []string `json:"symbols"`
}

// POST /api/v1/portfolios/:portfolio_id/rebalance-run
func (h *PortfolioRebalanceRunHandler) CreateRun(c *gin.Context) {
	portfolioID := c.Param("portfolio_id")
	if _, err := uuid.Parse(portfolioID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "portfolio_id must be a valid UUID"})
		return
	}

	var req CreatePortfolioRebalanceRunRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	profile := strings.TrimSpace(req.Profile)
	if profile == "" {
		profile = string(services.AnalysisProfileWeeklyRebalance)
	}
	resolvedProfile, err := services.ResolveAnalysisProfile(profile)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if resolvedProfile != services.AnalysisProfileWeeklyRebalance {
		c.JSON(http.StatusBadRequest, gin.H{"error": "unsupported rebalance profile"})
		return
	}

	targetDate := strings.TrimSpace(req.TargetDate)
	if targetDate == "" {
		targetDate = time.Now().UTC().Format("2006-01-02")
	}

	// Rebalance is portfolio-level; symbols are optional but we record them if provided.
	symbols := []string{}
	if len(req.Symbols) > 0 {
		valid, _ := sanitizeSymbols(req.Symbols)
		symbols = valid
	}

	runID := uuid.New().String()
	_ = h.auditRepo.CreateRun(runID, "running", map[string]any{
		"operation":    "portfolio_rebalance",
		"portfolio_id": portfolioID,
		"symbols":      symbols,
		"profile":      string(resolvedProfile),
		"target_date":  targetDate,
		"requested_at": time.Now().UTC().Format(time.RFC3339),
	})

	if !h.useJobQueue || h.jobQueue == nil {
		msg := "job queue not enabled"
		_ = h.auditRepo.CreateEvent(runID, "error", "queue_not_enabled", nil, nil, nil, &msg, map[string]any{"enable_job_queue": false}, nil)
		_ = h.auditRepo.UpdateRunStatus(runID, "failed", map[string]any{"go_error": msg})
		c.JSON(http.StatusServiceUnavailable, gin.H{"success": false, "run_id": runID, "status": "failed", "error": msg})
		return
	}

	parentCtx := context.Background()
	ctx, cancel := context.WithTimeout(parentCtx, 15*time.Second)
	defer cancel()

	startMsg := "enqueuing portfolio rebalance job"
	_ = h.auditRepo.CreateEvent(runID, "info", "queue_enqueue_started", nil, nil, &startMsg, nil, map[string]any{"profile": string(resolvedProfile)}, nil)

	_ = h.jobQueue.SetRunRemaining(ctx, runID, 1)

	_, err = h.jobQueue.EnqueuePortfolioRebalanceJob(ctx, services.PortfolioRebalanceJobPayload{
		RunID:       runID,
		PortfolioID: portfolioID,
		TargetDate:  targetDate,
		Profile:     string(resolvedProfile),
		Attempt:     1,
		MaxAttempts: 3,
	})
	if err != nil {
		errMsg := err.Error()
		_ = h.auditRepo.CreateEvent(runID, "error", "queue_enqueue_failed", nil, nil, nil, &errMsg, nil, nil)
		_ = h.auditRepo.UpdateRunStatus(runID, "failed", map[string]any{"go_error": errMsg})
		c.JSON(http.StatusAccepted, gin.H{"success": true, "run_id": runID, "portfolio_id": portfolioID, "status": "failed", "profile": string(resolvedProfile), "target_date": targetDate})
		return
	}

	fin := "enqueue completed"
	_ = h.auditRepo.CreateEvent(runID, "info", "queue_enqueue_finished", nil, nil, &fin, nil, map[string]any{"profile": string(resolvedProfile)}, nil)

	c.JSON(http.StatusAccepted, gin.H{
		"success":      true,
		"run_id":       runID,
		"portfolio_id": portfolioID,
		"status":       "running",
		"profile":      string(resolvedProfile),
		"target_date":  targetDate,
	})
}
