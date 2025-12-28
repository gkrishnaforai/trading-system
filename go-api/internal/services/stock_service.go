package services

import (
	"context"
	"fmt"
	"time"

	"github.com/trading-system/go-api/internal/models"
	"github.com/trading-system/go-api/internal/repositories"
)

type StockService struct {
	indicatorRepo      *repositories.IndicatorRepository
	marketDataRepo     *repositories.MarketDataRepository
	cache              *CacheService
	pythonWorkerClient *PythonWorkerClient
}

func NewStockService(
	indicatorRepo *repositories.IndicatorRepository,
	marketDataRepo *repositories.MarketDataRepository,
	cache *CacheService,
	pythonWorkerURL string,
) *StockService {
	return &StockService{
		indicatorRepo:      indicatorRepo,
		marketDataRepo:     marketDataRepo,
		cache:              cache,
		pythonWorkerClient: NewPythonWorkerClient(pythonWorkerURL),
	}
}

type StockResponse struct {
	Symbol     string                       `json:"symbol"`
	Indicators *models.AggregatedIndicators `json:"indicators"`
	Signal     *SignalResponse              `json:"signal,omitempty"`
}

type SignalResponse struct {
	Type         string        `json:"type"`
	Reason       string        `json:"reason"`
	PullbackZone *PullbackZone `json:"pullback_zone,omitempty"`
	StopLoss     *float64      `json:"stop_loss,omitempty"`
}

type PullbackZone struct {
	Lower float64 `json:"lower"`
	Upper float64 `json:"upper"`
}

func (s *StockService) GetStock(symbol string, subscriptionLevel string) (*StockResponse, error) {
	// Check cache
	cacheKey := fmt.Sprintf("stock:%s", symbol)
	var cached StockResponse
	if err := s.cache.Get(cacheKey, &cached); err == nil {
		// Filter based on subscription
		cached = *s.filterBySubscription(cached, subscriptionLevel)
		return &cached, nil
	}

	// Get latest indicators
	indicators, err := s.indicatorRepo.GetLatest(symbol)
	if err != nil {
		return nil, fmt.Errorf("failed to get indicators: %w", err)
	}

	response := &StockResponse{
		Symbol:     symbol,
		Indicators: indicators,
	}

	// Generate signal response
	if indicators.Signal != nil {
		response.Signal = s.generateSignalResponse(indicators, subscriptionLevel)
	}

	// Filter based on subscription
	response = s.filterBySubscription(*response, subscriptionLevel)

	// Cache for 5 minutes
	s.cache.Set(cacheKey, response, 5*time.Minute)

	return response, nil
}

func (s *StockService) filterBySubscription(response StockResponse, subscriptionLevel string) *StockResponse {
	levels := map[string]int{
		models.SubscriptionBasic: 1,
		models.SubscriptionPro:   2,
		models.SubscriptionElite: 3,
	}

	userLevel := levels[subscriptionLevel]
	if userLevel == 0 {
		userLevel = 1
	}

	// Basic users: only core indicators
	if userLevel < 2 {
		// Remove advanced indicators
		response.Indicators.MomentumScore = nil
		response.Indicators.PullbackZoneLower = nil
		response.Indicators.PullbackZoneUpper = nil
		response.Signal.PullbackZone = nil
	}

	// Pro users: get momentum but not all advanced features
	if userLevel < 3 {
		// Elite-only features would be filtered here
	}

	return &response
}

func (s *StockService) generateSignalResponse(
	indicators *models.AggregatedIndicators,
	subscriptionLevel string,
) *SignalResponse {
	if indicators.Signal == nil {
		return nil
	}

	signal := &SignalResponse{
		Type: *indicators.Signal,
	}

	// Generate reason based on indicators
	reason := s.generateReason(indicators)
	signal.Reason = reason

	// Add pullback zone for Pro/Elite
	levels := map[string]int{
		models.SubscriptionBasic: 1,
		models.SubscriptionPro:   2,
		models.SubscriptionElite: 3,
	}
	userLevel := levels[subscriptionLevel]
	if userLevel >= 2 && indicators.PullbackZoneLower != nil && indicators.PullbackZoneUpper != nil {
		signal.PullbackZone = &PullbackZone{
			Lower: *indicators.PullbackZoneLower,
			Upper: *indicators.PullbackZoneUpper,
		}
	}

	// Add stop loss for Pro/Elite
	if userLevel >= 2 && indicators.ATR != nil {
		// Calculate stop loss (simplified)
		if indicators.SMA50 != nil {
			stopLoss := *indicators.SMA50 - (*indicators.ATR * 2)
			signal.StopLoss = &stopLoss
		}
	}

	return signal
}

func (s *StockService) generateReason(indicators *models.AggregatedIndicators) string {
	if indicators.Signal == nil {
		return "No signal available"
	}

	signal := *indicators.Signal
	reason := fmt.Sprintf("%s signal based on ", signal)

	if indicators.LongTermTrend != nil {
		reason += fmt.Sprintf("long-term trend: %s, ", *indicators.LongTermTrend)
	}
	if indicators.MediumTermTrend != nil {
		reason += fmt.Sprintf("medium-term trend: %s, ", *indicators.MediumTermTrend)
	}
	if indicators.RSI != nil {
		reason += fmt.Sprintf("RSI: %.1f, ", *indicators.RSI)
	}
	if indicators.MACD != nil && indicators.MACDSignal != nil {
		if *indicators.MACD > *indicators.MACDSignal {
			reason += "MACD bullish, "
		} else {
			reason += "MACD bearish, "
		}
	}

	// Remove trailing comma
	if len(reason) > 0 && reason[len(reason)-2:] == ", " {
		reason = reason[:len(reason)-2]
	}

	return reason
}

func (s *StockService) GetFundamentals(symbol string) (*repositories.FundamentalData, error) {
	return s.marketDataRepo.GetLatestFundamentals(symbol)
}

func (s *StockService) GetNews(symbol string, limit int) ([]repositories.NewsArticle, error) {
	return s.marketDataRepo.GetLatestNews(symbol, limit)
}

func (s *StockService) GetEarnings(symbol string, limit int) ([]repositories.EarningsData, error) {
	return s.marketDataRepo.GetEarnings(symbol, limit)
}

func (s *StockService) GetIndustryPeers(symbol string) (*repositories.IndustryPeersData, error) {
	return s.marketDataRepo.GetIndustryPeers(symbol)
}

func (s *StockService) GetVolumeData(symbol string, days int) ([]repositories.VolumeDataPoint, error) {
	return s.marketDataRepo.GetVolumeData(symbol, days)
}

// RefreshData triggers data refresh for symbols using Python Worker
func (s *StockService) RefreshData(ctx context.Context, symbols []string, dataTypes []string, force bool) (*RefreshResponse, error) {
	req := RefreshRequest{
		Symbols:   symbols,
		DataTypes: dataTypes,
		Force:     force,
	}

	return s.pythonWorkerClient.RefreshData(ctx, req)
}

// GenerateSignals generates trading signals using Python Worker
func (s *StockService) GenerateSignals(ctx context.Context, symbols []string, strategy string) (*PythonWorkerSignalResponse, error) {
	req := SignalRequest{
		Symbols:  symbols,
		Strategy: strategy,
	}

	return s.pythonWorkerClient.GenerateSignals(ctx, req)
}

// RunScreener runs stock screener using Python Worker
func (s *StockService) RunScreener(ctx context.Context, req ScreenerRequest) (*ScreenerResponse, error) {
	return s.pythonWorkerClient.RunScreener(ctx, req)
}

// CheckPythonWorkerHealth checks the health of Python Worker
func (s *StockService) CheckPythonWorkerHealth(ctx context.Context) (*HealthResponse, error) {
	return s.pythonWorkerClient.CheckHealth(ctx)
}
