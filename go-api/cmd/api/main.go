package main

import (
	"log"
	"os"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/database"
	"github.com/trading-system/go-api/internal/handlers"
	"github.com/trading-system/go-api/internal/repositories"
	"github.com/trading-system/go-api/internal/services"
)

func main() {
	// Initialize logger
	log.SetOutput(os.Stdout)
	log.Println("🚀 Starting Trading System Go API...")

	// Initialize database
	if err := database.InitDB(); err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}
	defer database.CloseDB()

	// Initialize Redis cache
	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://localhost:6379/0"
	}

	cacheService, err := services.NewCacheService(redisURL)
	if err != nil {
		log.Printf("Warning: Failed to connect to Redis: %v. Continuing without cache.", err)
		cacheService = nil
	} else {
		defer cacheService.Close()
		log.Println("✅ Redis cache connected")
	}

	// Initialize repositories
	portfolioRepo := repositories.NewPortfolioRepository()
	indicatorRepo := repositories.NewIndicatorRepository()
	marketDataRepo := repositories.NewMarketDataRepository()
	watchlistRepo := repositories.NewWatchlistRepository()
	tickerRepo := repositories.NewTickerRepository()

	// Initialize services
	portfolioService := services.NewPortfolioService(portfolioRepo, indicatorRepo, cacheService)

	// Get Python Worker URL from environment
	pythonWorkerURL := os.Getenv("PYTHON_WORKER_URL")
	if pythonWorkerURL == "" {
		pythonWorkerURL = "http://localhost:8001"
	}

	stockService := services.NewStockService(indicatorRepo, marketDataRepo, cacheService, pythonWorkerURL)
	watchlistService := services.NewWatchlistService(watchlistRepo, portfolioRepo, cacheService)
	tickerService := services.NewTickerService(tickerRepo, cacheService)
	pythonWorkerClient := services.NewPythonWorkerClient(pythonWorkerURL)
	symbolScopeHandler := handlers.NewSymbolScopeHandler(watchlistService, portfolioService, cacheService)

	// Initialize handlers
	portfolioHandler := handlers.NewPortfolioHandler(portfolioService)
	stockHandler := handlers.NewStockHandler(stockService)
	watchlistHandler := handlers.NewWatchlistHandler(watchlistService)
	tickerHandler := handlers.NewTickerHandler(tickerService)
	llmHandler := handlers.NewLLMHandler()
	reportHandler := handlers.NewReportHandler()
	adminProxyHandler := handlers.NewAdminProxyHandler(pythonWorkerClient)

	// Initialize HTTP router
	r := gin.Default()

	// Health check
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"status":  "healthy",
			"service": "go-api",
		})
	})

	// API routes
	api := r.Group("/api/v1")
	{
		// Admin proxy endpoints (Go API -> python-worker)
		api.GET("/admin/health", adminProxyHandler.GetHealth)
		api.GET("/admin/data-sources", adminProxyHandler.GetDataSources)
		api.POST("/admin/refresh", adminProxyHandler.Refresh)
		api.GET("/admin/refresh/status", adminProxyHandler.GetRefreshStatus)
		api.GET("/admin/data-summary/:table", adminProxyHandler.GetDataSummary)
		api.GET("/admin/audit-logs", adminProxyHandler.GetAuditLogs)
		api.POST("/admin/signals/generate", adminProxyHandler.GenerateSignals)
		api.GET("/admin/signals/recent", adminProxyHandler.GetRecentSignals)
		api.POST("/admin/screener/run", adminProxyHandler.RunScreener)
		api.GET("/admin/screener/results/:id", adminProxyHandler.GetScreenerResults)

		// Stock insights endpoints
		api.POST("/admin/insights/generate", adminProxyHandler.GenerateStockInsights)
		api.GET("/admin/insights/strategies", adminProxyHandler.GetAvailableStrategies)
		api.POST("/admin/insights/strategy/:strategyName", adminProxyHandler.RunSingleStrategy)

		// Earnings calendar endpoints (Go API -> python-worker admin)
		api.GET("/admin/earnings-calendar", adminProxyHandler.GetEarningsCalendar)
		api.POST("/admin/earnings-calendar/refresh", adminProxyHandler.RefreshEarningsCalendar)
		api.POST("/admin/earnings-calendar/refresh-for-date", adminProxyHandler.RefreshEarningsForDate)

		// Swing endpoints (Go API -> python-worker)
		api.POST("/admin/swing/signal", adminProxyHandler.SwingSignal)
		api.POST("/admin/swing/risk/check", adminProxyHandler.SwingRiskCheck)

		// Portfolio endpoints
		api.GET("/portfolios/user/:user_id", portfolioHandler.GetPortfolios)
		api.GET("/portfolio/:user_id/:portfolio_id", portfolioHandler.GetPortfolio)
		api.POST("/portfolio/:user_id", portfolioHandler.CreatePortfolio)
		api.PUT("/portfolio/:user_id/:portfolio_id", portfolioHandler.UpdatePortfolio)
		api.DELETE("/portfolio/:user_id/:portfolio_id", portfolioHandler.DeletePortfolio)

		// Holdings endpoints
		api.POST("/portfolio/:user_id/:portfolio_id/holdings", portfolioHandler.CreateHolding)
		api.PUT("/holdings/:holding_id", portfolioHandler.UpdateHolding)
		api.DELETE("/holdings/:holding_id", portfolioHandler.DeleteHolding)

		// Watchlist endpoints
		api.POST("/watchlists", watchlistHandler.CreateWatchlist)
		api.GET("/watchlists/user/:user_id", watchlistHandler.GetWatchlists)
		api.GET("/watchlists/:watchlist_id", watchlistHandler.GetWatchlist)
		api.PUT("/watchlists/:watchlist_id", watchlistHandler.UpdateWatchlist)
		api.DELETE("/watchlists/:watchlist_id", watchlistHandler.DeleteWatchlist)
		api.POST("/watchlists/:watchlist_id/items", watchlistHandler.AddItem)
		api.PUT("/watchlist-items/:item_id", watchlistHandler.UpdateItem)
		api.DELETE("/watchlist-items/:item_id", watchlistHandler.RemoveItem)
		api.POST("/watchlists/:watchlist_id/move-to-portfolio", watchlistHandler.MoveToPortfolio)

		// Symbol scope endpoints (UI helper)
		api.GET("/symbol-scope/resolve", symbolScopeHandler.Resolve)

		// Ticker directory endpoints
		api.GET("/tickers/search", tickerHandler.SearchTickers)
		api.GET("/tickers/:symbol", tickerHandler.GetTicker)

		// Stock endpoints
		api.GET("/stock/:symbol", stockHandler.GetStock)
		api.GET("/stock/:symbol/advanced-analysis", stockHandler.GetAdvancedAnalysis)
		api.GET("/stock/:symbol/fundamentals", stockHandler.GetFundamentals)
		api.GET("/stock/:symbol/news", stockHandler.GetNews)
		api.GET("/stock/:symbol/earnings", stockHandler.GetEarnings)
		api.GET("/stock/:symbol/industry-peers", stockHandler.GetIndustryPeers)
		api.GET("/signal/:symbol", stockHandler.GetSignal)

		// LLM endpoints
		api.GET("/llm_blog/:symbol", llmHandler.GetLLMBlog)

		// Report endpoints
		api.GET("/report/:symbol", reportHandler.GetReport)
		api.POST("/report/:symbol/generate", reportHandler.GenerateReport)
		api.GET("/reports", reportHandler.ListReports)
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}

	log.Printf("📡 HTTP server listening on :%s", port)
	if err := r.Run(":" + port); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
