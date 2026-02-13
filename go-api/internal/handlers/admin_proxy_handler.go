package handlers

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/services"
)

// AdminProxyHandler proxies admin actions to the python-worker so UIs only need to talk to Go API.
// This keeps a single backend entrypoint while still using python-worker for heavy compute/workflows.
//
// Endpoints are exposed under /api/v1/admin/*.
type AdminProxyHandler struct {
	pythonWorker *services.PythonWorkerClient
	cache        *services.CacheService
}

func NewAdminProxyHandler(pythonWorker *services.PythonWorkerClient, cache *services.CacheService) *AdminProxyHandler {
	return &AdminProxyHandler{pythonWorker: pythonWorker, cache: cache}
}

func (h *AdminProxyHandler) proxy(c *gin.Context, method string, path string) {
	base, err := url.Parse(h.pythonWorker.BaseURL)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "invalid python worker base url"})
		return
	}

	reqURL, err := base.Parse(path)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to build python worker url"})
		return
	}

	// Preserve query string
	if raw := c.Request.URL.RawQuery; raw != "" {
		reqURL.RawQuery = raw
	}

	var bodyReader io.Reader
	if method == http.MethodPost || method == http.MethodPut || method == http.MethodPatch {
		b, _ := io.ReadAll(c.Request.Body)
		bodyReader = bytes.NewReader(b)
	} else {
		bodyReader = nil
	}

	req, err := http.NewRequestWithContext(c.Request.Context(), method, reqURL.String(), bodyReader)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create request"})
		return
	}

	// Forward content type for JSON bodies
	if ct := c.GetHeader("Content-Type"); ct != "" {
		req.Header.Set("Content-Type", ct)
	}

	resp, err := h.pythonWorker.HTTPClient.Do(req)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)
	contentType := resp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "application/json"
	}

	c.Data(resp.StatusCode, contentType, respBody)
}

// GET /api/v1/admin/health -> python-worker GET /health
func (h *AdminProxyHandler) GetHealth(c *gin.Context) {
	h.proxy(c, http.MethodGet, "/health")
}

// GET /api/v1/admin/data-sources -> python-worker GET /admin/data-sources
func (h *AdminProxyHandler) GetDataSources(c *gin.Context) {
	h.proxy(c, http.MethodGet, "/admin/data-sources")
}

// POST /api/v1/admin/refresh -> python-worker POST /refresh
func (h *AdminProxyHandler) Refresh(c *gin.Context) {
	// Read request body once so we can both proxy it and invalidate cache afterwards.
	b, _ := io.ReadAll(c.Request.Body)
	c.Request.Body = io.NopCloser(bytes.NewReader(b))

	// Best-effort symbol extraction for cache invalidation.
	symbols := []string{}
	if len(b) > 0 {
		var payload struct {
			Symbols []string `json:"symbols"`
		}
		if err := json.Unmarshal(b, &payload); err == nil {
			symbols = payload.Symbols
		}
	}

	// Proxy to python-worker.
	h.proxy(c, http.MethodPost, "/admin/refresh")

	// Invalidate cached stock indicator responses so Streamlit sees fresh MACD immediately.
	if h.cache == nil {
		return
	}
	for _, sym := range symbols {
		s := strings.TrimSpace(strings.ToUpper(sym))
		if s == "" {
			continue
		}
		_ = h.cache.Delete(fmt.Sprintf("stock:%s", s))
	}
}

// GET /api/v1/admin/refresh/status -> python-worker GET /admin/refresh/status
func (h *AdminProxyHandler) GetRefreshStatus(c *gin.Context) {
	h.proxy(c, http.MethodGet, "/admin/refresh/status")
}

// GET /api/v1/admin/data-summary/:table -> python-worker GET /admin/data-summary/:table
func (h *AdminProxyHandler) GetDataSummary(c *gin.Context) {
	table := c.Param("table")
	h.proxy(c, http.MethodGet, "/admin/data-summary/"+table)
}

// GET /api/v1/admin/audit-logs -> python-worker GET /admin/audit-logs
func (h *AdminProxyHandler) GetAuditLogs(c *gin.Context) {
	h.proxy(c, http.MethodGet, "/admin/audit-logs")
}

// POST /api/v1/admin/signals/generate -> python-worker POST /admin/signals/generate
func (h *AdminProxyHandler) GenerateSignals(c *gin.Context) {
	h.proxy(c, http.MethodPost, "/admin/signals/generate")
}

// GET /api/v1/admin/signals/recent -> python-worker GET /signals/recent
func (h *AdminProxyHandler) GetRecentSignals(c *gin.Context) {
	h.proxy(c, http.MethodGet, "/signals/recent")
}

// POST /api/v1/admin/screener/run -> python-worker POST /admin/screener/run
func (h *AdminProxyHandler) RunScreener(c *gin.Context) {
	h.proxy(c, http.MethodPost, "/admin/screener/run")
}

// GET /api/v1/admin/screener/results/:id -> python-worker GET /screener/results/:id
func (h *AdminProxyHandler) GetScreenerResults(c *gin.Context) {
	id := c.Param("id")
	h.proxy(c, http.MethodGet, "/screener/results/"+id)
}

// POST /api/v1/admin/insights/generate -> python-worker POST /admin/insights/generate
func (h *AdminProxyHandler) GenerateStockInsights(c *gin.Context) {
	h.proxy(c, http.MethodPost, "/admin/insights/generate")
}

// GET /api/v1/admin/insights/strategies -> python-worker GET /admin/insights/strategies
func (h *AdminProxyHandler) GetAvailableStrategies(c *gin.Context) {
	h.proxy(c, http.MethodGet, "/admin/insights/strategies")
}

// POST /api/v1/admin/insights/strategy/:strategyName -> python-worker POST /admin/insights/strategy/:strategyName
func (h *AdminProxyHandler) RunSingleStrategy(c *gin.Context) {
	strategyName := c.Param("strategyName")
	h.proxy(c, http.MethodPost, "/admin/insights/strategy/"+strategyName)
}

// GET /api/v1/admin/earnings-calendar -> python-worker GET /admin/earnings-calendar
func (h *AdminProxyHandler) GetEarningsCalendar(c *gin.Context) {
	h.proxy(c, http.MethodGet, "/admin/earnings-calendar")
}

// POST /api/v1/admin/earnings-calendar/refresh -> python-worker POST /admin/earnings-calendar/refresh
func (h *AdminProxyHandler) RefreshEarningsCalendar(c *gin.Context) {
	h.proxy(c, http.MethodPost, "/admin/earnings-calendar/refresh")
}

// POST /api/v1/admin/earnings-calendar/refresh-for-date -> python-worker POST /admin/earnings-calendar/refresh-for-date
func (h *AdminProxyHandler) RefreshEarningsForDate(c *gin.Context) {
	h.proxy(c, http.MethodPost, "/admin/earnings-calendar/refresh-for-date")
}

// POST /api/v1/admin/swing/signal -> python-worker POST /api/v1/swing/signal
func (h *AdminProxyHandler) SwingSignal(c *gin.Context) {
	h.proxy(c, http.MethodPost, "/api/v1/swing/signal")
}

// POST /api/v1/admin/swing/risk/check -> python-worker POST /api/v1/swing/risk/check
func (h *AdminProxyHandler) SwingRiskCheck(c *gin.Context) {
	h.proxy(c, http.MethodPost, "/api/v1/swing/risk/check")
}

// GET /api/v1/stocks/:symbol/coverage -> python-worker GET /api/v1/stocks/:symbol/coverage
func (h *AdminProxyHandler) GetStockCoverage(c *gin.Context) {
	symbol := c.Param("symbol")
	h.proxy(c, http.MethodGet, "/api/v1/stocks/"+symbol+"/coverage")
}

// POST /api/v1/admin/universal/signal/universal -> python-worker POST /api/v1/universal/signal/universal
func (h *AdminProxyHandler) UniversalSignal(c *gin.Context) {
	// Read request body once so we can both proxy it and extract the symbol for fundamentals overlay.
	b, _ := io.ReadAll(c.Request.Body)
	c.Request.Body = io.NopCloser(bytes.NewReader(b))

	symbol := ""
	if len(b) > 0 {
		var payload struct {
			Symbol string `json:"symbol"`
		}
		if err := json.Unmarshal(b, &payload); err == nil {
			symbol = strings.TrimSpace(strings.ToUpper(payload.Symbol))
		}
	}

	base, err := url.Parse(h.pythonWorker.BaseURL)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "invalid python worker base url"})
		return
	}

	reqURL, err := base.Parse("/api/v1/universal/signal/universal")
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to build python worker url"})
		return
	}

	// Preserve query string
	if raw := c.Request.URL.RawQuery; raw != "" {
		reqURL.RawQuery = raw
	}

	proxyReq, err := http.NewRequestWithContext(c.Request.Context(), http.MethodPost, reqURL.String(), bytes.NewReader(b))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create request"})
		return
	}
	if ct := c.GetHeader("Content-Type"); ct != "" {
		proxyReq.Header.Set("Content-Type", ct)
	}

	proxyResp, err := h.pythonWorker.HTTPClient.Do(proxyReq)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}
	defer proxyResp.Body.Close()

	proxyBody, _ := io.ReadAll(proxyResp.Body)
	contentType := proxyResp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "application/json"
	}

	// Only attempt enrichment for JSON 200 responses.
	if proxyResp.StatusCode != http.StatusOK || !strings.Contains(strings.ToLower(contentType), "application/json") {
		c.Data(proxyResp.StatusCode, contentType, proxyBody)
		return
	}

	var respObj map[string]any
	if err := json.Unmarshal(proxyBody, &respObj); err != nil {
		c.Data(proxyResp.StatusCode, contentType, proxyBody)
		return
	}

	dataObj, _ := respObj["data"].(map[string]any)
	if dataObj == nil {
		c.Data(proxyResp.StatusCode, contentType, proxyBody)
		return
	}

	overlay := map[string]any{
		"risk_state":                "UNKNOWN",
		"position_size_multiplier":  1.0,
		"confidence_cap":            1.0,
		"active_fundamental_alerts": []any{},
	}

	// Best-effort fundamentals overlay from fundamentals change events.
	if symbol != "" {
		evURL, err := base.Parse("/api/v1/fundamentals/events/" + symbol + "?limit=20")
		if err == nil {
			evReq, err := http.NewRequestWithContext(c.Request.Context(), http.MethodGet, evURL.String(), nil)
			if err == nil {
				evResp, err := h.pythonWorker.HTTPClient.Do(evReq)
				if err == nil {
					defer evResp.Body.Close()
					if evResp.StatusCode == http.StatusOK {
						evBody, _ := io.ReadAll(evResp.Body)
						var evObj map[string]any
						if err := json.Unmarshal(evBody, &evObj); err == nil {
							// Determine risk state from event severities.
							risk := "GREEN"
							maxSeverity := ""
							alerts := []any{}
							if events, ok := evObj["events"].([]any); ok {
								for i := 0; i < len(events); i++ {
									e, ok := events[i].(map[string]any)
									if !ok {
										continue
									}
									sev, _ := e["severity"].(string)
									header, _ := e["headline"].(string)
									sev = strings.ToUpper(strings.TrimSpace(sev))
									if maxSeverity == "" {
										maxSeverity = sev
									}
									switch sev {
									case "CRITICAL", "HIGH":
										maxSeverity = "HIGH"
									case "MEDIUM":
										if maxSeverity != "HIGH" {
											maxSeverity = "MEDIUM"
										}
									case "LOW":
										if maxSeverity == "" {
											maxSeverity = "LOW"
										}
									}
									if strings.TrimSpace(header) != "" && len(alerts) < 3 {
										alerts = append(alerts, header)
									}
								}
							}

							switch maxSeverity {
							case "HIGH":
								risk = "RED"
							case "MEDIUM":
								risk = "YELLOW"
							case "LOW", "":
								risk = "GREEN"
							}

							overlay["risk_state"] = risk
							switch risk {
							case "GREEN":
								overlay["position_size_multiplier"] = 1.0
								overlay["confidence_cap"] = 1.0
							case "YELLOW":
								overlay["position_size_multiplier"] = 0.5
								overlay["confidence_cap"] = 0.65
							case "RED":
								overlay["position_size_multiplier"] = 0.2
								overlay["confidence_cap"] = 0.45
							default:
								// keep defaults
							}

							overlay["active_fundamental_alerts"] = alerts
						}
					}
				}
			}
		}
	}

	// Optional hard gate: prevent BUY when fundamentals risk is RED.
	// Enable via env var FUNDAMENTALS_BUY_HARD_GATE=true
	if v := strings.TrimSpace(strings.ToLower(os.Getenv("FUNDAMENTALS_BUY_HARD_GATE"))); v == "true" {
		if rs, ok := overlay["risk_state"].(string); ok && rs == "RED" {
			// Best-effort: look for a top-level action/signal field and override BUY -> HOLD.
			if act, ok := dataObj["action"].(string); ok && strings.EqualFold(act, "BUY") {
				dataObj["action"] = "HOLD"
			}
			if sig, ok := dataObj["signal"].(string); ok && strings.EqualFold(sig, "BUY") {
				dataObj["signal"] = "HOLD"
			}
		}
	}

	dataObj["fundamentals_overlay"] = overlay
	respObj["data"] = dataObj

	out, err := json.Marshal(respObj)
	if err != nil {
		c.Data(proxyResp.StatusCode, contentType, proxyBody)
		return
	}

	c.Data(proxyResp.StatusCode, contentType, out)
}

// GET /api/v1/admin/growth-quality/*path -> python-worker GET /api/v1/growth-quality/*path
func (h *AdminProxyHandler) GrowthQualityGet(c *gin.Context) {
	path := c.Param("path")
	h.proxy(c, http.MethodGet, "/api/v1/growth-quality"+path)
}

// POST /api/v1/admin/growth-quality/*path -> python-worker POST /api/v1/growth-quality/*path
func (h *AdminProxyHandler) GrowthQualityPost(c *gin.Context) {
	path := c.Param("path")
	h.proxy(c, http.MethodPost, "/api/v1/growth-quality"+path)
}

// GET /api/v1/admin/fundamentals/*path -> python-worker GET /api/v1/fundamentals/*path
func (h *AdminProxyHandler) FundamentalsGet(c *gin.Context) {
	path := c.Param("path")
	h.proxy(c, http.MethodGet, "/api/v1/fundamentals"+path)
}

// Rating Alerts proxy
// GET /api/v1/admin/rating-alerts/*path -> python-worker GET /api/v1/rating-alerts/*path
func (h *AdminProxyHandler) RatingAlertsGet(c *gin.Context) {
	path := c.Param("path")
	h.proxy(c, http.MethodGet, "/api/v1/rating-alerts"+path)
}

// POST /api/v1/admin/rating-alerts/*path -> python-worker POST /api/v1/rating-alerts/*path
func (h *AdminProxyHandler) RatingAlertsPost(c *gin.Context) {
	path := c.Param("path")
	h.proxy(c, http.MethodPost, "/api/v1/rating-alerts"+path)
}

// PUT /api/v1/admin/rating-alerts/*path -> python-worker PUT /api/v1/rating-alerts/*path
func (h *AdminProxyHandler) RatingAlertsPut(c *gin.Context) {
	path := c.Param("path")
	h.proxy(c, http.MethodPut, "/api/v1/rating-alerts"+path)
}

// DELETE /api/v1/admin/rating-alerts/*path -> python-worker DELETE /api/v1/rating-alerts/*path
func (h *AdminProxyHandler) RatingAlertsDelete(c *gin.Context) {
	path := c.Param("path")
	h.proxy(c, http.MethodDelete, "/api/v1/rating-alerts"+path)
}
