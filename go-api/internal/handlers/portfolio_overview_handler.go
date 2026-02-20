package handlers

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/repositories"
)

type PortfolioOverviewHandler struct {
	overviewRepo *repositories.PortfolioOverviewRepository
}

func NewPortfolioOverviewHandler(overviewRepo *repositories.PortfolioOverviewRepository) *PortfolioOverviewHandler {
	return &PortfolioOverviewHandler{overviewRepo: overviewRepo}
}

// GetOverview handles GET /api/v1/portfolios/:portfolio_id/overview?window_days=7&subscription_level=basic
// Returns aggregated portfolio context for the home screen.
func (h *PortfolioOverviewHandler) GetOverview(c *gin.Context) {
	portfolioID := c.Param("portfolio_id")
	windowDays := 7
	if wd := c.Query("window_days"); wd != "" {
		if parsed, err := strconv.Atoi(wd); err == nil && parsed > 0 && parsed <= 365 {
			windowDays = parsed
		}
	}
	subscriptionLevel := c.Query("subscription_level")
	if subscriptionLevel == "" {
		subscriptionLevel = "basic"
	}

	overview, err := h.overviewRepo.GetOverview(portfolioID, windowDays, subscriptionLevel)
	if err != nil {
		if err.Error() == "portfolio not found: "+portfolioID {
			c.JSON(http.StatusNotFound, gin.H{"error": "portfolio not found"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, overview)
}
