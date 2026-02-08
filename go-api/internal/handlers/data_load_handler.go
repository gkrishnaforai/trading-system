package handlers

import (
	"context"
	"encoding/json"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/trading-system/go-api/internal/repositories"
	"github.com/trading-system/go-api/internal/services"
)

type DataLoadHandler struct {
	pythonWorker *services.PythonWorkerClient
	auditRepo    *repositories.IngestionAuditRepository
	jobQueue     *services.RedisStreamJobQueue
	useJobQueue  bool
}

func NewDataLoadHandler(pythonWorker *services.PythonWorkerClient, auditRepo *repositories.IngestionAuditRepository, jobQueue *services.RedisStreamJobQueue, useJobQueue bool) *DataLoadHandler {
	return &DataLoadHandler{pythonWorker: pythonWorker, auditRepo: auditRepo, jobQueue: jobQueue, useJobQueue: useJobQueue}
}

// GET /api/v1/admin/job-profiles
func (h *DataLoadHandler) GetJobProfiles(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"profiles": services.JobProfilesAsMap()})
}

type CreatePortfolioDataLoadRequest struct {
	Symbols          []string `json:"symbols"`
	Profile          string   `json:"profile"`
	DataTypes        []string `json:"data_types"`
	IncludeDataTypes []string `json:"include_data_types"`
	ExcludeDataTypes []string `json:"exclude_data_types"`
	Force            bool     `json:"force"`
}

func normalizeDataTypes(in []string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(in))
	for _, raw := range in {
		s := strings.TrimSpace(strings.ToLower(raw))
		if s == "" {
			continue
		}
		if _, ok := seen[s]; ok {
			continue
		}
		seen[s] = struct{}{}
		out = append(out, s)
	}
	return out
}

func applyDataTypeOverrides(base []string, include []string, exclude []string) []string {
	base = normalizeDataTypes(base)
	include = normalizeDataTypes(include)
	exclude = normalizeDataTypes(exclude)

	excluded := map[string]struct{}{}
	for _, dt := range exclude {
		excluded[dt] = struct{}{}
	}

	seen := map[string]struct{}{}
	out := make([]string, 0, len(base)+len(include))
	for _, dt := range base {
		if _, ok := excluded[dt]; ok {
			continue
		}
		if _, ok := seen[dt]; ok {
			continue
		}
		seen[dt] = struct{}{}
		out = append(out, dt)
	}
	for _, dt := range include {
		if _, ok := excluded[dt]; ok {
			continue
		}
		if _, ok := seen[dt]; ok {
			continue
		}
		seen[dt] = struct{}{}
		out = append(out, dt)
	}
	return out
}

var symbolPattern = regexp.MustCompile(`^[A-Z][A-Z0-9.\-]{0,14}$`)

func sanitizeSymbols(in []string) (valid []string, dropped []string) {
	seen := map[string]struct{}{}
	for _, raw := range in {
		s := strings.ToUpper(strings.TrimSpace(raw))
		if s == "" {
			dropped = append(dropped, raw)
			continue
		}
		// Reject purely numeric symbols like "0" and anything that doesn't match our allowlist.
		allDigits := true
		for i := 0; i < len(s); i++ {
			if s[i] < '0' || s[i] > '9' {
				allDigits = false
				break
			}
		}
		if allDigits || !symbolPattern.MatchString(s) {
			dropped = append(dropped, s)
			continue
		}
		if _, ok := seen[s]; ok {
			continue
		}
		seen[s] = struct{}{}
		valid = append(valid, s)
	}
	return valid, dropped
}

// POST /api/v1/portfolios/:portfolio_id/data-load
func (h *DataLoadHandler) CreatePortfolioDataLoad(c *gin.Context) {
	portfolioID := c.Param("portfolio_id")
	if _, err := uuid.Parse(portfolioID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "portfolio_id must be a valid UUID"})
		return
	}

	var req CreatePortfolioDataLoadRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if len(req.Symbols) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "symbols must be non-empty"})
		return
	}

	dataTypes := req.DataTypes
	if strings.TrimSpace(req.Profile) != "" {
		resolved, err := services.ResolveJobProfileDataTypes(req.Profile)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		dataTypes = resolved
	}
	dataTypes = applyDataTypeOverrides(dataTypes, req.IncludeDataTypes, req.ExcludeDataTypes)
	if len(dataTypes) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "data_types must be non-empty"})
		return
	}

	symbols, dropped := sanitizeSymbols(req.Symbols)
	if len(symbols) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "no valid symbols after sanitization"})
		return
	}

	runID := uuid.New().String()
	_ = h.auditRepo.CreateRun(runID, "running", map[string]any{
		"operation":          "refresh",
		"portfolio_id":       portfolioID,
		"symbols":            symbols,
		"symbols_dropped":    dropped,
		"profile":            req.Profile,
		"data_types":         dataTypes,
		"include_data_types": normalizeDataTypes(req.IncludeDataTypes),
		"exclude_data_types": normalizeDataTypes(req.ExcludeDataTypes),
		"force":              req.Force,
		"requested_at":       time.Now().UTC().Format(time.RFC3339),
	})

	if len(dropped) > 0 {
		msg := "some invalid symbols were dropped"
		_ = h.auditRepo.CreateEvent(runID, "warn", "symbols_sanitized", nil, nil, &msg, nil, map[string]any{"dropped": dropped}, nil)
	}

	if h.useJobQueue && h.jobQueue != nil {
		parentCtx := context.Background()
		ctx, cancel := context.WithTimeout(parentCtx, 15*time.Second)
		defer cancel()

		msg := "enqueuing portfolio data-load jobs"
		_ = h.auditRepo.CreateEvent(runID, "info", "queue_enqueue_started", nil, nil, &msg, nil, map[string]any{"symbols_count": len(symbols)}, nil)

		_ = h.jobQueue.SetRunRemaining(ctx, runID, len(symbols))

		enqueueFailed := 0
		for _, sym := range symbols {
			symCopy := sym
			err := func() error {
				_, err := h.jobQueue.EnqueueDataLoadJob(ctx, services.DataLoadJobPayload{
					RunID:       runID,
					PortfolioID: portfolioID,
					Symbol:      symCopy,
					DataTypes:   dataTypes,
					Force:       req.Force,
					Attempt:     1,
					MaxAttempts: 3,
				})
				return err
			}()
			if err != nil {
				enqueueFailed += 1
				errMsg := err.Error()
				_ = h.auditRepo.CreateEvent(runID, "error", "queue_enqueue_failed", &symCopy, nil, nil, &errMsg, nil, nil)
				continue
			}
			m := "job enqueued"
			_ = h.auditRepo.CreateEvent(runID, "info", "queue_job_enqueued", &symCopy, nil, &m, nil, map[string]any{"profile": req.Profile, "data_types": dataTypes}, nil)
		}

		if enqueueFailed > 0 {
			failMsg := "some jobs failed to enqueue"
			_ = h.auditRepo.CreateEvent(runID, "error", "queue_enqueue_partial_failure", nil, nil, nil, &failMsg, map[string]any{"failed": enqueueFailed}, nil)
			_ = h.auditRepo.UpdateRunStatus(runID, "failed", map[string]any{"go_error": failMsg, "enqueue_failed": enqueueFailed})
			c.JSON(http.StatusAccepted, gin.H{"success": true, "run_id": runID, "portfolio_id": portfolioID, "status": "failed", "profile": req.Profile, "data_types": dataTypes, "include_data_types": req.IncludeDataTypes, "exclude_data_types": req.ExcludeDataTypes})
			return
		}

		fin := "enqueue completed"
		_ = h.auditRepo.CreateEvent(runID, "info", "queue_enqueue_finished", nil, nil, &fin, nil, map[string]any{"symbols_count": len(symbols)}, nil)

		c.JSON(http.StatusAccepted, gin.H{"success": true, "run_id": runID, "portfolio_id": portfolioID, "status": "running", "profile": req.Profile, "data_types": dataTypes, "include_data_types": req.IncludeDataTypes, "exclude_data_types": req.ExcludeDataTypes})
		return
	}

	// IMPORTANT: do NOT use c.Request.Context() here. The HTTP request context is cancelled
	// as soon as this handler returns (202 Accepted), which would cancel the background
	// python-worker refresh call and mark the run as failed with "context canceled".
	parentCtx := context.Background()
	symbolsCopy := append([]string(nil), symbols...)
	dataTypesCopy := append([]string(nil), dataTypes...)
	force := req.Force

	go func() {
		ctx, cancel := context.WithTimeout(parentCtx, 30*time.Minute)
		defer cancel()

		createInfo := func(operation string, symbol *string, provider *string, message string, extra map[string]any) {
			msg := message
			_ = h.auditRepo.CreateEvent(runID, "info", operation, symbol, provider, &msg, nil, extra, nil)
		}
		createError := func(operation string, symbol *string, provider *string, err error) {
			errMsg := ""
			if err != nil {
				errMsg = err.Error()
			}
			_ = h.auditRepo.CreateEvent(runID, "error", operation, symbol, provider, nil, &errMsg, nil, nil)
		}

		createInfo("run_started", nil, nil, "run started", map[string]any{"portfolio_id": portfolioID})

		isGradesType := func(dt string) bool {
			switch dt {
			case "stock_grades", "analyst_ratings", "consensus_data", "price_targets":
				return true
			default:
				return false
			}
		}

		gradesRequested := false
		mainDataTypes := make([]string, 0, len(dataTypesCopy))
		for _, dt := range dataTypesCopy {
			if isGradesType(dt) {
				gradesRequested = true
				continue
			}
			mainDataTypes = append(mainDataTypes, dt)
		}

		if len(mainDataTypes) > 0 {
			cancelRequested, err := h.auditRepo.IsCancelRequested(runID)
			if err == nil && cancelRequested {
				createInfo("run_canceled", nil, nil, "cancel requested", nil)
				_ = h.auditRepo.UpdateRunStatus(runID, "canceled", map[string]any{"canceled_at": time.Now().UTC().Format(time.RFC3339)})
				return
			}

			createInfo("admin_refresh_started", nil, nil, "calling python-worker /admin/refresh", map[string]any{"data_types": mainDataTypes})
			start := time.Now()
			_, err = h.pythonWorker.AdminRefreshData(ctx, services.AdminRefreshRequest{
				RunID:       runID,
				PortfolioID: portfolioID,
				Symbols:     symbolsCopy,
				DataTypes:   mainDataTypes,
				Force:       force,
			})
			if err != nil {
				createError("admin_refresh_failed", nil, nil, err)
				_ = h.auditRepo.UpdateRunStatus(runID, "failed", map[string]any{"go_error": err.Error()})
				return
			}
			dur := int(time.Since(start).Milliseconds())
			createInfo("admin_refresh_finished", nil, nil, "python-worker /admin/refresh completed", map[string]any{"duration_ms": dur})
		}

		if gradesRequested {
			createInfo("grades_refresh_started", nil, nil, "calling python-worker /api/v1/grades/refresh/{symbol}", nil)
			gradesFailed := 0
			gradesFailures := make([]map[string]any, 0)
			for _, sym := range symbolsCopy {
				cancelRequested, err := h.auditRepo.IsCancelRequested(runID)
				if err == nil && cancelRequested {
					createInfo("run_canceled", &sym, nil, "cancel requested", nil)
					_ = h.auditRepo.UpdateRunStatus(runID, "canceled", map[string]any{"canceled_at": time.Now().UTC().Format(time.RFC3339)})
					return
				}

				symCopy := sym
				createInfo("grades_symbol_started", &symCopy, nil, "refreshing grades", nil)
				start := time.Now()
				err = h.pythonWorker.RefreshGrades(ctx, sym, "fmp", true, force)
				if err != nil {
					createError("grades_symbol_failed", &symCopy, nil, err)
					gradesFailed += 1
					gradesFailures = append(gradesFailures, map[string]any{
						"symbol": sym,
						"error":  err.Error(),
					})
					continue
				}
				dur := int(time.Since(start).Milliseconds())
				createInfo("grades_symbol_finished", &symCopy, nil, "grades refresh completed", map[string]any{"duration_ms": dur})
			}
			if gradesFailed > 0 {
				_ = h.auditRepo.PatchRunMetadata(runID, map[string]any{
					"grades_failed":         gradesFailed,
					"grades_failed_symbols": gradesFailures,
				})
			}
			createInfo("grades_refresh_finished", nil, nil, "grades refresh completed", nil)
		}

		createInfo("run_finished", nil, nil, "run completed", nil)
		_ = h.auditRepo.UpdateRunStatus(runID, "success", map[string]any{"finished_at": time.Now().UTC().Format(time.RFC3339)})
	}()

	c.JSON(http.StatusAccepted, gin.H{
		"success":            true,
		"run_id":             runID,
		"portfolio_id":       portfolioID,
		"status":             "running",
		"profile":            req.Profile,
		"data_types":         dataTypes,
		"include_data_types": req.IncludeDataTypes,
		"exclude_data_types": req.ExcludeDataTypes,
	})
}

// POST /api/v1/data-load/runs/:run_id/cancel
func (h *DataLoadHandler) CancelRun(c *gin.Context) {
	runID := c.Param("run_id")
	if _, err := uuid.Parse(runID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "run_id must be a valid UUID"})
		return
	}

	run, err := h.auditRepo.GetRun(runID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	if run.Status != "running" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "run is not running", "status": run.Status})
		return
	}

	if err := h.auditRepo.RequestCancel(runID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	msg := "cancel requested"
	_ = h.auditRepo.CreateEvent(runID, "info", "cancel_requested", nil, nil, &msg, nil, nil, nil)
	_ = h.auditRepo.PatchRunMetadata(runID, map[string]any{"cancel_requested": true})

	c.JSON(http.StatusAccepted, gin.H{"success": true, "run_id": runID, "status": "cancel_requested"})
}

// GET /api/v1/portfolios/:portfolio_id/data-load/runs
func (h *DataLoadHandler) ListPortfolioRuns(c *gin.Context) {
	portfolioID := c.Param("portfolio_id")
	if _, err := uuid.Parse(portfolioID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "portfolio_id must be a valid UUID"})
		return
	}
	limit := 20
	if v := c.Query("limit"); v != "" {
		if parsed, err := parseInt(v); err == nil {
			limit = parsed
		}
	}

	runs, err := h.auditRepo.ListRunsByPortfolio(portfolioID, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true, "portfolio_id": portfolioID, "runs": runs, "count": len(runs)})
}

// GET /api/v1/data-load/runs/:run_id
func (h *DataLoadHandler) GetRun(c *gin.Context) {
	runID := c.Param("run_id")
	if _, err := uuid.Parse(runID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "run_id must be a valid UUID"})
		return
	}

	run, err := h.auditRepo.GetRun(runID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	events, err := h.auditRepo.ListEvents(runID, 200)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"success": true, "run": run, "events": events, "events_count": len(events)})
}

// GET /api/v1/data-load/runs/:run_id/alert-events
func (h *DataLoadHandler) ListRunAlertEvents(c *gin.Context) {
	runID := c.Param("run_id")
	if _, err := uuid.Parse(runID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "run_id must be a valid UUID"})
		return
	}

	limit := 200
	if v := c.Query("limit"); v != "" {
		if parsed, err := parseInt(v); err == nil {
			limit = parsed
		}
	}

	run, err := h.auditRepo.GetRun(runID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	meta, err := parseRunMetadata(run.Metadata)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	symbolsAny, _ := meta["symbols"].([]any)
	symbols := anySliceToStringSlice(symbolsAny)
	if len(symbols) == 0 {
		c.JSON(http.StatusOK, gin.H{"success": true, "run_id": runID, "since": run.StartedAt, "alert_events": []any{}, "count": 0})
		return
	}

	rows, err := h.auditRepo.ListRunAlertEvents(runID, symbols, run.StartedAt, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success":      true,
		"run_id":       runID,
		"since":        run.StartedAt,
		"symbols":      symbols,
		"alert_events": rows,
		"count":        len(rows),
	})
}

// GET /api/v1/portfolios/:portfolio_id/alerts/summary
// Query params:
// - window_hours (optional, default 24)
func (h *DataLoadHandler) GetPortfolioAlertsSummary(c *gin.Context) {
	portfolioID := c.Param("portfolio_id")
	if _, err := uuid.Parse(portfolioID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "portfolio_id must be a valid UUID"})
		return
	}

	windowHours := 24
	if v := c.Query("window_hours"); v != "" {
		if parsed, err := parseInt(v); err == nil && parsed > 0 {
			windowHours = parsed
		}
	}
	since := time.Now().Add(-time.Duration(windowHours) * time.Hour)

	symbols, err := h.auditRepo.SymbolsForPortfolio(portfolioID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	rows, err := h.auditRepo.PortfolioSymbolsAlertSummary(symbols, since)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	bySymbol := map[string]any{}
	for _, r := range rows {
		bySymbol[r.Symbol] = r
	}

	c.JSON(http.StatusOK, gin.H{
		"success":       true,
		"portfolio_id":  portfolioID,
		"window_hours":  windowHours,
		"symbols_count": len(symbols),
		"rows":          rows,
		"by_symbol":     bySymbol,
	})
}

// GET /api/v1/alerts/events
// Query params:
// - symbol (required)
// - window_hours (optional, default 168)
// - limit (optional, default 200)
func (h *DataLoadHandler) ListAlertEventsForSymbol(c *gin.Context) {
	symbol := c.Query("symbol")
	if symbol == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "symbol is required"})
		return
	}

	windowHours := 168
	if v := c.Query("window_hours"); v != "" {
		if parsed, err := parseInt(v); err == nil && parsed > 0 {
			windowHours = parsed
		}
	}
	limit := 200
	if v := c.Query("limit"); v != "" {
		if parsed, err := parseInt(v); err == nil && parsed > 0 {
			limit = parsed
		}
	}

	since := time.Now().Add(-time.Duration(windowHours) * time.Hour)
	rows, err := h.auditRepo.ListAlertEventsForSymbol(symbol, since, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success":      true,
		"symbol":       symbol,
		"window_hours": windowHours,
		"alert_events": rows,
		"count":        len(rows),
	})
}

// POST /api/v1/data-load/runs/:run_id/rerun-failed
func (h *DataLoadHandler) RerunFailed(c *gin.Context) {
	runID := c.Param("run_id")
	if _, err := uuid.Parse(runID); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "run_id must be a valid UUID"})
		return
	}

	run, err := h.auditRepo.GetRun(runID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	failed, err := h.auditRepo.FailedSymbolsForRun(runID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	meta, _ := parseRunMetadata(run.Metadata)
	dataTypes, _ := meta["data_types"].([]any)
	symbols := failed
	if len(symbols) == 0 {
		// if no failed symbols recorded, fall back to original symbols
		if s, ok := meta["symbols"].([]any); ok {
			symbols = anySliceToStringSlice(s)
		}
	}

	portfolioID, _ := meta["portfolio_id"].(string)

	newRunID := uuid.New().String()
	_ = h.auditRepo.CreateRun(newRunID, "running", map[string]any{
		"operation":    "rerun_failed",
		"portfolio_id": portfolioID,
		"symbols":      symbols,
		"data_types":   dataTypes,
		"rerun_of":     run.RunID,
		"requested_at": time.Now().UTC().Format(time.RFC3339),
	})

	// IMPORTANT: do NOT use c.Request.Context() here. The HTTP request context is cancelled
	// as soon as this handler returns (202 Accepted), which would cancel the background
	// python-worker refresh call and mark the run as failed with "context canceled".
	parentCtx := context.Background()
	symbolsCopy := append([]string(nil), symbols...)
	dataTypesCopy := anySliceToStringSlice(dataTypes)

	go func() {
		ctx, cancel := context.WithTimeout(parentCtx, 30*time.Minute)
		defer cancel()

		_, err := h.pythonWorker.AdminRefreshData(ctx, services.AdminRefreshRequest{
			RunID:       newRunID,
			PortfolioID: portfolioID,
			Symbols:     symbolsCopy,
			DataTypes:   dataTypesCopy,
			Force:       true,
		})
		if err != nil {
			_ = h.auditRepo.UpdateRunStatus(newRunID, "failed", map[string]any{"go_error": err.Error()})
			return
		}
	}()

	c.JSON(http.StatusAccepted, gin.H{"success": true, "new_run_id": newRunID, "rerun_of": run.RunID, "symbols": symbols})
}

// --- helpers (kept private to avoid scattering utils) ---

func parseInt(s string) (int, error) {
	return strconv.Atoi(s)
}

func parseRunMetadata(raw []byte) (map[string]any, error) {
	var m map[string]any
	if len(raw) == 0 {
		return map[string]any{}, nil
	}
	if err := json.Unmarshal(raw, &m); err != nil {
		return map[string]any{}, err
	}
	return m, nil
}

func anySliceToStringSlice(v []any) []string {
	out := make([]string, 0, len(v))
	for _, it := range v {
		if s, ok := it.(string); ok {
			out = append(out, s)
		}
	}
	return out
}
