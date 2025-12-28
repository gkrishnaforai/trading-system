package services

import (
	"fmt"
	"time"

	"github.com/trading-system/go-api/internal/models"
	"github.com/trading-system/go-api/internal/repositories"
)

type WatchlistService struct {
	watchlistRepo *repositories.WatchlistRepository
	portfolioRepo *repositories.PortfolioRepository
	cache         *CacheService
}

func NewWatchlistService(
	watchlistRepo *repositories.WatchlistRepository,
	portfolioRepo *repositories.PortfolioRepository,
	cache *CacheService,
) *WatchlistService {
	return &WatchlistService{
		watchlistRepo: watchlistRepo,
		portfolioRepo: portfolioRepo,
		cache:         cache,
	}
}

// CreateWatchlist creates a new watchlist
func (s *WatchlistService) CreateWatchlist(
	userID string,
	watchlistName string,
	description *string,
	tags *string,
	isDefault bool,
	subscriptionLevel string,
) (*models.Watchlist, error) {
	watchlistID := fmt.Sprintf("watchlist_%s_%d", userID, time.Now().Unix())
	
	watchlist := &models.Watchlist{
		WatchlistID:            watchlistID,
		UserID:                 userID,
		WatchlistName:          watchlistName,
		Description:            description,
		Tags:                   tags,
		IsDefault:              isDefault,
		SubscriptionLevelRequired: subscriptionLevel,
	}
	
	if err := s.watchlistRepo.Create(watchlist); err != nil {
		return nil, fmt.Errorf("failed to create watchlist: %w", err)
	}
	
	// Invalidate cache
	s.cache.Delete(fmt.Sprintf("watchlists:%s", userID))
	
	return watchlist, nil
}

// GetWatchlists gets all watchlists for a user
func (s *WatchlistService) GetWatchlists(userID string, subscriptionLevel string) ([]models.Watchlist, error) {
	// Check cache
	cacheKey := fmt.Sprintf("watchlists:%s", userID)
	var cached []models.Watchlist
	if err := s.cache.Get(cacheKey, &cached); err == nil {
		// Filter by subscription level
		return s.filterWatchlistsBySubscription(cached, subscriptionLevel), nil
	}
	
	watchlists, err := s.watchlistRepo.GetByUserID(userID)
	if err != nil {
		return nil, fmt.Errorf("failed to get watchlists: %w", err)
	}
	
	// Filter by subscription level
	watchlists = s.filterWatchlistsBySubscription(watchlists, subscriptionLevel)
	
	// Cache for 5 minutes
	s.cache.Set(cacheKey, watchlists, 5*time.Minute)
	
	return watchlists, nil
}

// GetWatchlist gets a watchlist with items
func (s *WatchlistService) GetWatchlist(watchlistID string, subscriptionLevel string) (*models.WatchlistWithItems, error) {
	// Check cache
	cacheKey := fmt.Sprintf("watchlist:%s", watchlistID)
	var cached models.WatchlistWithItems
	if err := s.cache.Get(cacheKey, &cached); err == nil {
		return &cached, nil
	}
	
	watchlist, err := s.watchlistRepo.GetByID(watchlistID)
	if err != nil {
		return nil, fmt.Errorf("failed to get watchlist: %w", err)
	}
	
	// Check subscription level
	if !s.hasAccessToWatchlist(watchlist, subscriptionLevel) {
		return nil, fmt.Errorf("watchlist requires %s subscription", watchlist.SubscriptionLevelRequired)
	}
	
	items, err := s.watchlistRepo.GetItems(watchlistID)
	if err != nil {
		return nil, fmt.Errorf("failed to get watchlist items: %w", err)
	}
	
	// Convert to WatchlistItemWithData (stock data will be enriched by Python service)
	itemsWithData := make([]models.WatchlistItemWithData, len(items))
	for i, item := range items {
		itemsWithData[i] = models.WatchlistItemWithData{
			WatchlistItem: item,
		}
	}
	
	result := &models.WatchlistWithItems{
		Watchlist: *watchlist,
		Items:     itemsWithData,
	}
	
	// Cache for 5 minutes
	s.cache.Set(cacheKey, result, 5*time.Minute)
	
	return result, nil
}

// UpdateWatchlist updates a watchlist
func (s *WatchlistService) UpdateWatchlist(watchlistID string, updates map[string]interface{}) error {
	if err := s.watchlistRepo.Update(watchlistID, updates); err != nil {
		return fmt.Errorf("failed to update watchlist: %w", err)
	}
	
	// Invalidate cache
	watchlist, err := s.watchlistRepo.GetByID(watchlistID)
	if err == nil {
		s.cache.Delete(fmt.Sprintf("watchlists:%s", watchlist.UserID))
		s.cache.Delete(fmt.Sprintf("watchlist:%s", watchlistID))
	}
	
	return nil
}

// DeleteWatchlist deletes a watchlist
func (s *WatchlistService) DeleteWatchlist(watchlistID string) error {
	watchlist, err := s.watchlistRepo.GetByID(watchlistID)
	if err != nil {
		return fmt.Errorf("watchlist not found: %w", err)
	}
	
	if err := s.watchlistRepo.Delete(watchlistID); err != nil {
		return fmt.Errorf("failed to delete watchlist: %w", err)
	}
	
	// Invalidate cache
	s.cache.Delete(fmt.Sprintf("watchlists:%s", watchlist.UserID))
	s.cache.Delete(fmt.Sprintf("watchlist:%s", watchlistID))
	
	return nil
}

// AddItem adds a stock to a watchlist
func (s *WatchlistService) AddItem(
	watchlistID string,
	stockSymbol string,
	notes *string,
	priority int,
	tags *string,
) (*models.WatchlistItem, error) {
	itemID := fmt.Sprintf("item_%s_%s_%d", watchlistID, stockSymbol, time.Now().Unix())
	
	item := &models.WatchlistItem{
		ItemID:      itemID,
		WatchlistID: watchlistID,
		StockSymbol: stockSymbol,
		Notes:       notes,
		Priority:    priority,
		Tags:        tags,
	}
	
	if err := s.watchlistRepo.AddItem(item); err != nil {
		return nil, fmt.Errorf("failed to add watchlist item: %w", err)
	}
	
	// Invalidate cache
	s.cache.Delete(fmt.Sprintf("watchlist:%s", watchlistID))
	
	return item, nil
}

// UpdateItem updates a watchlist item
func (s *WatchlistService) UpdateItem(itemID string, updates map[string]interface{}) error {
	if err := s.watchlistRepo.UpdateItem(itemID, updates); err != nil {
		return fmt.Errorf("failed to update watchlist item: %w", err)
	}
	
	// Invalidate cache (need to get watchlist ID from item)
	// For now, we'll invalidate all watchlist caches (can be optimized)
	return nil
}

// RemoveItem removes a stock from a watchlist
func (s *WatchlistService) RemoveItem(itemID string) error {
	if err := s.watchlistRepo.RemoveItem(itemID); err != nil {
		return fmt.Errorf("failed to remove watchlist item: %w", err)
	}
	
	// Invalidate cache
	// Note: We'd need watchlistID to invalidate properly, but for simplicity
	// we'll let cache expire naturally
	return nil
}

// MoveToPortfolio moves a stock from watchlist to portfolio
func (s *WatchlistService) MoveToPortfolio(
	watchlistID string,
	itemID string,
	request *models.MoveToPortfolioRequest,
) (*models.Holding, error) {
	// Get watchlist item
	items, err := s.watchlistRepo.GetItems(watchlistID)
	if err != nil {
		return nil, fmt.Errorf("failed to get watchlist items: %w", err)
	}
	
	var item *models.WatchlistItem
	for i := range items {
		if items[i].ItemID == itemID {
			item = &items[i]
			break
		}
	}
	
	if item == nil {
		return nil, fmt.Errorf("watchlist item not found")
	}
	
	// Parse purchase date
	purchaseDate, err := time.Parse("2006-01-02", request.PurchaseDate)
	if err != nil {
		return nil, fmt.Errorf("invalid purchase_date format: %w", err)
	}
	
	// Create holding
	holdingID := fmt.Sprintf("holding_%s_%s_%d", request.PortfolioID, item.StockSymbol, time.Now().Unix())
	holding := &models.Holding{
		HoldingID:     holdingID,
		PortfolioID:   request.PortfolioID,
		StockSymbol:   item.StockSymbol,
		Quantity:      request.Quantity,
		AvgEntryPrice: request.AvgEntryPrice,
		PositionType:  request.PositionType,
		StrategyTag:   request.StrategyTag,
		Notes:         request.Notes,
		PurchaseDate:  purchaseDate,
	}
	
	if err := s.portfolioRepo.CreateHolding(holding); err != nil {
		return nil, fmt.Errorf("failed to create holding: %w", err)
	}
	
	// Remove from watchlist (optional - could keep it)
	if err := s.watchlistRepo.RemoveItem(itemID); err != nil {
		// Log error but don't fail - holding is already created
		// In production, consider transaction rollback
	}
	
	// Invalidate caches
	s.cache.Delete(fmt.Sprintf("watchlist:%s", watchlistID))
	s.cache.Delete(fmt.Sprintf("portfolio:%s", request.PortfolioID))
	
	return holding, nil
}

// Helper methods

func (s *WatchlistService) filterWatchlistsBySubscription(
	watchlists []models.Watchlist,
	subscriptionLevel string,
) []models.Watchlist {
	levels := map[string]int{
		"basic": 1,
		"pro":   2,
		"elite": 3,
	}
	
	userLevel := levels[subscriptionLevel]
	if userLevel == 0 {
		userLevel = 1 // Default to basic
	}
	
	var filtered []models.Watchlist
	for _, w := range watchlists {
		requiredLevel := levels[w.SubscriptionLevelRequired]
		if userLevel >= requiredLevel {
			filtered = append(filtered, w)
		}
	}
	
	return filtered
}

func (s *WatchlistService) hasAccessToWatchlist(
	watchlist *models.Watchlist,
	subscriptionLevel string,
) bool {
	levels := map[string]int{
		"basic": 1,
		"pro":   2,
		"elite": 3,
	}
	
	userLevel := levels[subscriptionLevel]
	if userLevel == 0 {
		userLevel = 1
	}
	
	requiredLevel := levels[watchlist.SubscriptionLevelRequired]
	return userLevel >= requiredLevel
}

