package main

import (
	"log"
	"os"
	_ "time/tzdata"

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

	// Initialize Redis job queue (feature-flagged)
	useJobQueue := os.Getenv("ENABLE_JOB_QUEUE") == "true"
	var jobQueue *services.RedisStreamJobQueue
	if useJobQueue {
		log.Println("🧵 ENABLE_JOB_QUEUE=true; using Redis Streams job queue")
		jq, err := services.NewRedisStreamJobQueue(redisURL)
		if err != nil {
			log.Printf("Warning: Failed to connect to Redis job queue: %v. Falling back to direct python-worker calls.", err)
			useJobQueue = false
		} else {
			jobQueue = jq
			defer jobQueue.Close()
			log.Println("✅ Redis job queue connected")
		}
	} else {
		log.Println("🧵 ENABLE_JOB_QUEUE!=true; using direct python-worker calls (no Redis job queue)")
	}

	// Initialize repositories
	portfolioRepo := repositories.NewPortfolioRepository()
	indicatorRepo := repositories.NewIndicatorRepository()
	marketDataRepo := repositories.NewMarketDataRepository()
	stockGradesRepo := repositories.NewStockGradesRepository()
	watchlistRepo := repositories.NewWatchlistRepository()
	tickerRepo := repositories.NewTickerRepository()
	userRepo := repositories.NewUserRepository()
	ingestionAuditRepo := repositories.NewIngestionAuditRepository()
	scheduleRepo := repositories.NewScheduleRepository()
	dataPreviewRepo := repositories.NewDataPreviewRepository()
	notificationQueueRepo := repositories.NewNotificationQueueRepository()
	runRepo := repositories.NewRunRepository()
	portfolioOverviewRepo := repositories.NewPortfolioOverviewRepository()
	portfolioScheduleRepo := repositories.NewPortfolioScheduleRepository()

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
	dataPreviewService := services.NewDataPreviewService(dataPreviewRepo)
	symbolScopeHandler := handlers.NewSymbolScopeHandler(watchlistService, portfolioService, cacheService)
	meHandler := handlers.NewMeHandler(userRepo)

	// Initialize handlers
	portfolioHandler := handlers.NewPortfolioHandler(portfolioService)
	stockHandler := handlers.NewStockHandler(stockService, ingestionAuditRepo, stockGradesRepo)
	watchlistHandler := handlers.NewWatchlistHandler(watchlistService)
	tickerHandler := handlers.NewTickerHandler(tickerService)
	llmHandler := handlers.NewLLMHandler()
	reportHandler := handlers.NewReportHandler()
	adminProxyHandler := handlers.NewAdminProxyHandler(pythonWorkerClient, cacheService)
	dataLoadHandler := handlers.NewDataLoadHandler(pythonWorkerClient, ingestionAuditRepo, jobQueue, useJobQueue)
	tradingDecisionV3Handler := handlers.NewTradingDecisionV3Handler(ingestionAuditRepo, jobQueue, useJobQueue)
	dataPreviewHandler := handlers.NewDataPreviewHandler(dataPreviewService)
	notificationQueueHandler := handlers.NewNotificationQueueHandler(notificationQueueRepo)
	jobQueueAdminHandler := handlers.NewJobQueueAdminHandler(jobQueue)
	portfolioV2ProxyHandler := handlers.NewPortfolioV2ProxyHandler(pythonWorkerClient)
	portfolioAnalysisRunHandler := handlers.NewPortfolioAnalysisRunHandler(ingestionAuditRepo, jobQueue, useJobQueue)
	analysisProfilesHandler := handlers.NewAnalysisProfilesHandler()
	portfolioRebalanceRunHandler := handlers.NewPortfolioRebalanceRunHandler(ingestionAuditRepo, jobQueue, useJobQueue)
	runHandler := handlers.NewRunHandler(runRepo, pythonWorkerClient)
	portfolioOverviewHandler := handlers.NewPortfolioOverviewHandler(portfolioOverviewRepo)
	portfolioScheduleHandler := handlers.NewPortfolioScheduleHandler(portfolioScheduleRepo)

	schedulerService := services.NewSchedulerService(scheduleRepo, ingestionAuditRepo, jobQueue, useJobQueue)
	scheduleHandler := handlers.NewScheduleHandler(scheduleRepo, schedulerService, ingestionAuditRepo)
	schedulerTickHandler := handlers.NewSchedulerTickHandler(schedulerService)

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
		// Portfolio API v2 proxy (compat bridge: Streamlit -> Go API only)
		api.Any("/portfolio-v2/*path", portfolioV2ProxyHandler.Proxy)

		// Notification Queue (Operator UX)
		api.GET("/notifications/queue/summary", notificationQueueHandler.Summary)
		api.GET("/notifications/queue/recent", notificationQueueHandler.Recent)
		api.GET("/notifications/queue/by-correlation/:correlation_id", notificationQueueHandler.ByCorrelationID)

		// Current user profile (BFF)
		api.GET("/me", meHandler.GetMe)
		api.PATCH("/me", meHandler.UpdateMe)

		// Users (UI helper)
		api.GET("/users", func(c *gin.Context) {
			users, err := userRepo.ListUsers(200)
			if err != nil {
				c.JSON(500, gin.H{"error": err.Error()})
				return
			}
			c.JSON(200, gin.H{"count": len(users), "users": users})
		})

		// Admin proxy endpoints (Go API -> python-worker)
		api.GET("/admin/health", adminProxyHandler.GetHealth)
		api.GET("/admin/data-sources", adminProxyHandler.GetDataSources)
		api.POST("/admin/refresh", adminProxyHandler.Refresh)
		api.GET("/admin/refresh/status", adminProxyHandler.GetRefreshStatus)
		api.GET("/admin/job-profiles", dataLoadHandler.GetJobProfiles)
		api.GET("/admin/analysis-profiles", analysisProfilesHandler.GetProfiles)
		api.GET("/admin/job-queue/status", jobQueueAdminHandler.GetStatus)
		api.POST("/admin/job-queue/dlq/requeue", jobQueueAdminHandler.RequeueDLQ)
		api.POST("/admin/job-queue/stream/delete", jobQueueAdminHandler.DeleteStreamEntries)
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

		// Scheduler CRUD + tick (Go API is orchestrator)
		api.GET("/schedules", scheduleHandler.List)
		api.POST("/schedules", scheduleHandler.Create)
		api.GET("/schedules/:schedule_id", scheduleHandler.Get)
		api.GET("/schedules/:schedule_id/runs", scheduleHandler.ListRuns)
		api.PATCH("/schedules/:schedule_id", scheduleHandler.Update)
		api.DELETE("/schedules/:schedule_id", scheduleHandler.Delete)
		api.POST("/schedules/:schedule_id/run-now", scheduleHandler.RunNow)
		api.POST("/schedules/:schedule_id/make-due-now", scheduleHandler.MakeDueNow)
		api.POST("/scheduler/tick", schedulerTickHandler.Tick)

		// Earnings calendar endpoints (Go API -> python-worker admin)
		api.GET("/admin/earnings-calendar", adminProxyHandler.GetEarningsCalendar)
		api.POST("/admin/earnings-calendar/refresh", adminProxyHandler.RefreshEarningsCalendar)
		api.POST("/admin/earnings-calendar/refresh-for-date", adminProxyHandler.RefreshEarningsForDate)

		// Swing endpoints (Go API -> python-worker)
		api.POST("/admin/swing/signal", adminProxyHandler.SwingSignal)
		api.POST("/admin/swing/risk/check", adminProxyHandler.SwingRiskCheck)
		api.POST("/admin/universal/signal/universal", adminProxyHandler.UniversalSignal)

		// Portfolio Schedule Management endpoints
		api.GET("/portfolio-schedules/list", portfolioScheduleHandler.ListSchedules)
		api.GET("/portfolio-schedules/:schedule_id", portfolioScheduleHandler.GetSchedule)
		api.POST("/portfolio-schedules/", portfolioScheduleHandler.CreateSchedule)
		api.PUT("/portfolio-schedules/:schedule_id", portfolioScheduleHandler.UpdateSchedule)
		api.DELETE("/portfolio-schedules/:schedule_id", portfolioScheduleHandler.DeleteSchedule)
		api.POST("/portfolio-schedules/:schedule_id/toggle", portfolioScheduleHandler.ToggleSchedule)
		api.GET("/portfolio-schedules/status/overview", portfolioScheduleHandler.GetScheduleOverview)
		api.Any("/admin/fundamentals/*path", func(c *gin.Context) {
			path := c.Param("path")
			if path == "/fair-value" && c.Request.Method == "POST" {
				adminProxyHandler.FairValue(c)
				return
			}
			switch c.Request.Method {
			case "GET":
				adminProxyHandler.FundamentalsGet(c)
			default:
				c.JSON(405, gin.H{"error": "method not allowed"})
			}
		})
		api.Any("/admin/growth-quality/*path", func(c *gin.Context) {
			// Allow GET/POST passthrough for now
			switch c.Request.Method {
			case "GET":
				adminProxyHandler.GrowthQualityGet(c)
			case "POST":
				adminProxyHandler.GrowthQualityPost(c)
			default:
				c.JSON(405, gin.H{"error": "method not allowed"})
			}
		})
		api.GET("/admin/rating-alerts/*path", adminProxyHandler.RatingAlertsGet)
		api.POST("/admin/rating-alerts/*path", adminProxyHandler.RatingAlertsPost)
		api.PUT("/admin/rating-alerts/*path", adminProxyHandler.RatingAlertsPut)
		api.DELETE("/admin/rating-alerts/*path", adminProxyHandler.RatingAlertsDelete)

		// Generic, allowlisted data preview endpoint (Operator UX)
		api.GET("/data-preview", dataPreviewHandler.GetPreview)

		// Stock coverage proxy (UI helper)
		api.GET("/stocks/:symbol/coverage", adminProxyHandler.GetStockCoverage)

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

		// Portfolio endpoints
		api.GET("/portfolios/user/:user_id", portfolioHandler.GetPortfolios)
		api.GET("/portfolio/:user_id/:portfolio_id", portfolioHandler.GetPortfolio)
		api.POST("/portfolio/:user_id", portfolioHandler.CreatePortfolio)
		api.GET("/portfolios/:portfolio_id/overview", portfolioOverviewHandler.GetOverview)

		// Portfolio data-load orchestration (Option B)
		api.POST("/portfolios/:portfolio_id/data-load", dataLoadHandler.CreatePortfolioDataLoad)
		api.GET("/portfolios/:portfolio_id/data-load/runs", dataLoadHandler.ListPortfolioRuns)
		api.GET("/portfolios/:portfolio_id/alerts/summary", dataLoadHandler.GetPortfolioAlertsSummary)
		api.GET("/data-load/runs/:run_id", dataLoadHandler.GetRun)
		api.GET("/data-load/runs/:run_id/alert-events", dataLoadHandler.ListRunAlertEvents)
		api.GET("/alerts/events", dataLoadHandler.ListAlertEventsForSymbol)
		api.POST("/data-load/runs/:run_id/cancel", dataLoadHandler.CancelRun)
		api.POST("/data-load/runs/:run_id/rerun-failed", dataLoadHandler.RerunFailed)

		// Trading Decision V3 orchestration (Option B)
		api.POST("/portfolios/:portfolio_id/trading-decisions/v3/run", tradingDecisionV3Handler.CreatePortfolioDecisionRun)

		// Portfolio analysis run orchestration (Option B)
		api.POST("/portfolios/:portfolio_id/analysis-run", portfolioAnalysisRunHandler.CreateRun)
		api.POST("/portfolios/:portfolio_id/rebalance-run", portfolioRebalanceRunHandler.CreateRun)

		// Symbol scope endpoints (UI helper)
		api.GET("/symbol-scope/resolve", symbolScopeHandler.Resolve)

		// Ticker directory endpoints
		api.GET("/tickers", tickerHandler.GetAllTickers)
		api.GET("/tickers/search", tickerHandler.SearchTickers)
		api.GET("/tickers/:symbol", tickerHandler.GetTicker)

		// Stock endpoints
		api.GET("/stock/:symbol", stockHandler.GetStock)
		api.GET("/stock/:symbol/alert-context", stockHandler.GetAlertContext)
		api.GET("/stock/:symbol/advanced-analysis", stockHandler.GetAdvancedAnalysis)
		api.GET("/stock/:symbol/fundamentals", stockHandler.GetFundamentals)
		api.GET("/stock/:symbol/news", stockHandler.GetNews)
		api.GET("/stock/:symbol/earnings", stockHandler.GetEarnings)
		api.GET("/stock/:symbol/industry-peers", stockHandler.GetIndustryPeers)
		api.GET("/signal/:symbol", stockHandler.GetSignal)

		// Runs endpoints (DRY orchestration)
		api.POST("/runs", runHandler.CreateRun)
		api.GET("/runs/:run_id", runHandler.GetRun)
		api.GET("/runs", runHandler.ListRuns)

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
