package handlers

import (
	"bytes"
	"io"
	"net/http"
	"net/url"

	"github.com/gin-gonic/gin"
	"github.com/trading-system/go-api/internal/services"
)

// PortfolioV2ProxyHandler proxies the python-worker Portfolio API v2 so UIs only talk to Go API.
//
// This is a compatibility bridge while we move portfolio/auth/run orchestration fully into Go.
// It forwards Authorization and Content-Type headers.
//
// Mounted under /api/v1/portfolio-v2/*path.
type PortfolioV2ProxyHandler struct {
	pythonWorker *services.PythonWorkerClient
}

func NewPortfolioV2ProxyHandler(pythonWorker *services.PythonWorkerClient) *PortfolioV2ProxyHandler {
	return &PortfolioV2ProxyHandler{pythonWorker: pythonWorker}
}

func (h *PortfolioV2ProxyHandler) Proxy(c *gin.Context) {
	path := c.Param("path")

	base, err := url.Parse(h.pythonWorker.BaseURL)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "invalid python worker base url"})
		return
	}

	// python-worker portfolio v2 lives at /api/v2/portfolio
	reqURL, err := base.Parse("/api/v2/portfolio" + path)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to build python worker url"})
		return
	}

	if raw := c.Request.URL.RawQuery; raw != "" {
		reqURL.RawQuery = raw
	}

	var bodyReader io.Reader
	method := c.Request.Method
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

	if ct := c.GetHeader("Content-Type"); ct != "" {
		req.Header.Set("Content-Type", ct)
	}
	if auth := c.GetHeader("Authorization"); auth != "" {
		req.Header.Set("Authorization", auth)
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
