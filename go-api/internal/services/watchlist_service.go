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
	isDefault bool,
) (*models.Watchlist, error) {
	watchlist := &models.Watchlist{
		UserID:      userID,
		Name:        watchlistName,
		Description: description,
		IsDefault:   isDefault,
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
		return cached, nil
	}

	watchlists, err := s.watchlistRepo.GetByUserID(userID)
	if err != nil {
		return nil, fmt.Errorf("failed to get watchlists: %w", err)
	}

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

	items, err := s.watchlistRepo.GetItems(watchlistID)
	if err != nil {
		return nil, fmt.Errorf("failed to get watchlist items: %w", err)
	}

	// Convert to WatchlistStockWithData (stock data will be enriched by Python service)
	itemsWithData := make([]models.WatchlistStockWithData, len(items))
	for i, item := range items {
		itemsWithData[i] = models.WatchlistStockWithData{
			WatchlistStock: item,
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
) (*models.WatchlistStock, error) {
	_ = notes
	_ = priority
	_ = tags
	item, err := s.watchlistRepo.AddStock(watchlistID, stockSymbol)
	if err != nil {
		return nil, fmt.Errorf("failed to add watchlist stock: %w", err)
	}

	// Invalidate caches
	s.cache.Delete(fmt.Sprintf("watchlist:%s", watchlistID))

	// Also get watchlist to invalidate user's watchlist list cache
	watchlist, err := s.watchlistRepo.GetByID(watchlistID)
	if err == nil {
		s.cache.Delete(fmt.Sprintf("watchlists:%s", watchlist.UserID))
	}

	return item, nil
}

// UpdateItem updates a watchlist item
func (s *WatchlistService) UpdateItem(itemID string, updates map[string]interface{}) error {
	// Get item first to find watchlistID
	item, err := s.watchlistRepo.GetItemByID(itemID)
	if err != nil {
		return fmt.Errorf("failed to get watchlist item: %w", err)
	}

	if err := s.watchlistRepo.UpdateItem(itemID, updates); err != nil {
		return fmt.Errorf("failed to update watchlist item: %w", err)
	}

	// Invalidate watchlist cache
	s.cache.Delete(fmt.Sprintf("watchlist:%s", item.WatchlistID))

	// Also get watchlist to invalidate user's watchlist list cache
	watchlist, err := s.watchlistRepo.GetByID(item.WatchlistID)
	if err == nil {
		s.cache.Delete(fmt.Sprintf("watchlists:%s", watchlist.UserID))
	}

	return nil
}

// RemoveItem removes a stock from a watchlist
func (s *WatchlistService) RemoveItem(itemID string) error {
	// Get item first to find watchlistID
	item, err := s.watchlistRepo.GetItemByID(itemID)
	if err != nil {
		return fmt.Errorf("failed to get watchlist item: %w", err)
	}

	if err := s.watchlistRepo.RemoveItem(itemID); err != nil {
		return fmt.Errorf("failed to remove watchlist item: %w", err)
	}

	// Invalidate watchlist cache
	s.cache.Delete(fmt.Sprintf("watchlist:%s", item.WatchlistID))

	// Also get watchlist to invalidate user's watchlist list cache
	watchlist, err := s.watchlistRepo.GetByID(item.WatchlistID)
	if err == nil {
		s.cache.Delete(fmt.Sprintf("watchlists:%s", watchlist.UserID))
	}

	return nil
}

// MoveToPortfolio moves a stock from watchlist to portfolio
func (s *WatchlistService) MoveToPortfolio(
	watchlistID string,
	itemID string,
	request *models.MoveToPortfolioRequest,
) (*models.PortfolioPosition, error) {
	// Get watchlist item
	items, err := s.watchlistRepo.GetItems(watchlistID)
	if err != nil {
		return nil, fmt.Errorf("failed to get watchlist items: %w", err)
	}

	var item *models.WatchlistStock
	for i := range items {
		if items[i].ID == itemID {
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

	_ = purchaseDate
	position, err := s.portfolioRepo.AddPositionBySymbol(request.PortfolioID, item.Symbol, request.Quantity, request.AvgEntryPrice)
	if err != nil {
		return nil, fmt.Errorf("failed to create portfolio position: %w", err)
	}

	// Remove from watchlist (optional - could keep it)
	if err := s.watchlistRepo.RemoveItem(itemID); err != nil {
		// Log error but don't fail - holding is already created
		// In production, consider transaction rollback
	}

	// Invalidate caches
	s.cache.Delete(fmt.Sprintf("watchlist:%s", watchlistID))

	// Get portfolio to find userID for portfolio cache invalidation
	portfolio, err := s.portfolioRepo.GetByID(request.PortfolioID)
	if err == nil {
		s.cache.Delete(fmt.Sprintf("portfolio:%s:%s", portfolio.UserID, request.PortfolioID))
		s.cache.Delete(fmt.Sprintf("portfolios:%s", portfolio.UserID))
	}

	// Get watchlist to invalidate user's watchlist list cache
	watchlist, err := s.watchlistRepo.GetByID(watchlistID)
	if err == nil {
		s.cache.Delete(fmt.Sprintf("watchlists:%s", watchlist.UserID))
	}

	return position, nil
}
