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

type TradingDecisionV3Handler struct {
	auditRepo   *repositories.IngestionAuditRepository
	jobQueue    *services.RedisStreamJobQueue
	useJobQueue bool
}

func NewTradingDecisionV3Handler(auditRepo *repositories.IngestionAuditRepository, jobQueue *services.RedisStreamJobQueue, useJobQueue bool) *TradingDecisionV3Handler {
	return &TradingDecisionV3Handler{auditRepo: auditRepo, jobQueue: jobQueue, useJobQueue: useJobQueue}
}

type CreatePortfolioDecisionV3RunRequest struct {
	Symbols  []string `json:"symbols"`
	AsOfDate string   `json:"as_of_date"`
}

func (h *TradingDecisionV3Handler) CreatePortfolioDecisionRun(c *gin.Context) {
	portfolioID := c.Param("portfolio_id")
	if _, err := uuid.Parse(portfolioID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "portfolio_id must be a valid UUID"})
		return
	}

	if !h.useJobQueue || h.jobQueue == nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "job queue not enabled"})
		return
	}

	var req CreatePortfolioDecisionV3RunRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	symbols := req.Symbols
	if len(symbols) == 0 {
		resolved, err := h.auditRepo.SymbolsForPortfolio(portfolioID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		symbols = resolved
	}
	if len(symbols) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "no symbols resolved"})
		return
	}

	asOfDate := strings.TrimSpace(req.AsOfDate)

	runID := uuid.New().String()
	_ = h.auditRepo.CreateRun(runID, "running", map[string]any{
		"operation":    "trading_decision_v3",
		"portfolio_id": portfolioID,
		"symbols":      symbols,
		"as_of_date":   asOfDate,
		"requested_at": time.Now().UTC().Format(time.RFC3339),
		"triggered_by": "api",
	})

	parentCtx := context.Background()
	ctx, cancel := context.WithTimeout(parentCtx, 15*time.Second)
	defer cancel()

	_ = h.jobQueue.SetRunRemaining(ctx, runID, len(symbols))

	enqueueFailed := 0
	for _, sym := range symbols {
		symCopy := strings.TrimSpace(strings.ToUpper(sym))
		if symCopy == "" {
			enqueueFailed += 1
			continue
		}
		if _, err := h.jobQueue.EnqueueTradingDecisionV3Job(ctx, services.TradingDecisionV3JobPayload{
			RunID:       runID,
			PortfolioID: portfolioID,
			Symbol:      symCopy,
			AsOfDate:    asOfDate,
			Attempt:     1,
			MaxAttempts: 3,
		}); err != nil {
			enqueueFailed += 1
			errMsg := err.Error()
			_ = h.auditRepo.CreateEvent(runID, "error", "queue_enqueue_failed", &symCopy, nil, nil, &errMsg, nil, nil)
			continue
		}
		m := "job enqueued"
		_ = h.auditRepo.CreateEvent(runID, "info", "queue_job_enqueued", &symCopy, nil, &m, nil, map[string]any{"job_type": "trading_decision_v3"}, nil)
	}

	if enqueueFailed > 0 {
		failMsg := "some jobs failed to enqueue"
		_ = h.auditRepo.CreateEvent(runID, "error", "queue_enqueue_partial_failure", nil, nil, nil, &failMsg, map[string]any{"failed": enqueueFailed}, nil)
		_ = h.auditRepo.UpdateRunStatus(runID, "failed", map[string]any{"go_error": failMsg, "enqueue_failed": enqueueFailed})
		c.JSON(http.StatusAccepted, gin.H{"success": true, "run_id": runID, "portfolio_id": portfolioID, "status": "failed"})
		return
	}

	fin := "enqueue completed"
	_ = h.auditRepo.CreateEvent(runID, "info", "queue_enqueue_finished", nil, nil, &fin, nil, map[string]any{"symbols_count": len(symbols)}, nil)
	c.JSON(http.StatusAccepted, gin.H{"success": true, "run_id": runID, "portfolio_id": portfolioID, "status": "running"})
}
