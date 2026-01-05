package handlers

import (
	"net/http"
	"sort"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/trading-system/go-api/internal/services"
)

type SymbolScopeHandler struct {
	watchlistService *services.WatchlistService
	portfolioService *services.PortfolioService
	cache            *services.CacheService
}

type SymbolScopeResolveResponse struct {
	Symbols []string `json:"symbols"`
	Count   int      `json:"count"`
}

func NewSymbolScopeHandler(watchlistService *services.WatchlistService, portfolioService *services.PortfolioService, cache *services.CacheService) *SymbolScopeHandler {
	return &SymbolScopeHandler{
		watchlistService: watchlistService,
		portfolioService: portfolioService,
		cache:            cache,
	}
}

// Resolve handles GET /api/v1/symbol-scope/resolve
// Query params:
// - user_id (required when portfolio_id is provided)
// - watchlist_id (optional)
// - portfolio_id (optional)
// - subscription_level (optional, defaults to basic)
func (h *SymbolScopeHandler) Resolve(c *gin.Context) {
	subscriptionLevel := c.Query("subscription_level")
	if subscriptionLevel == "" {
		subscriptionLevel = "basic"
	}

	watchlistID := c.Query("watchlist_id")
	portfolioID := c.Query("portfolio_id")
	userID := c.Query("user_id")

	if watchlistID == "" && portfolioID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "watchlist_id or portfolio_id is required"})
		return
	}
	if portfolioID != "" && userID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "user_id is required when portfolio_id is provided"})
		return
	}
	if userID != "" {
		if _, err := uuid.Parse(userID); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "user_id must be a valid UUID"})
			return
		}
	}

	cacheKey := "symbol_scope:v1:sub:" + subscriptionLevel + ":u:" + userID + ":w:" + watchlistID + ":p:" + portfolioID
	if h.cache != nil {
		var cached SymbolScopeResolveResponse
		if err := h.cache.Get(cacheKey, &cached); err == nil {
			c.JSON(http.StatusOK, cached)
			return
		}
	}

	set := map[string]struct{}{}

	if watchlistID != "" {
		wl, err := h.watchlistService.GetWatchlist(watchlistID, subscriptionLevel)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		for _, it := range wl.Items {
			s := strings.ToUpper(strings.TrimSpace(it.Symbol))
			if s == "" {
				continue
			}
			set[s] = struct{}{}
		}
	}

	if portfolioID != "" {
		pf, err := h.portfolioService.GetPortfolio(userID, portfolioID, subscriptionLevel)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		for _, hld := range pf.Holdings {
			s := strings.ToUpper(strings.TrimSpace(hld.Symbol))
			if s == "" {
				continue
			}
			set[s] = struct{}{}
		}
	}

	symbols := make([]string, 0, len(set))
	for s := range set {
		symbols = append(symbols, s)
	}
	sort.Strings(symbols)

	resp := SymbolScopeResolveResponse{Symbols: symbols, Count: len(symbols)}
	if h.cache != nil {
		// Watchlists/portfolios change infrequently; short TTL balances freshness + load reduction.
		_ = h.cache.Set(cacheKey, resp, 60*time.Second)
	}

	c.JSON(http.StatusOK, resp)
}
