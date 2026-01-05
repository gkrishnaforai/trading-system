package handlers

import (
	"bytes"
	"io"
	"net/http"
	"net/url"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/services"
)

// AdminProxyHandler proxies admin actions to the python-worker so UIs only need to talk to Go API.
// This keeps a single backend entrypoint while still using python-worker for heavy compute/workflows.
//
// Endpoints are exposed under /api/v1/admin/*.
type AdminProxyHandler struct {
	pythonWorker *services.PythonWorkerClient
}

func NewAdminProxyHandler(pythonWorker *services.PythonWorkerClient) *AdminProxyHandler {
	return &AdminProxyHandler{pythonWorker: pythonWorker}
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

// GET /api/v1/admin/health -> python-worker GET /admin/health
func (h *AdminProxyHandler) GetHealth(c *gin.Context) {
	h.proxy(c, http.MethodGet, "/admin/health")
}

// GET /api/v1/admin/data-sources -> python-worker GET /admin/data-sources
func (h *AdminProxyHandler) GetDataSources(c *gin.Context) {
	h.proxy(c, http.MethodGet, "/admin/data-sources")
}

// POST /api/v1/admin/refresh -> python-worker POST /refresh
func (h *AdminProxyHandler) Refresh(c *gin.Context) {
	h.proxy(c, http.MethodPost, "/refresh")
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
