package handlers

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/services"
)

type StockHandler struct {
	stockService *services.StockService
}

func NewStockHandler(stockService *services.StockService) *StockHandler {
	return &StockHandler{
		stockService: stockService,
	}
}

// GetStock handles GET /api/v1/stock/:symbol
func (h *StockHandler) GetStock(c *gin.Context) {
	symbol := c.Param("symbol")

	// Get subscription level from query or default to basic
	subscriptionLevel := c.Query("subscription_level")
	if subscriptionLevel == "" {
		subscriptionLevel = "basic"
	}

	stock, err := h.stockService.GetStock(symbol, subscriptionLevel)
	if err != nil {
		// Check if it's a "not found" error - return 200 with no data message
		if strings.Contains(err.Error(), "not found") {
			c.JSON(http.StatusOK, gin.H{
				"symbol": symbol,
				"data_available": false,
				"message": "No data available for this symbol. Please run the batch worker to fetch market data first.",
				"hint": "Run: docker-compose exec python-worker python -c \"from app.database import init_database; from app.services.data_fetcher import DataFetcher; from app.services.indicator_service import IndicatorService; init_database(); df = DataFetcher(); is_service = IndicatorService(); df.fetch_and_save_stock('" + symbol + "'); is_service.calculate_indicators('" + symbol + "')\"",
			})
			return
		}
		// Other errors are server errors
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, stock)
}

// GetSignal handles GET /api/v1/signal/:symbol
func (h *StockHandler) GetSignal(c *gin.Context) {
	symbol := c.Param("symbol")

	subscriptionLevel := c.Query("subscription_level")
	if subscriptionLevel == "" {
		subscriptionLevel = "basic"
	}

	stock, err := h.stockService.GetStock(symbol, subscriptionLevel)
	if err != nil {
		// Check if it's a "not found" error - return 200 with no data message
		if strings.Contains(err.Error(), "not found") {
			c.JSON(http.StatusOK, gin.H{
				"symbol": symbol,
				"data_available": false,
				"message": "No data available for this symbol. Please run the batch worker to fetch market data first.",
			})
			return
		}
		// Other errors are server errors
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	if stock.Signal == nil {
		c.JSON(http.StatusOK, gin.H{
			"symbol": symbol,
			"signal": "hold",
			"reason": "No signal available",
		})
		return
	}

	c.JSON(http.StatusOK, stock.Signal)
}

// GetFundamentals handles GET /api/v1/stock/:symbol/fundamentals
func (h *StockHandler) GetFundamentals(c *gin.Context) {
	symbol := c.Param("symbol")
	fundamentals, err := h.stockService.GetFundamentals(symbol)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			c.JSON(http.StatusOK, gin.H{
				"symbol": symbol,
				"data_available": false,
				"message": "No fundamental data available for this symbol.",
			})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, fundamentals)
}

// GetNews handles GET /api/v1/stock/:symbol/news
func (h *StockHandler) GetNews(c *gin.Context) {
	symbol := c.Param("symbol")
	limit := 10
	news, err := h.stockService.GetNews(symbol, limit)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"symbol": symbol,
			"news": []interface{}{},
			"message": "No news available",
		})
		return
	}
	c.JSON(http.StatusOK, gin.H{"symbol": symbol, "news": news})
}

// GetEarnings handles GET /api/v1/stock/:symbol/earnings
func (h *StockHandler) GetEarnings(c *gin.Context) {
	symbol := c.Param("symbol")
	earnings, err := h.stockService.GetEarnings(symbol, 10)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"symbol": symbol,
			"earnings": []interface{}{},
			"message": "No earnings data available",
		})
		return
	}
	c.JSON(http.StatusOK, gin.H{"symbol": symbol, "earnings": earnings})
}

// GetIndustryPeers handles GET /api/v1/stock/:symbol/industry-peers
func (h *StockHandler) GetIndustryPeers(c *gin.Context) {
	symbol := c.Param("symbol")
	peers, err := h.stockService.GetIndustryPeers(symbol)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"symbol": symbol,
			"sector": nil,
			"industry": nil,
			"peers": []interface{}{},
			"message": "No industry/peer data available",
		})
		return
	}
	c.JSON(http.StatusOK, peers)
}

// GetAdvancedAnalysis handles GET /api/v1/stock/:symbol/advanced-analysis
// Returns all advanced analysis data: moving averages, MACD, RSI, volume, ATR, etc.
func (h *StockHandler) GetAdvancedAnalysis(c *gin.Context) {
	symbol := c.Param("symbol")
	
	// Get subscription level
	subscriptionLevel := c.Query("subscription_level")
	if subscriptionLevel == "" {
		subscriptionLevel = "basic"
	}

	// Get stock data (includes indicators)
	stock, err := h.stockService.GetStock(symbol, subscriptionLevel)
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"symbol": symbol,
			"data_available": false,
			"message": "No data available for this symbol",
		})
		return
	}

	// Get volume data from raw market data
	volumeData, _ := h.stockService.GetVolumeData(symbol, 30) // Last 30 days

	// Build comprehensive response
	response := gin.H{
		"symbol": symbol,
		"data_available": true,
		"moving_averages": gin.H{
			"ma7":   stock.Indicators.MA7,
			"ma21":  stock.Indicators.MA21,
			"sma50": stock.Indicators.SMA50,
			"ema20": stock.Indicators.EMA20,
			"ema50": stock.Indicators.EMA50,
			"sma200": stock.Indicators.SMA200,
		},
		"macd": gin.H{
			"macd_line":     stock.Indicators.MACD,
			"macd_signal":   stock.Indicators.MACDSignal,
			"macd_histogram": stock.Indicators.MACDHistogram,
		},
		"rsi": stock.Indicators.RSI,
		"volume": volumeData,
		"atr_volatility": gin.H{
			"atr": stock.Indicators.ATR,
			"bollinger_bands": gin.H{
				"upper":  stock.Indicators.BBUpper,
				"middle": stock.Indicators.BBMiddle,
				"lower":  stock.Indicators.BBLower,
			},
		},
		"trends": gin.H{
			"long_term":   stock.Indicators.LongTermTrend,
			"medium_term": stock.Indicators.MediumTermTrend,
		},
		"momentum_score": stock.Indicators.MomentumScore,
		"pullback_zones": gin.H{
			"lower": stock.Indicators.PullbackZoneLower,
			"upper": stock.Indicators.PullbackZoneUpper,
		},
	}

	// Add subscription-filtered data
	if subscriptionLevel == "pro" || subscriptionLevel == "elite" {
		// Pro/Elite get full data
	} else {
		// Basic users get limited data
		response["momentum_score"] = nil
		response["pullback_zones"] = gin.H{"lower": nil, "upper": nil}
	}

	c.JSON(http.StatusOK, response)
}

