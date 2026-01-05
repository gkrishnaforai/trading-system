package handlers

import (
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/trading-system/go-api/internal/models"
	"github.com/trading-system/go-api/internal/services"
)

type PortfolioHandler struct {
	portfolioService *services.PortfolioService
}

func NewPortfolioHandler(portfolioService *services.PortfolioService) *PortfolioHandler {
	return &PortfolioHandler{
		portfolioService: portfolioService,
	}
}

// GetPortfolios handles GET /api/v1/portfolios/user/:user_id
func (h *PortfolioHandler) GetPortfolios(c *gin.Context) {
	userID := c.Param("user_id")
	if _, err := uuid.Parse(userID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "user_id must be a valid UUID"})
		return
	}
	resp, err := h.portfolioService.GetPortfolios(userID)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			c.JSON(http.StatusOK, gin.H{"user_id": userID, "portfolios": []models.Portfolio{}, "count": 0})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, resp)
}

// GetPortfolio handles GET /api/v1/portfolio/:user_id/:portfolio_id
func (h *PortfolioHandler) GetPortfolio(c *gin.Context) {
	userID := c.Param("user_id")
	portfolioID := c.Param("portfolio_id")
	if _, err := uuid.Parse(userID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "user_id must be a valid UUID"})
		return
	}

	// Get subscription level from query or default to basic
	subscriptionLevel := c.Query("subscription_level")
	if subscriptionLevel == "" {
		subscriptionLevel = "basic"
	}

	portfolio, err := h.portfolioService.GetPortfolio(userID, portfolioID, subscriptionLevel)
	if err != nil {
		// Check if it's a "not found" error - return 200 with no data message
		if strings.Contains(err.Error(), "not found") {
			c.JSON(http.StatusOK, gin.H{
				"user_id":        userID,
				"portfolio_id":   portfolioID,
				"data_available": false,
				"message":        err.Error(),
			})
			return
		}
		// Other errors are server errors
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, portfolio)
}

// CreatePortfolio handles POST /api/v1/portfolio/:user_id
func (h *PortfolioHandler) CreatePortfolio(c *gin.Context) {
	userID := c.Param("user_id")
	if _, err := uuid.Parse(userID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "user_id must be a valid UUID"})
		return
	}
	log.Printf("INFO: Creating portfolio for user %s", userID)

	var req struct {
		PortfolioName string  `json:"portfolio_name" binding:"required"`
		Notes         *string `json:"notes,omitempty"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		log.Printf("ERROR: Invalid request body for user %s: %v", userID, err)
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	log.Printf("INFO: Portfolio name: %s, Notes provided: %v", req.PortfolioName, req.Notes != nil)

	portfolio, err := h.portfolioService.CreatePortfolio(userID, req.PortfolioName, req.Notes)
	if err != nil {
		log.Printf("ERROR: Failed to create portfolio for user %s: %v", userID, err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	log.Printf("INFO: Successfully created portfolio %s for user %s", portfolio.ID, userID)
	c.JSON(http.StatusCreated, portfolio)
}

// UpdatePortfolio handles PUT /api/v1/portfolio/:user_id/:portfolio_id
func (h *PortfolioHandler) UpdatePortfolio(c *gin.Context) {
	userID := c.Param("user_id")
	portfolioID := c.Param("portfolio_id")
	if _, err := uuid.Parse(userID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "user_id must be a valid UUID"})
		return
	}

	var req struct {
		PortfolioName *string `json:"portfolio_name,omitempty"`
		Notes         *string `json:"notes,omitempty"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if req.PortfolioName == nil && req.Notes == nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "At least one field must be provided for update"})
		return
	}

	if err := h.portfolioService.UpdatePortfolio(userID, portfolioID, req.PortfolioName, req.Notes); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Portfolio updated successfully"})
}

// DeletePortfolio handles DELETE /api/v1/portfolio/:user_id/:portfolio_id
func (h *PortfolioHandler) DeletePortfolio(c *gin.Context) {
	userID := c.Param("user_id")
	portfolioID := c.Param("portfolio_id")
	if _, err := uuid.Parse(userID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "user_id must be a valid UUID"})
		return
	}

	if err := h.portfolioService.DeletePortfolio(userID, portfolioID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Portfolio deleted successfully"})
}

// CreateHolding handles POST /api/v1/portfolio/:user_id/:portfolio_id/holdings
func (h *PortfolioHandler) CreateHolding(c *gin.Context) {
	portfolioID := c.Param("portfolio_id")

	var req struct {
		StockSymbol   string  `json:"stock_symbol" binding:"required"`
		Quantity      float64 `json:"quantity" binding:"required"`
		AvgEntryPrice float64 `json:"avg_entry_price" binding:"required"`
		PositionType  string  `json:"position_type" binding:"required"`
		StrategyTag   *string `json:"strategy_tag,omitempty"`
		Notes         *string `json:"notes,omitempty"`
		PurchaseDate  string  `json:"purchase_date" binding:"required"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	_ = time.Now()
	_ = req.PositionType
	_ = req.StrategyTag
	_ = req.Notes
	_ = req.PurchaseDate

	pos := &models.PortfolioPosition{
		PortfolioID: portfolioID,
		Symbol:      req.StockSymbol,
		Quantity:    req.Quantity,
		AvgPrice:    req.AvgEntryPrice,
	}

	if err := h.portfolioService.CreateHolding(portfolioID, pos); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, pos)
}

// UpdateHolding handles PUT /api/v1/holdings/:holding_id
func (h *PortfolioHandler) UpdateHolding(c *gin.Context) {
	holdingID := c.Param("holding_id")

	var req map[string]interface{}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.portfolioService.UpdateHolding(holdingID, req); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Holding updated successfully"})
}

// DeleteHolding handles DELETE /api/v1/holdings/:holding_id
func (h *PortfolioHandler) DeleteHolding(c *gin.Context) {
	holdingID := c.Param("holding_id")

	if err := h.portfolioService.DeleteHolding(holdingID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Holding deleted successfully"})
}
