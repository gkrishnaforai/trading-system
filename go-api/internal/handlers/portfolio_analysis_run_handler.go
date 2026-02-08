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

type PortfolioAnalysisRunHandler struct {
	auditRepo   *repositories.IngestionAuditRepository
	jobQueue    *services.RedisStreamJobQueue
	useJobQueue bool
}

func NewPortfolioAnalysisRunHandler(auditRepo *repositories.IngestionAuditRepository, jobQueue *services.RedisStreamJobQueue, useJobQueue bool) *PortfolioAnalysisRunHandler {
	return &PortfolioAnalysisRunHandler{auditRepo: auditRepo, jobQueue: jobQueue, useJobQueue: useJobQueue}
}

type CreatePortfolioAnalysisRunRequest struct {
	TargetDate string `json:"target_date"`
	AssetType  string `json:"asset_type"`
}

// POST /api/v1/portfolios/:portfolio_id/analysis-run
func (h *PortfolioAnalysisRunHandler) CreateRun(c *gin.Context) {
	portfolioID := c.Param("portfolio_id")
	if _, err := uuid.Parse(portfolioID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "portfolio_id must be a valid UUID"})
		return
	}

	var req CreatePortfolioAnalysisRunRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	assetType := strings.TrimSpace(req.AssetType)
	if assetType == "" {
		assetType = "stock"
	}
	assetType = strings.ToLower(assetType)

	targetDate := strings.TrimSpace(req.TargetDate)
	if targetDate == "" {
		targetDate = time.Now().UTC().Format("2006-01-02")
	}

	symbols, err := h.auditRepo.SymbolsForPortfolio(portfolioID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if len(symbols) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "no holdings found in portfolio"})
		return
	}

	runID := uuid.New().String()
	_ = h.auditRepo.CreateRun(runID, "running", map[string]any{
		"operation":    "portfolio_analysis",
		"portfolio_id": portfolioID,
		"symbols":      symbols,
		"asset_type":   assetType,
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

	startMsg := "enqueuing portfolio analysis jobs"
	_ = h.auditRepo.CreateEvent(runID, "info", "queue_enqueue_started", nil, nil, &startMsg, nil, map[string]any{"symbols_count": len(symbols)}, nil)

	_ = h.jobQueue.SetRunRemaining(ctx, runID, len(symbols))

	enqueueFailed := 0
	for _, sym := range symbols {
		symCopy := sym
		err := func() error {
			_, err := h.jobQueue.EnqueuePortfolioAnalysisJob(ctx, services.PortfolioAnalysisJobPayload{
				RunID:       runID,
				PortfolioID: portfolioID,
				Symbol:      symCopy,
				AssetType:   assetType,
				TargetDate:  targetDate,
				Attempt:     1,
				MaxAttempts: 3,
			})
			return err
		}()
		if err != nil {
			enqueueFailed += 1
			errMsg := err.Error()
			_ = h.auditRepo.CreateEvent(runID, "error", "queue_enqueue_failed", &symCopy, nil, nil, &errMsg, nil, nil)
			continue
		}
		m := "job enqueued"
		_ = h.auditRepo.CreateEvent(runID, "info", "queue_job_enqueued", &symCopy, nil, &m, nil, map[string]any{"asset_type": assetType, "target_date": targetDate}, nil)
	}

	if enqueueFailed > 0 {
		failMsg := "some jobs failed to enqueue"
		_ = h.auditRepo.CreateEvent(runID, "error", "queue_enqueue_partial_failure", nil, nil, nil, &failMsg, map[string]any{"failed": enqueueFailed}, nil)
		_ = h.auditRepo.UpdateRunStatus(runID, "failed", map[string]any{"go_error": failMsg, "enqueue_failed": enqueueFailed})
		c.JSON(http.StatusAccepted, gin.H{"success": true, "run_id": runID, "portfolio_id": portfolioID, "status": "failed", "asset_type": assetType, "target_date": targetDate})
		return
	}

	fin := "enqueue completed"
	_ = h.auditRepo.CreateEvent(runID, "info", "queue_enqueue_finished", nil, nil, &fin, nil, map[string]any{"symbols_count": len(symbols)}, nil)

	c.JSON(http.StatusAccepted, gin.H{
		"success":      true,
		"run_id":       runID,
		"portfolio_id": portfolioID,
		"status":       "running",
		"asset_type":   assetType,
		"target_date":  targetDate,
	})
}
