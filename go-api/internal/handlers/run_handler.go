package handlers

import (
	"fmt"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/trading-system/go-api/internal/repositories"
	"github.com/trading-system/go-api/internal/services"
)

type RunHandler struct {
	runRepo *repositories.RunRepository
	worker  *services.PythonWorkerClient
}

func NewRunHandler(runRepo *repositories.RunRepository, worker *services.PythonWorkerClient) *RunHandler {
	return &RunHandler{runRepo: runRepo, worker: worker}
}

// CreateRun handles POST /api/v1/runs
// Body: { "profile_name": "monthly_portfolio_refresh_v1", "symbols": [...], "metadata": {...} }
// Returns: { "run_id": "...", "status": "pending" }
func (h *RunHandler) CreateRun(c *gin.Context) {
	var req struct {
		ProfileName string         `json:"profile_name" binding:"required"`
		Symbols     []string       `json:"symbols,omitempty"`
		Metadata    map[string]any `json:"metadata,omitempty"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	// Ensure a run_id exists
	runID := uuid.New().String()
	// Store initial metadata
	metadata := req.Metadata
	if metadata == nil {
		metadata = make(map[string]any)
	}
	metadata["profile_name"] = req.ProfileName
	metadata["symbols"] = req.Symbols

	if _, err := h.runRepo.CreateRun(runID, "pending", metadata); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	// Kick off python-worker run (fire-and-forget for now)
	go func() {
		workerReq := map[string]any{
			"run_id":       runID,
			"profile_name": req.ProfileName,
			"symbols":      req.Symbols,
		}
		// TODO: make this endpoint and handle errors
		h.worker.PostJSON("/worker/run", workerReq)
	}()

	c.JSON(http.StatusAccepted, gin.H{"run_id": runID, "status": "pending"})
}

// GetRun handles GET /api/v1/runs/:run_id
// Returns the run record (status, timestamps, metadata)
func (h *RunHandler) GetRun(c *gin.Context) {
	runID := c.Param("run_id")
	if _, err := uuid.Parse(runID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "run_id must be a valid UUID"})
		return
	}
	run, err := h.runRepo.GetRun(runID)
	if err != nil {
		if err.Error() == "run not found: "+runID {
			c.JSON(http.StatusNotFound, gin.H{"error": "run not found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, run)
}

// ListRuns handles GET /api/v1/runs?limit=N
// Returns recent runs
func (h *RunHandler) ListRuns(c *gin.Context) {
	limit := 20
	if l := c.Query("limit"); l != "" {
		if parsed, err := parseLimit(l); err == nil && parsed > 0 && parsed <= 200 {
			limit = parsed
		}
	}
	runs, err := h.runRepo.ListRuns(limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"runs": runs})
}

// parseLimit helper
func parseLimit(s string) (int, error) {
	var i int
	_, err := fmt.Sscanf(s, "%d", &i)
	return i, err
}
