package handlers

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/trading-system/go-api/internal/repositories"
	"github.com/trading-system/go-api/internal/services"
)

type AgentRunHandler struct {
	runRepo *repositories.RunRepository
	worker  *services.PythonWorkerClient
}

func NewAgentRunHandler(runRepo *repositories.RunRepository, worker *services.PythonWorkerClient) *AgentRunHandler {
	return &AgentRunHandler{runRepo: runRepo, worker: worker}
}

func (h *AgentRunHandler) Catalog(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"agents": []gin.H{
		{"id": "market_regime", "name": "Market Regime", "scopes": []string{"market"}, "status": "available"},
		{"id": "swing_review", "name": "Swing Review", "scopes": []string{"stock", "portfolio"}, "status": "available"},
		{"id": "fundamental_intelligence", "name": "Fundamental Intelligence", "scopes": []string{"stock"}, "status": "available"},
		{"id": "event_review", "name": "Event Review", "scopes": []string{"market", "stock"}, "status": "available"},
		{"id": "risk_assessment", "name": "Risk Assessment", "scopes": []string{"stock"}, "status": "available"},
		{"id": "portfolio_review", "name": "Portfolio Review", "scopes": []string{"portfolio"}, "status": "manual_only"},
		{"id": "day_trading", "name": "Day Trading", "scopes": []string{"market", "stock"}, "status": "unavailable_intraday_contract"},
		{"id": "live_execution", "name": "Live Execution", "scopes": []string{"portfolio", "stock"}, "status": "disabled"},
	}})
}

func (h *AgentRunHandler) Run(c *gin.Context) {
	var req map[string]interface{}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	mode, _ := req["mode"].(string)
	if mode == "live" {
		c.JSON(http.StatusForbidden, gin.H{"error": "live agent execution is disabled"})
		return
	}
	runID := uuid.New().String()
	metadata := map[string]interface{}{"workflow": "agent_run", "request": req}
	if _, err := h.runRepo.CreateRun(runID, "running", metadata); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	ctx := c.Request.Context()
	result, err := h.worker.RunAgent(ctx, req)
	finished := time.Now().UTC()
	if err != nil {
		_ = h.runRepo.UpdateRunMetadata(runID, map[string]interface{}{"error": err.Error()})
		_ = h.runRepo.UpdateRunStatus(runID, "failed", &finished)
		c.JSON(http.StatusBadGateway, gin.H{"run_id": runID, "status": "failed", "error": err.Error()})
		return
	}

	// Python returns an execution envelope. The Go BFF exposes the canonical
	// graph result directly so all UI clients share one response shape.
	graphResult := result
	if nested, ok := result["result"].(map[string]interface{}); ok {
		graphResult = nested
	}
	_ = h.runRepo.UpdateRunStatus(runID, "completed", &finished)
	agentName, _ := result["agent"].(string)
	_ = h.runRepo.UpdateRunMetadata(runID, map[string]interface{}{
		"agent":        agentName,
		"agent_result": graphResult,
		"completed_at": finished,
	})
	response := gin.H{"run_id": runID, "status": "completed", "result": graphResult}
	if agentName != "" {
		response["agent"] = agentName
	}
	c.JSON(http.StatusOK, response)
}
