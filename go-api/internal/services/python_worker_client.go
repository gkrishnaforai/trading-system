package services

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"time"
)

// PythonWorkerClient handles communication with the Python Worker API
type PythonWorkerClient struct {
	BaseURL    string
	HTTPClient *http.Client
}

// RefreshGrades triggers python-worker stock grades refresh for a symbol.
// This is used for analyst-related data types (analyst_ratings, price_targets, consensus_data, stock_grades).
func (c *PythonWorkerClient) RefreshGrades(ctx context.Context, symbol string, dataSource string, includeConsensus bool, forceRefresh bool) error {
	if symbol == "" {
		return fmt.Errorf("symbol is required")
	}
	if dataSource == "" {
		dataSource = "fmp"
	}

	q := url.Values{}
	q.Set("data_source", dataSource)
	q.Set("include_consensus", strconv.FormatBool(includeConsensus))
	q.Set("force_refresh", strconv.FormatBool(forceRefresh))

	url := fmt.Sprintf("%s/api/v1/grades/refresh/%s?%s", c.BaseURL, symbol, q.Encode())

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer([]byte("{}")))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(body))
	}

	return nil
}

// NewPythonWorkerClient creates a new client for Python Worker
func NewPythonWorkerClient(baseURL string) *PythonWorkerClient {
	return &PythonWorkerClient{
		BaseURL: baseURL,
		HTTPClient: &http.Client{
			// Refresh operations can be long-running (full symbol backfills, indicators, etc.).
			// Keep this comfortably above the handler-level refresh timeout.
			Timeout: 45 * time.Minute,
		},
	}
}

// RefreshRequest represents a request to refresh data
type RefreshRequest struct {
	RunID       string   `json:"run_id,omitempty"`
	PortfolioID string   `json:"portfolio_id,omitempty"`
	Symbols     []string `json:"symbols"`
	DataTypes   []string `json:"data_types"`
	Force       bool     `json:"force"`
}

// AdminRefreshRequest is the Option B request shape used by Go API orchestration.
type AdminRefreshRequest struct {
	RunID       string   `json:"run_id"`
	PortfolioID string   `json:"portfolio_id,omitempty"`
	Symbols     []string `json:"symbols"`
	DataTypes   []string `json:"data_types"`
	Force       bool     `json:"force"`
}

// RefreshResponse represents the response from refresh endpoint
type RefreshResponse struct {
	Success bool                   `json:"success"`
	Message string                 `json:"message"`
	Results map[string]interface{} `json:"results"`
}

// RefreshData triggers data refresh for symbols
func (c *PythonWorkerClient) RefreshData(ctx context.Context, req RefreshRequest) (*RefreshResponse, error) {
	url := fmt.Sprintf("%s/api/v1/refresh", c.BaseURL)

	jsonData, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(body))
	}

	var refreshResp RefreshResponse
	if err := json.NewDecoder(resp.Body).Decode(&refreshResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &refreshResp, nil
}

// AdminRefreshData triggers admin refresh (python-worker /admin/refresh) with a caller-provided run_id.
func (c *PythonWorkerClient) AdminRefreshData(ctx context.Context, req AdminRefreshRequest) (*RefreshResponse, error) {
	url := fmt.Sprintf("%s/admin/refresh", c.BaseURL)

	jsonData, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(body))
	}

	var refreshResp RefreshResponse
	if err := json.NewDecoder(resp.Body).Decode(&refreshResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &refreshResp, nil
}

// SignalRequest represents a request to generate signals
type SignalRequest struct {
	Symbols  []string `json:"symbols"`
	Strategy string   `json:"strategy"`
}

// PythonWorkerSignalResponse represents the response from Python Worker signals endpoint
type PythonWorkerSignalResponse struct {
	Signals        []Signal `json:"signals"`
	TotalRequested int      `json:"total_requested"`
	TotalGenerated int      `json:"total_generated"`
}

// Signal represents a trading signal
type Signal struct {
	Symbol     string  `json:"symbol"`
	Signal     string  `json:"signal"`
	Confidence float64 `json:"confidence"`
	Strategy   string  `json:"strategy"`
	Timestamp  string  `json:"timestamp"`
}

// GenerateSignals generates trading signals for symbols
func (c *PythonWorkerClient) GenerateSignals(ctx context.Context, req SignalRequest) (*PythonWorkerSignalResponse, error) {
	url := fmt.Sprintf("%s/signals/generate", c.BaseURL)

	jsonData, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(body))
	}

	var signalResp PythonWorkerSignalResponse
	if err := json.NewDecoder(resp.Body).Decode(&signalResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &signalResp, nil
}

// ScreenerRequest represents a request to run screener
type ScreenerRequest struct {
	MinRSI     *float64 `json:"min_rsi,omitempty"`
	MaxRSI     *float64 `json:"max_rsi,omitempty"`
	MinSMA50   *float64 `json:"min_sma_50,omitempty"`
	MaxPERatio *float64 `json:"max_pe_ratio,omitempty"`
	Limit      int      `json:"limit"`
}

// ScreenerResponse represents the response from screener endpoint
type ScreenerResponse struct {
	Stocks   []ScreenerStock `json:"stocks"`
	Count    int             `json:"count"`
	Criteria ScreenerRequest `json:"criteria"`
}

// ScreenerStock represents a stock from screener results
type ScreenerStock struct {
	Symbol string  `json:"symbol"`
	RSI    float64 `json:"rsi"`
	SMA50  float64 `json:"sma_50"`
	Price  float64 `json:"price"`
	Volume string  `json:"volume"`
}

// RunScreener runs stock screener with criteria
func (c *PythonWorkerClient) RunScreener(ctx context.Context, req ScreenerRequest) (*ScreenerResponse, error) {
	url := fmt.Sprintf("%s/screener/run", c.BaseURL)

	jsonData, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(body))
	}

	var screenerResp ScreenerResponse
	if err := json.NewDecoder(resp.Body).Decode(&screenerResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &screenerResp, nil
}

// HealthResponse represents health check response
type HealthResponse struct {
	Status    string                 `json:"status"`
	Database  map[string]interface{} `json:"database"`
	Timestamp string                 `json:"timestamp"`
}

// StockInsightsRequest represents a request to generate stock insights
type StockInsightsRequest struct {
	Symbol           string `json:"symbol"`
	RunAllStrategies bool   `json:"run_all_strategies"`
}

// StockInsightsResponse represents the response from stock insights endpoint
type StockInsightsResponse struct {
	Symbol                string                 `json:"symbol"`
	Timestamp             string                 `json:"timestamp"`
	AnalysisSections      map[string]interface{} `json:"analysis_sections"`
	OverallRecommendation map[string]interface{} `json:"overall_recommendation"`
	StrategyComparison    []StrategyResult       `json:"strategy_comparison"`
	Metadata              map[string]interface{} `json:"metadata"`
}

// StrategyResult represents a single strategy result
type StrategyResult struct {
	Name          string                 `json:"name"`
	Description   string                 `json:"description"`
	Signal        string                 `json:"signal"`
	Confidence    float64                `json:"confidence"`
	Reason        string                 `json:"reason"`
	Metadata      map[string]interface{} `json:"metadata"`
	ExecutionTime string                 `json:"execution_time"`
}

// StrategiesResponse represents the response from strategies endpoint
type StrategiesResponse struct {
	Strategies map[string]string `json:"strategies"`
	Total      int               `json:"total"`
}

// SingleStrategyResponse represents the response from single strategy execution
type SingleStrategyResponse struct {
	Symbol    string         `json:"symbol"`
	Strategy  StrategyResult `json:"strategy"`
	Timestamp string         `json:"timestamp"`
}

// CheckHealth checks the health of Python Worker
func (c *PythonWorkerClient) CheckHealth(ctx context.Context) (*HealthResponse, error) {
	url := fmt.Sprintf("%s/health", c.BaseURL)

	httpReq, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("health check failed with status %d: %s", resp.StatusCode, string(body))
	}

	var healthResp HealthResponse
	if err := json.NewDecoder(resp.Body).Decode(&healthResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &healthResp, nil
}

// GenerateStockInsights generates comprehensive stock insights with strategy comparison
func (c *PythonWorkerClient) GenerateStockInsights(ctx context.Context, req StockInsightsRequest) (*StockInsightsResponse, error) {
	url := fmt.Sprintf("%s/insights/generate", c.BaseURL)

	jsonData, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(body))
	}

	var insightsResp StockInsightsResponse
	if err := json.NewDecoder(resp.Body).Decode(&insightsResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &insightsResp, nil
}

// GetAvailableStrategies gets list of all available trading strategies
func (c *PythonWorkerClient) GetAvailableStrategies(ctx context.Context) (*StrategiesResponse, error) {
	url := fmt.Sprintf("%s/insights/strategies", c.BaseURL)

	httpReq, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(body))
	}

	var strategiesResp StrategiesResponse
	if err := json.NewDecoder(resp.Body).Decode(&strategiesResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &strategiesResp, nil
}

// RunSingleStrategy runs a single strategy for a symbol
func (c *PythonWorkerClient) RunSingleStrategy(ctx context.Context, symbol, strategyName string) (*SingleStrategyResponse, error) {
	url := fmt.Sprintf("%s/insights/strategy/%s", c.BaseURL, strategyName)

	// Create request body with symbol
	requestBody := map[string]string{"symbol": symbol}
	jsonData, err := json.Marshal(requestBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.HTTPClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("request failed with status %d: %s", resp.StatusCode, string(body))
	}

	var strategyResp SingleStrategyResponse
	if err := json.NewDecoder(resp.Body).Decode(&strategyResp); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &strategyResp, nil
}
