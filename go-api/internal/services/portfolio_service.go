package services

import (
	"fmt"
	"time"

	"github.com/trading-system/go-api/internal/models"
	"github.com/trading-system/go-api/internal/repositories"
)

type PortfolioService struct {
	portfolioRepo *repositories.PortfolioRepository
	indicatorRepo *repositories.IndicatorRepository
	cache         *CacheService
}

func NewPortfolioService(
	portfolioRepo *repositories.PortfolioRepository,
	indicatorRepo *repositories.IndicatorRepository,
	cache *CacheService,
) *PortfolioService {
	return &PortfolioService{
		portfolioRepo: portfolioRepo,
		indicatorRepo: indicatorRepo,
		cache:         cache,
	}
}

type PortfolioResponse struct {
	Portfolio models.Portfolio           `json:"portfolio"`
	Holdings  []models.PortfolioPosition `json:"holdings"`
	Signals   []models.PortfolioSignal   `json:"signals"`
}

type PortfoliosResponse struct {
	UserID     string             `json:"user_id"`
	Portfolios []models.Portfolio `json:"portfolios"`
	Count      int                `json:"count"`
}

func (s *PortfolioService) GetPortfolios(userID string) (*PortfoliosResponse, error) {
	cacheKey := fmt.Sprintf("portfolios:%s", userID)
	var cached PortfoliosResponse
	if err := s.cache.Get(cacheKey, &cached); err == nil {
		return &cached, nil
	}

	portfolios, err := s.portfolioRepo.GetByUserID(userID)
	if err != nil {
		return nil, fmt.Errorf("failed to get portfolios: %w", err)
	}
	if portfolios == nil {
		portfolios = []models.Portfolio{}
	}

	resp := &PortfoliosResponse{UserID: userID, Portfolios: portfolios, Count: len(portfolios)}
	// Cache for 5 minutes
	_ = s.cache.Set(cacheKey, resp, 5*time.Minute)
	return resp, nil
}

func (s *PortfolioService) GetPortfolio(userID string, portfolioID string, subscriptionLevel string) (*PortfolioResponse, error) {
	// Check cache
	cacheKey := fmt.Sprintf("portfolio:%s:%s", userID, portfolioID)
	var cached PortfolioResponse
	if err := s.cache.Get(cacheKey, &cached); err == nil {
		// Filter signals based on subscription level
		cached.Signals = s.filterSignalsBySubscription(cached.Signals, subscriptionLevel)
		return &cached, nil
	}

	// Get portfolios for user
	portfolios, err := s.portfolioRepo.GetByUserID(userID)
	if err != nil {
		return nil, fmt.Errorf("failed to get portfolios: %w", err)
	}

	// Find the requested portfolio
	var portfolio *models.Portfolio
	for i := range portfolios {
		if portfolios[i].ID == portfolioID {
			portfolio = &portfolios[i]
			break
		}
	}

	if portfolio == nil {
		return nil, fmt.Errorf("portfolio not found")
	}

	// Get holdings
	holdings, err := s.portfolioRepo.GetHoldings(portfolioID)
	if err != nil {
		return nil, fmt.Errorf("failed to get holdings: %w", err)
	}
	// Ensure holdings is never nil (empty slice instead)
	if holdings == nil {
		holdings = []models.PortfolioPosition{}
	}

	// Get signals
	signals, err := s.portfolioRepo.GetSignals(portfolioID)
	if err != nil {
		return nil, fmt.Errorf("failed to get signals: %w", err)
	}
	// Ensure signals is never nil (empty slice instead)
	if signals == nil {
		signals = []models.PortfolioSignal{}
	}

	// Filter signals based on subscription level
	signals = s.filterSignalsBySubscription(signals, subscriptionLevel)

	response := &PortfolioResponse{
		Portfolio: *portfolio,
		Holdings:  holdings,
		Signals:   signals,
	}

	// Cache for 5 minutes
	s.cache.Set(cacheKey, response, 5*time.Minute)

	return response, nil
}

// CreatePortfolio creates a new portfolio
func (s *PortfolioService) CreatePortfolio(userID string, portfolioName string, notes *string) (*models.Portfolio, error) {
	portfolio := &models.Portfolio{
		UserID: userID,
		Name:   portfolioName,
	}
	_ = notes

	if err := s.portfolioRepo.CreatePortfolio(portfolio); err != nil {
		return nil, fmt.Errorf("failed to create portfolio: %w", err)
	}

	// Invalidate cache
	s.cache.Delete(fmt.Sprintf("portfolio:%s:%s", userID, portfolio.ID))
	s.cache.Delete(fmt.Sprintf("portfolios:%s", userID))

	return portfolio, nil
}

// UpdatePortfolio updates an existing portfolio
func (s *PortfolioService) UpdatePortfolio(userID string, portfolioID string, portfolioName *string, notes *string) error {
	if err := s.portfolioRepo.UpdatePortfolio(portfolioID, portfolioName, notes); err != nil {
		return fmt.Errorf("failed to update portfolio: %w", err)
	}

	// Invalidate cache
	s.cache.Delete(fmt.Sprintf("portfolio:%s:%s", userID, portfolioID))
	s.cache.Delete(fmt.Sprintf("portfolios:%s", userID))

	return nil
}

// DeletePortfolio deletes a portfolio
func (s *PortfolioService) DeletePortfolio(userID string, portfolioID string) error {
	if err := s.portfolioRepo.DeletePortfolio(portfolioID); err != nil {
		return fmt.Errorf("failed to delete portfolio: %w", err)
	}

	// Invalidate cache
	s.cache.Delete(fmt.Sprintf("portfolio:%s:%s", userID, portfolioID))
	s.cache.Delete(fmt.Sprintf("portfolios:%s", userID))

	return nil
}

// CreateHolding creates a new portfolio position in a portfolio (by symbol).
func (s *PortfolioService) CreateHolding(portfolioID string, holding *models.PortfolioPosition) error {
	_, err := s.portfolioRepo.AddPositionBySymbol(portfolioID, holding.Symbol, holding.Quantity, holding.AvgPrice)
	if err != nil {
		return fmt.Errorf("failed to create portfolio position: %w", err)
	}

	// Get portfolio to find userID for cache invalidation
	portfolio, err := s.portfolioRepo.GetByID(portfolioID)
	if err == nil {
		// Invalidate portfolio detail and list caches
		s.cache.Delete(fmt.Sprintf("portfolio:%s:%s", portfolio.UserID, portfolioID))
		s.cache.Delete(fmt.Sprintf("portfolios:%s", portfolio.UserID))
	}

	return nil
}

// UpdateHolding updates an existing holding
func (s *PortfolioService) UpdateHolding(holdingID string, updates map[string]interface{}) error {
	// Get holding first to find portfolioID
	holding, err := s.portfolioRepo.GetHoldingByID(holdingID)
	if err != nil {
		return fmt.Errorf("failed to get holding: %w", err)
	}

	if err := s.portfolioRepo.UpdateHolding(holdingID, updates); err != nil {
		return fmt.Errorf("failed to update holding: %w", err)
	}

	// Get portfolio to find userID for cache invalidation
	portfolio, err := s.portfolioRepo.GetByID(holding.PortfolioID)
	if err == nil {
		// Invalidate portfolio detail and list caches
		s.cache.Delete(fmt.Sprintf("portfolio:%s:%s", portfolio.UserID, holding.PortfolioID))
		s.cache.Delete(fmt.Sprintf("portfolios:%s", portfolio.UserID))
	}

	return nil
}

// DeleteHolding deletes a holding
func (s *PortfolioService) DeleteHolding(holdingID string) error {
	// Get holding first to find portfolioID
	holding, err := s.portfolioRepo.GetHoldingByID(holdingID)
	if err != nil {
		return fmt.Errorf("failed to get holding: %w", err)
	}

	if err := s.portfolioRepo.DeleteHolding(holdingID); err != nil {
		return fmt.Errorf("failed to delete holding: %w", err)
	}

	// Get portfolio to find userID for cache invalidation
	portfolio, err := s.portfolioRepo.GetByID(holding.PortfolioID)
	if err == nil {
		// Invalidate portfolio detail and list caches
		s.cache.Delete(fmt.Sprintf("portfolio:%s:%s", portfolio.UserID, holding.PortfolioID))
		s.cache.Delete(fmt.Sprintf("portfolios:%s", portfolio.UserID))
	}

	return nil
}

func (s *PortfolioService) filterSignalsBySubscription(
	signals []models.PortfolioSignal,
	subscriptionLevel string,
) []models.PortfolioSignal {
	levels := map[string]int{
		models.SubscriptionBasic: 1,
		models.SubscriptionPro:   2,
		models.SubscriptionElite: 3,
	}

	userLevel := levels[subscriptionLevel]
	if userLevel == 0 {
		userLevel = 1 // Default to basic
	}

	var filtered []models.PortfolioSignal
	for _, signal := range signals {
		requiredLevel := levels[signal.SubscriptionLevelRequired]
		if userLevel >= requiredLevel {
			filtered = append(filtered, signal)
		}
	}

	return filtered
}
