package handlers

import (
	"fmt"
	"log"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/models"
	"github.com/trading-system/go-api/internal/services"
)

type WatchlistHandler struct {
	watchlistService *services.WatchlistService
}

func NewWatchlistHandler(watchlistService *services.WatchlistService) *WatchlistHandler {
	return &WatchlistHandler{
		watchlistService: watchlistService,
	}
}

// CreateWatchlist handles POST /api/v1/watchlists
func (h *WatchlistHandler) CreateWatchlist(c *gin.Context) {
	userID := c.Query("user_id")
	if userID == "" {
		log.Printf("ERROR: CreateWatchlist called without user_id")
		c.JSON(http.StatusBadRequest, gin.H{"error": "user_id is required"})
		return
	}
	
	log.Printf("INFO: Creating watchlist for user %s", userID)
	
	var req struct {
		WatchlistName          string  `json:"watchlist_name" binding:"required"`
		Description           *string `json:"description,omitempty"`
		Tags                  *string `json:"tags,omitempty"`
		IsDefault             bool    `json:"is_default"`
		SubscriptionLevelRequired string `json:"subscription_level_required"`
	}
	
	if err := c.ShouldBindJSON(&req); err != nil {
		log.Printf("ERROR: Invalid request body for user %s: %v", userID, err)
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	
	subscriptionLevel := req.SubscriptionLevelRequired
	if subscriptionLevel == "" {
		subscriptionLevel = "basic"
		log.Printf("INFO: No subscription_level_required provided, defaulting to 'basic'")
	}
	
	// Validate subscription level - fail fast if invalid
	validLevels := map[string]bool{"basic": true, "pro": true, "elite": true}
	if !validLevels[subscriptionLevel] {
		log.Printf("ERROR: Invalid subscription_level_required '%s' for user %s", subscriptionLevel, userID)
		c.JSON(http.StatusBadRequest, gin.H{
			"error": fmt.Sprintf("invalid subscription_level_required: %s. Must be one of: basic, pro, elite", subscriptionLevel),
		})
		return
	}
	
	log.Printf("INFO: Creating watchlist '%s' for user %s with subscription_level_required: %s", 
		req.WatchlistName, userID, subscriptionLevel)
	
	watchlist, err := h.watchlistService.CreateWatchlist(
		userID,
		req.WatchlistName,
		req.Description,
		req.Tags,
		req.IsDefault,
		subscriptionLevel,
	)
	if err != nil {
		log.Printf("ERROR: Failed to create watchlist for user %s: %v", userID, err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	log.Printf("INFO: Successfully created watchlist %s for user %s", watchlist.WatchlistID, userID)
	c.JSON(http.StatusCreated, watchlist)
}

// GetWatchlists handles GET /api/v1/watchlists/user/:user_id
func (h *WatchlistHandler) GetWatchlists(c *gin.Context) {
	userID := c.Param("user_id")
	
	subscriptionLevel := c.Query("subscription_level")
	if subscriptionLevel == "" {
		subscriptionLevel = "basic"
	}
	
	watchlists, err := h.watchlistService.GetWatchlists(userID, subscriptionLevel)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			c.JSON(http.StatusOK, gin.H{
				"user_id": userID,
				"watchlists": []models.Watchlist{},
				"count": 0,
			})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{
		"watchlists": watchlists,
		"count":      len(watchlists),
	})
}

// GetWatchlist handles GET /api/v1/watchlists/:watchlist_id
func (h *WatchlistHandler) GetWatchlist(c *gin.Context) {
	watchlistID := c.Param("watchlist_id")
	
	subscriptionLevel := c.Query("subscription_level")
	if subscriptionLevel == "" {
		subscriptionLevel = "basic"
	}
	
	watchlist, err := h.watchlistService.GetWatchlist(watchlistID, subscriptionLevel)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			c.JSON(http.StatusOK, gin.H{
				"watchlist_id": watchlistID,
				"data_available": false,
				"message": err.Error(),
			})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, watchlist)
}

// UpdateWatchlist handles PUT /api/v1/watchlists/:watchlist_id
func (h *WatchlistHandler) UpdateWatchlist(c *gin.Context) {
	watchlistID := c.Param("watchlist_id")
	
	var req map[string]interface{}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	
	if err := h.watchlistService.UpdateWatchlist(watchlistID, req); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"message": "Watchlist updated successfully"})
}

// DeleteWatchlist handles DELETE /api/v1/watchlists/:watchlist_id
func (h *WatchlistHandler) DeleteWatchlist(c *gin.Context) {
	watchlistID := c.Param("watchlist_id")
	
	if err := h.watchlistService.DeleteWatchlist(watchlistID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"message": "Watchlist deleted successfully"})
}

// AddItem handles POST /api/v1/watchlists/:watchlist_id/items
func (h *WatchlistHandler) AddItem(c *gin.Context) {
	watchlistID := c.Param("watchlist_id")
	
	var req struct {
		StockSymbol string  `json:"stock_symbol" binding:"required"`
		Notes       *string `json:"notes,omitempty"`
		Priority    int     `json:"priority"`
		Tags        *string `json:"tags,omitempty"`
	}
	
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	
	item, err := h.watchlistService.AddItem(
		watchlistID,
		req.StockSymbol,
		req.Notes,
		req.Priority,
		req.Tags,
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusCreated, item)
}

// UpdateItem handles PUT /api/v1/watchlist-items/:item_id
func (h *WatchlistHandler) UpdateItem(c *gin.Context) {
	itemID := c.Param("item_id")
	
	var req map[string]interface{}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	
	if err := h.watchlistService.UpdateItem(itemID, req); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"message": "Watchlist item updated successfully"})
}

// RemoveItem handles DELETE /api/v1/watchlist-items/:item_id
func (h *WatchlistHandler) RemoveItem(c *gin.Context) {
	itemID := c.Param("item_id")
	
	if err := h.watchlistService.RemoveItem(itemID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusOK, gin.H{"message": "Watchlist item removed successfully"})
}

// MoveToPortfolio handles POST /api/v1/watchlists/:watchlist_id/move-to-portfolio
func (h *WatchlistHandler) MoveToPortfolio(c *gin.Context) {
	watchlistID := c.Param("watchlist_id")
	
	var req struct {
		ItemID        string                      `json:"item_id" binding:"required"`
		MoveRequest   models.MoveToPortfolioRequest `json:"move_request" binding:"required"`
	}
	
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	
	holding, err := h.watchlistService.MoveToPortfolio(
		watchlistID,
		req.ItemID,
		&req.MoveRequest,
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	
	c.JSON(http.StatusCreated, gin.H{
		"message": "Stock moved to portfolio successfully",
		"holding": holding,
	})
}

