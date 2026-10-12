package handlers

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/repositories"
)

type PortfolioAgentHistoryHandler struct {
	repo *repositories.PortfolioAgentHistoryRepository
}

func NewPortfolioAgentHistoryHandler(repo *repositories.PortfolioAgentHistoryRepository) *PortfolioAgentHistoryHandler {
	return &PortfolioAgentHistoryHandler{repo: repo}
}

func (h *PortfolioAgentHistoryHandler) ListSnapshots(c *gin.Context) {
	portfolioID := c.Param("portfolio_id")
	snapshots, err := h.repo.ListSnapshots(portfolioID, 30)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"portfolio_id": portfolioID, "snapshots": snapshots})
}

func (h *PortfolioAgentHistoryHandler) GetSnapshot(c *gin.Context) {
	portfolioID := c.Param("portfolio_id")
	snapshotID := c.Param("snapshot_id")
	snapshot, err := h.repo.GetSnapshot(portfolioID, snapshotID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, snapshot)
}
