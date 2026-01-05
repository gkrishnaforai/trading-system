package services

import (
	"context"
	"fmt"
	"time"

	"github.com/trading-system/go-api/internal/repositories"
)

type TickerService struct {
	tickerRepo *repositories.TickerRepository
	cache      *CacheService
}

func NewTickerService(tickerRepo *repositories.TickerRepository, cache *CacheService) *TickerService {
	return &TickerService{
		tickerRepo: tickerRepo,
		cache:      cache,
	}
}

// SearchTickers searches tickers by query; cached for 10 minutes
func (s *TickerService) SearchTickers(ctx context.Context, query string, limit int) ([]repositories.Ticker, error) {
	cacheKey := fmt.Sprintf("tickers:search:%s:%d", query, limit)
	var cached []repositories.Ticker
	if err := s.cache.Get(cacheKey, &cached); err == nil {
		return cached, nil
	}
	tickers, err := s.tickerRepo.SearchTickers(query, limit)
	if err != nil {
		return nil, err
	}
	// Cache for 10 minutes
	if s.cache != nil {
		s.cache.Set(cacheKey, tickers, 10*time.Minute)
	}
	return tickers, nil
}

// GetTickerBySymbol returns a ticker by symbol; cached for 1 hour
func (s *TickerService) GetTickerBySymbol(ctx context.Context, symbol string) (*repositories.Ticker, error) {
	cacheKey := fmt.Sprintf("ticker:%s", symbol)
	var cached repositories.Ticker
	if err := s.cache.Get(cacheKey, &cached); err == nil {
		return &cached, nil
	}
	ticker, err := s.tickerRepo.GetTickerBySymbol(symbol)
	if err != nil {
		return nil, err
	}
	// Cache for 1 hour
	if s.cache != nil {
		s.cache.Set(cacheKey, ticker, 1*time.Hour)
	}
	return ticker, nil
}
