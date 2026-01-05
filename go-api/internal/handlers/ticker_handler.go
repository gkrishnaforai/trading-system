package handlers

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/services"
)

type TickerHandler struct {
	tickerService *services.TickerService
}

func NewTickerHandler(tickerService *services.TickerService) *TickerHandler {
	return &TickerHandler{
		tickerService: tickerService,
	}
}

// SearchTickers handles GET /api/v1/tickers/search?q=...&limit=20
func (h *TickerHandler) SearchTickers(c *gin.Context) {
	query := c.Query("q")
	if query == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Query parameter 'q' is required"})
		return
	}
	limitStr := c.Query("limit")
	limit := 20
	if limitStr != "" {
		if parsed, err := strconv.Atoi(limitStr); err == nil && parsed > 0 {
			limit = parsed
		}
	}

	tickers, err := h.tickerService.SearchTickers(c.Request.Context(), query, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"tickers": tickers})
}

// GetTicker handles GET /api/v1/tickers/:symbol
func (h *TickerHandler) GetTicker(c *gin.Context) {
	symbol := c.Param("symbol")
	if symbol == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Symbol is required"})
		return
	}
	ticker, err := h.tickerService.GetTickerBySymbol(c.Request.Context(), symbol)
	if err != nil {
		if err.Error() == "ticker not found for symbol: "+symbol {
			c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		} else {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		}
		return
	}
	c.JSON(http.StatusOK, ticker)
}
