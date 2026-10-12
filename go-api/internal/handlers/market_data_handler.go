package handlers

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/services"
)

type MarketDataHandler struct{ worker *services.PythonWorkerClient }

func NewMarketDataHandler(worker *services.PythonWorkerClient) *MarketDataHandler {
	return &MarketDataHandler{worker: worker}
}

func (h *MarketDataHandler) LiveQuote(c *gin.Context) {
	symbol := strings.ToUpper(strings.TrimSpace(c.Param("symbol")))
	if symbol == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "symbol is required"})
		return
	}
	quote, err := h.worker.GetCanonicalLiveQuote(c.Request.Context(), symbol)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, quote)
}
