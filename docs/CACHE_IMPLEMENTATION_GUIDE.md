# Cache Implementation Guide

This document provides comprehensive guidance for LLMs and developers on understanding, implementing, and enhancing the caching system in the trading system.

## Overview

The trading system implements a **Redis-based cache-aside pattern** with **targeted invalidation** and **real-time refresh capabilities** to ensure data consistency while optimizing performance. The system includes both server-side caching (Go API) and client-side caching (Streamlit UI) with market-hours aware refresh strategies.

## Architecture

### Cache Service
- **Location**: `go-api/internal/services/cache_service.go`
- **Backend**: Redis
- **Pattern**: Cache-Aside (Lazy Loading)
- **TTL**: 5 minutes for most operations, 1 minute for real-time data
- **Real-time**: Market-hours aware refresh with 30-second intervals

### Cache Key Patterns

| Entity Type | List Cache Key | Detail Cache Key | Real-time Key | Example |
|-------------|----------------|------------------|---------------|---------|
| Portfolios | `portfolios:{user_id}` | `portfolio:{user_id}:{portfolio_id}` | `portfolio:rt:{user_id}:{portfolio_id}` | `portfolios:user123` |
| Watchlists | `watchlists:{user_id}` | `watchlist:{watchlist_id}` | `watchlist:rt:{watchlist_id}` | `watchlist:watchlist_456` |
| Prices | `prices:{symbol}` | `price:rt:{symbol}` | N/A | `price:rt:AAPL` |

### Real-Time Refresh Infrastructure
- **Market Hours Detection**: US market hours (9:30 AM - 4:00 PM ET)
- **Smart Refresh Intervals**: 30 seconds (market open) vs 5 minutes (closed)
- **Data Freshness Indicators**: Color-coded status (Live/Fresh/Stale/Outdated)
- **Auto-refresh Controls**: User-configurable with market-hours awareness

## Implementation Patterns

### 1. Cache-Aside Pattern (Read Path)

```go
func (s *Service) GetData(key string) (*Response, error) {
    cacheKey := fmt.Sprintf("entity:%s", key)
    var cached Response
    
    // Try cache first
    if err := s.cache.Get(cacheKey, &cached); err == nil {
        return &cached, nil
    }
    
    // Cache miss - fetch from database
    data, err := s.repository.GetByKey(key)
    if err != nil {
        return nil, err
    }
    
    // Populate cache
    _ = s.cache.Set(cacheKey, data, 5*time.Minute)
    return data, nil
}
```

### 2. Real-Time Cache Pattern with Market Hours Awareness

```go
func (s *Service) GetRealTimeData(symbol string) (*PriceData, error) {
    // Check market hours for appropriate cache strategy
    if !isMarketHours() {
        return s.GetCachedData(symbol, 5*time.Minute)
    }
    
    // During market hours, use shorter TTL
    cacheKey := fmt.Sprintf("price:rt:%s", symbol)
    var cached PriceData
    if err := s.cache.Get(cacheKey, &cached); err == nil {
        return &cached, nil
    }
    
    // Fetch fresh data
    data, err := s.dataProvider.GetRealTimePrice(symbol)
    if err != nil {
        return nil, err
    }
    
    // Cache with shorter TTL during market hours
    _ = s.cache.Set(cacheKey, data, 30*time.Second)
    return data, nil
}
```

### 3. Smart Cache Invalidation (Write Path)

```go
func (s *Service) UpdateData(userID string, entityID string, updates map[string]interface{}) error {
    // Perform database operation
    if err := s.repository.Update(entityID, updates); err != nil {
        return err
    }
    
    // Invalidate all relevant caches including real-time
    s.cache.Delete(fmt.Sprintf("entity:%s:%s", userID, entityID))        // Detail cache
    s.cache.Delete(fmt.Sprintf("entities:%s", userID))                    // List cache
    s.cache.Delete(fmt.Sprintf("entity:rt:%s:%s", userID, entityID))      // Real-time cache
    
    // Publish cache invalidation event for real-time updates
    s.eventBus.Publish("cache_invalidation", map[string]interface{}{
        "entity_type": "entity",
        "user_id": userID,
        "entity_id": entityID,
        "timestamp": time.Now(),
    })
    
    return nil
}
```

### 4. Client-Side Cache Management (Streamlit)

```python
@st.cache_data(ttl=300)  # 5 minutes for general data
def get_watchlist_data(user_id: str):
    """Get watchlist with standard caching"""
    return _go_api_get(f"/api/v1/watchlists/{user_id}")

@st.cache_data(ttl=60)   # 1 minute for real-time data
def get_real_time_prices(symbols: List[str]):
    """Get real-time prices with shorter cache"""
    return _go_api_post("/api/v1/prices/real-time", {"symbols": symbols})

def smart_refresh():
    """Market-hours aware refresh logic"""
    if is_market_hours():
        # Clear cache more frequently during market hours
        st.cache_data.clear()
        st.rerun()
```

## Current Cache Implementation

### Portfolio Service Cache Keys

| Operation | Standard Cache Keys | Real-time Cache Keys | Streamlit Actions |
|-----------|-------------------|---------------------|-------------------|
| CreatePortfolio | `portfolio:{user}:{id}`, `portfolios:{user}` | `portfolio:rt:{user}:{id}` | Clear cache, `st.rerun()` |
| UpdatePortfolio | `portfolio:{user}:{id}`, `portfolios:{user}` | `portfolio:rt:{user}:{id}` | Clear cache, `st.rerun()` |
| DeletePortfolio | `portfolio:{user}:{id}`, `portfolios:{user}` | `portfolio:rt:{user}:{id}` | Clear cache, `st.rerun()` |
| CreateHolding | `portfolio:{user}:{id}`, `portfolios:{user}` | `portfolio:rt:{user}:{id}` | Clear cache, `st.rerun()` |
| UpdateHolding | `portfolio:{user}:{id}`, `portfolios:{user}` | `portfolio:rt:{user}:{id}` | Clear cache, `st.rerun()` |
| DeleteHolding | `portfolio:{user}:{id}`, `portfolios:{user}` | `portfolio:rt:{user}:{id}` | Clear cache, `st.rerun()` |

### Watchlist Service Cache Keys

| Operation | Standard Cache Keys | Real-time Cache Keys | Streamlit Actions |
|-----------|-------------------|---------------------|-------------------|
| CreateWatchlist | `watchlists:{user}` | N/A | Clear cache, `st.rerun()` |
| UpdateWatchlist | `watchlists:{user}`, `watchlist:{id}` | `watchlist:rt:{id}` | Clear cache, `st.rerun()` |
| DeleteWatchlist | `watchlists:{user}`, `watchlist:{id}` | `watchlist:rt:{id}` | Clear cache, `st.rerun()` |
| AddItem | `watchlists:{user}`, `watchlist:{id}` | `watchlist:rt:{id}` | Clear cache, `st.rerun()` |
| UpdateItem | `watchlists:{user}`, `watchlist:{id}` | `watchlist:rt:{id}` | Clear cache, `st.rerun()` |
| RemoveItem | `watchlists:{user}`, `watchlist:{id}` | `watchlist:rt:{id}` | Clear cache, `st.rerun()` |
| MoveToPortfolio | `watchlists:{user}`, `watchlist:{id}`, `portfolio:{user}:{id}`, `portfolios:{user}` | `watchlist:rt:{id}`, `portfolio:rt:{user}:{id}` | Clear cache, `st.rerun()` |

### Real-Time Price Cache Keys

| Operation | Cache Keys | TTL | Refresh Strategy |
|-----------|------------|-----|------------------|
| GetRealTimePrice | `price:rt:{symbol}` | 30 seconds (market hours) | Auto-refresh every 30s |
| GetHistoricalPrice | `price:{symbol}:{date}` | 24 hours | Manual refresh |
| GetBatchPrices | `prices:rt:{batch_hash}` | 30 seconds | Auto-refresh during market hours |

## Best Practices

### 1. Cache Key Naming Convention
- Use plural form for list caches: `portfolios:{user_id}`
- Use singular form for detail caches: `portfolio:{user_id}:{portfolio_id}`
- Include user context in keys for proper isolation
- Use consistent separators (`:`)

### 2. Cache Invalidation Strategy
- **Always invalidate both detail and list caches** on mutations
- **Use targeted invalidation** - only delete affected keys
- **Handle cross-entity operations** (e.g., MoveToPortfolio affects both watchlist and portfolio caches)
- **Get user context** when needed for proper invalidation

### 3. Error Handling
- Cache operations should **never fail the main operation**
- Use graceful degradation: continue if cache fails
- Log cache errors for monitoring

```go
// Good: Graceful cache handling
portfolio, err := s.portfolioRepo.GetByID(portfolioID)
if err == nil {
    s.cache.Delete(fmt.Sprintf("portfolio:%s:%s", portfolio.UserID, portfolioID))
    s.cache.Delete(fmt.Sprintf("portfolios:%s", portfolio.UserID))
}
// Continue even if cache operations fail
```

### 4. Performance Considerations
- **Cache TTL**: 5 minutes balances freshness and performance
- **Cache size**: Monitor Redis memory usage
- **Batch operations**: Consider cache warming for predictable access patterns

## Adding New Features with Caching

### Step 1: Define Cache Keys
Follow the naming convention for your new entity:

```go
// Example for new "Signals" entity
const (
    SignalsListCacheKey   = "signals:%s"           // signals:{user_id}
    SignalDetailCacheKey  = "signal:%s:%s"         // signal:{user_id}:{signal_id}
)
```

### Step 2: Implement Cache-Aside for Reads
```go
func (s *SignalService) GetSignals(userID string) (*SignalsResponse, error) {
    cacheKey := fmt.Sprintf(SignalsListCacheKey, userID)
    var cached SignalsResponse
    
    if err := s.cache.Get(cacheKey, &cached); err == nil {
        return &cached, nil
    }
    
    signals, err := s.signalRepo.GetByUserID(userID)
    if err != nil {
        return nil, fmt.Errorf("failed to get signals: %w", err)
    }
    
    resp := &SignalsResponse{UserID: userID, Signals: signals}
    _ = s.cache.Set(cacheKey, resp, 5*time.Minute)
    return resp, nil
}
```

### Step 3: Implement Cache Invalidation for Writes
```go
func (s *SignalService) CreateSignal(userID string, signal *models.Signal) error {
    if err := s.signalRepo.Create(signal); err != nil {
        return err
    }
    
    // Invalidate caches
    s.cache.Delete(fmt.Sprintf(SignalDetailCacheKey, userID, signal.SignalID))
    s.cache.Delete(fmt.Sprintf(SignalsListCacheKey, userID))
    
    return nil
}
```

### Step 4: Add Repository Methods for Context
If you need user context for invalidation:

```go
// Add to repository
func (r *SignalRepository) GetSignalByID(signalID string) (*models.Signal, error) {
    query := `SELECT signal_id, user_id, ... FROM signals WHERE signal_id = ?`
    // Implementation
}
```

## Enhancing Existing Functionality

### Adding New Cache Keys
When adding new cache keys to existing services:

1. **Update invalidation methods** to include new keys
2. **Maintain consistency** with existing patterns
3. **Consider cross-service impacts**

### Example: Adding Portfolio Analytics Cache
```go
// New cache key
const PortfolioAnalyticsCacheKey = "analytics:portfolio:%s:%s"  // analytics:portfolio:{user}:{portfolio}

// Update existing operations to invalidate analytics
func (s *PortfolioService) CreateHolding(portfolioID string, holding *models.Holding) error {
    // ... existing logic ...
    
    // Invalidate analytics cache
    portfolio, err := s.portfolioRepo.GetByID(portfolioID)
    if err == nil {
        s.cache.Delete(fmt.Sprintf(PortfolioAnalyticsCacheKey, portfolio.UserID, portfolioID))
    }
    
    return nil
}
```

## Cache Monitoring and Debugging

### 1. Monitoring Metrics
- Cache hit/miss ratios
- Redis memory usage
- Cache operation latency
- Invalidation frequency

### 2. Debugging Tools
```bash
# Redis CLI commands for debugging
redis-cli KEYS "portfolios:*"
redis-cli GET "portfolios:user123"
redis-cli TTL "portfolios:user123"
```

### 3. Logging
Add structured logging for cache operations:

```go
s.logger.Info("cache_invalidated", 
    "operation", "create_portfolio",
    "keys", []string{detailKey, listKey},
    "user_id", userID,
)
```

## Common Pitfalls and Solutions

### 1. Cache Stampede
**Problem**: Multiple requests miss cache simultaneously
**Solution**: Use cache warming or request coalescing for high-traffic keys

### 2. Stale Data
**Problem**: Cache not invalidated properly
**Solution**: Double-check invalidation logic, especially for cross-entity operations

### 3. Memory Bloat
**Problem**: Cache growing too large
**Solution**: Monitor TTL usage, implement cache size limits

### 4. Inconsistent Keys
**Problem**: Different key formats across services
**Solution**: Use constants and helper functions for key generation

```go
// Helper function for consistent key generation
func PortfolioDetailKey(userID, portfolioID string) string {
    return fmt.Sprintf("portfolio:%s:%s", userID, portfolioID)
}
```

## Testing Cache Behavior

### Unit Tests
```go
func TestPortfolioCacheInvalidation(t *testing.T) {
    // Setup mock cache
    mockCache := &MockCacheService{}
    service := NewPortfolioService(repo, mockCache)
    
    // Test create operation
    _, err := service.CreatePortfolio("user123", "Test Portfolio", nil)
    assert.NoError(t, err)
    
    // Verify cache invalidation
    mockCache.AssertCalled(t, "Delete", "portfolio:user123:portfolio_123")
    mockCache.AssertCalled(t, "Delete", "portfolios:user123")
}
```

### Integration Tests
- Test cache behavior with real Redis
- Verify TTL settings
- Test concurrent access scenarios

## Next Phase Implementation Steps for LLMs

### 🚀 Phase 2: Real-Time Infrastructure (Week 2-6)

#### 2.1 WebSocket Implementation for Real-Time Prices

**Step 1: Add WebSocket Support to Go API**
```go
// File: go-api/internal/websocket/price_server.go
type PriceServer struct {
    hub      *Hub
    cache    *CacheService
    upgrader websocket.Upgrader
}

func (ps *PriceServer) HandlePriceUpdates(c *gin.Context) {
    conn, err := ps.upgrader.Upgrade(c.Writer, c.Request, nil)
    if err != nil {
        log.Error("WebSocket upgrade failed:", err)
        return
    }
    
    client := &Client{
        conn: conn,
        send: make(chan []byte, 256),
        hub:  ps.hub,
    }
    
    ps.hub.register <- client
    go client.writePump()
    go client.readPump()
}
```

**Step 2: Implement Real-Time Price Broadcasting**
```go
// File: go-api/internal/services/real_time_service.go
type RealTimeService struct {
    priceFeed     PriceFeed
    websocketHub  *Hub
    cache         *CacheService
    subscribers   map[string]map[string]bool // symbol -> clientIDs
}

func (rts *RealTimeService) StartPriceStream() {
    ticker := time.NewTicker(1 * time.Second)
    defer ticker.Stop()
    
    for {
        select {
        case <-ticker.C:
            if isMarketHours() {
                rts.updatePricesAndBroadcast()
            }
        }
    }
}

func (rts *RealTimeService) updatePricesAndBroadcast() {
    symbols := rts.getSubscribedSymbols()
    prices, err := rts.priceFeed.GetRealTimePrices(symbols)
    if err != nil {
        return
    }
    
    for symbol, price := range prices {
        // Update cache
        cacheKey := fmt.Sprintf("price:rt:%s", symbol)
        rts.cache.Set(cacheKey, price, 30*time.Second)
        
        // Broadcast to subscribers
        rts.broadcastPriceUpdate(symbol, price)
    }
}
```

**Step 3: Add Streamlit WebSocket Client**
```python
# File: python-worker/streamlit_enhanced_watchlist_portfolio.py
import websocket
import json
import threading

class RealTimePriceClient:
    def __init__(self, go_api_url: str):
        self.ws_url = go_api_url.replace('http', 'ws') + '/ws/prices'
        self.prices = {}
        self.callbacks = []
        self.ws = None
        self.connected = False
    
    def connect(self):
        def on_message(ws, message):
            data = json.loads(message)
            symbol = data['symbol']
            price = data['price']
            
            self.prices[symbol] = price
            for callback in self.callbacks:
                callback(symbol, price)
        
        def on_open(ws):
            self.connected = True
            print("WebSocket connected for real-time prices")
        
        def on_error(ws, error):
            print(f"WebSocket error: {error}")
        
        def on_close(ws, close_status_code, close_msg):
            self.connected = False
            print("WebSocket disconnected")
        
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_message=on_message,
            on_open=on_open,
            on_error=on_error,
            on_close=on_close
        )
        
        # Start WebSocket in separate thread
        wst = threading.Thread(target=self.ws.run_forever)
        wst.daemon = True
        wst.start()
    
    def subscribe(self, symbols: List[str]):
        if self.connected:
            self.ws.send(json.dumps({
                "action": "subscribe",
                "symbols": symbols
            }))
    
    def add_price_callback(self, callback):
        self.callbacks.append(callback)

# Initialize in Streamlit app
if 'price_client' not in st.session_state:
    st.session_state.price_client = RealTimePriceClient(_go_api_base_url())
    st.session_state.price_client.connect()
```

#### 2.2 Server-Sent Events (SSE) Alternative

**Step 1: Add SSE Endpoint to Go API**
```go
// File: go-api/internal/handlers/sse_handler.go
func (h *SSEHandler) HandlePriceUpdates(c *gin.Context) {
    // Set SSE headers
    c.Header("Content-Type", "text/event-stream")
    c.Header("Cache-Control", "no-cache")
    c.Header("Connection", "keep-alive")
    c.Header("Access-Control-Allow-Origin", "*")
    
    // Create client channel
    clientChan := make(chan PriceUpdate, 10)
    h.priceService.AddClient(clientChan)
    defer h.priceService.RemoveClient(clientChan)
    
    // Stream updates
    for {
        select {
        case priceUpdate := <-clientChan:
            event := fmt.Sprintf("data: %s\n\n", priceUpdate.ToJSON())
            _, err := c.Writer.Write([]byte(event))
            if err != nil {
                return
            }
            c.Writer.Flush()
        case <-c.Request.Context().Done():
            return
        }
    }
}
```

#### 2.3 Event-Driven Cache Invalidation

**Step 1: Add Redis Pub/Sub for Cache Events**
```go
// File: go-api/internal/events/cache_invalidator.go
type CacheInvalidator struct {
    redis    *redis.Client
    pubsub   *redis.PubSub
    handlers map[string]func(event CacheEvent)
}

func (ci *CacheInvalidator) StartEventListener() {
    ci.pubsub = ci.redis.Subscribe("cache_invalidation")
    channel := ci.pubsub.Channel()
    
    go func() {
        for msg := range channel {
            var event CacheEvent
            json.Unmarshal([]byte(msg.Payload), &event)
            
            if handler, exists := ci.handlers[event.Type]; exists {
                handler(event)
            }
        }
    }()
}

func (ci *CacheInvalidator) InvalidatePortfolio(event PortfolioUpdateEvent) {
    // Publish invalidation event
    ci.redis.Publish("cache_invalidation", map[string]interface{}{
        "type": "portfolio_update",
        "user_id": event.UserID,
        "portfolio_id": event.PortfolioID,
        "timestamp": time.Now().Unix(),
    })
    
    // Invalidate local cache
    ci.invalidatePortfolioCache(event.UserID, event.PortfolioID)
}
```

### 🚀 Phase 3: Advanced Real-Time Features (Week 7-12)

#### 3.1 Optimistic UI Updates

**Step 1: Implement Optimistic Updates in Streamlit**
```python
# File: python-worker/streamlit_enhanced_watchlist_portfolio.py
def add_symbol_optimistic(watchlist_id: str, symbol: str):
    """Add symbol with optimistic UI update"""
    
    # 1. Create optimistic item
    optimistic_item = {
        "symbol": symbol,
        "company_name": "Loading...",
        "current_price": 0.0,
        "daily_change": 0.0,
        "daily_change_pct": 0.0,
        "volume": 0,
        "status": "pending",
        "op_id": f"opt_{int(time.time())}"
    }
    
    # 2. Update UI immediately
    if 'watchlist_items' not in st.session_state:
        st.session_state.watchlist_items = []
    st.session_state.watchlist_items.append(optimistic_item)
    st.rerun()
    
    # 3. Make API call
    try:
        result = _go_api_post(f"/api/v1/watchlists/{watchlist_id}/items", {
            "stock_symbol": symbol
        })
        
        # 4. Replace optimistic item with real data
        for i, item in enumerate(st.session_state.watchlist_items):
            if item.get("op_id") == optimistic_item["op_id"]:
                st.session_state.watchlist_items[i] = result
                break
        
        st.rerun()
        st.success(f"✅ Added {symbol} to watchlist")
        
    except Exception as e:
        # 5. Rollback on error
        st.session_state.watchlist_items = [
            item for item in st.session_state.watchlist_items 
            if item.get("op_id") != optimistic_item["op_id"]
        ]
        st.rerun()
        st.error(f"❌ Failed to add {symbol}: {e}")
```

#### 3.2 Conflict Resolution with Versioning

**Step 1: Add Versioning to Data Models**
```go
// File: go-api/internal/models/portfolio.go
type Holding struct {
    HoldingID     string    `json:"holding_id" db:"holding_id"`
    PortfolioID   string    `json:"portfolio_id" db:"portfolio_id"`
    StockSymbol   string    `json:"stock_symbol" db:"stock_symbol"`
    Quantity      float64   `json:"quantity" db:"quantity"`
    AvgEntryPrice float64   `json:"avg_entry_price" db:"avg_entry_price"`
    Version       int64     `json:"version" db:"version"`
    UpdatedAt     time.Time `json:"updated_at" db:"updated_at"`
    // ... other fields
}
```

**Step 2: Implement Optimistic Locking**
```go
// File: go-api/internal/services/portfolio_service.go
func (s *PortfolioService) UpdateHoldingWithVersion(
    holdingID string, 
    updates map[string]interface{}, 
    expectedVersion int64,
) (*models.Holding, error) {
    // Get current holding
    current, err := s.portfolioRepo.GetHoldingByID(holdingID)
    if err != nil {
        return nil, err
    }
    
    // Check version
    if current.Version != expectedVersion {
        return nil, &ConflictError{
            Current: current,
            Expected: expectedVersion,
            Message: "Holding was modified by another process",
        }
    }
    
    // Update with new version
    updates["version"] = current.Version + 1
    updates["updated_at"] = time.Now()
    
    err = s.portfolioRepo.UpdateHolding(holdingID, updates)
    if err != nil {
        return nil, err
    }
    
    // Get updated holding
    return s.portfolioRepo.GetHoldingByID(holdingID)
}
```

#### 3.3 Smart Refresh Strategy

**Step 1: Context-Aware Refresh Intervals**
```go
// File: go-api/internal/services/smart_refresh_service.go
type SmartRefreshService struct {
    marketHours   *MarketHoursService
    volatilityAPI *VolatilityAPI
    calendarAPI   *EarningsCalendarAPI
}

func (srs *SmartRefreshService) GetRefreshInterval(symbol string, dataType DataType) time.Duration {
    // Base intervals
    baseIntervals := map[DataType]time.Duration{
        DataType.PRICE_CURRENT:   30 * time.Second,
        DataType.PRICE_INTRADAY:  15 * time.Minute,
        DataType.NEWS:           5 * time.Minute,
        DataType.INDICATORS:     1 * time.Hour,
    }
    
    baseInterval := baseIntervals[dataType]
    
    // Adjust for market hours
    if !srs.marketHours.IsMarketOpen() {
        return baseInterval * 10  // Slower when market closed
    }
    
    // Adjust for volatility
    volatility, err := srs.volatilityAPI.GetVolatility(symbol)
    if err == nil && volatility > 0.3 {  // High volatility
        baseInterval = baseInterval / 2
    }
    
    // Adjust for earnings announcements
    if srs.calendarAPI.HasEarningsToday(symbol) {
        baseInterval = baseInterval / 4  // Much faster on earnings day
    }
    
    return baseInterval
}
```

### 🚀 Phase 4: Production Readiness (Week 13-16)

#### 4.1 Performance Optimization

**Step 1: Implement Cache Warming**
```go
// File: go-api/internal/services/cache_warming_service.go
type CacheWarmingService struct {
    portfolioRepo *repositories.PortfolioRepository
    watchlistRepo *repositories.WatchlistRepository
    cache         *CacheService
    scheduler     *cron.Cron
}

func (cws *CacheWarmingService) StartCacheWarming() {
    // Warm popular watchlists at market open
    cws.scheduler.AddFunc("0 30 9 * * 1-5", func() { // 9:30 AM weekdays
        cws.warmPopularWatchlists()
    })
    
    // Warm portfolio data periodically
    cws.scheduler.AddFunc("0 */15 9-16 * * 1-5", func() { // Every 15 min during market hours
        cws.warmActivePortfolios()
    })
    
    cws.scheduler.Start()
}

func (cws *CacheWarmingService) warmPopularWatchlists() {
    popularWatchlists, err := cws.watchlistRepo.GetPopularWatchlists(100)
    if err != nil {
        return
    }
    
    for _, watchlist := range popularWatchlists {
        // Pre-load watchlist data
        cacheKey := fmt.Sprintf("watchlist:%s", watchlist.WatchlistID)
        cws.cache.Set(cacheKey, watchlist, 5*time.Minute)
    }
}
```

#### 4.2 Monitoring and Observability

**Step 1: Add Cache Metrics**
```go
// File: go-api/internal/metrics/cache_metrics.go
type CacheMetrics struct {
    hitCount     prometheus.Counter
    missCount    prometheus.Counter
    latency      prometheus.Histogram
    errorCount   prometheus.Counter
}

func NewCacheMetrics() *CacheMetrics {
    return &CacheMetrics{
        hitCount: prometheus.NewCounter(prometheus.CounterOpts{
            Name: "cache_hits_total",
            Help: "Total number of cache hits",
        }),
        missCount: prometheus.NewCounter(prometheus.CounterOpts{
            Name: "cache_misses_total", 
            Help: "Total number of cache misses",
        }),
        latency: prometheus.NewHistogram(prometheus.HistogramOpts{
            Name: "cache_operation_duration_seconds",
            Help: "Cache operation latency",
        }),
        errorCount: prometheus.NewCounter(prometheus.CounterOpts{
            Name: "cache_errors_total",
            Help: "Total number of cache errors",
        }),
    }
}
```

#### 4.3 Testing Infrastructure

**Step 1: Real-Time Testing Framework**
```go
// File: go-api/tests/realtime_test.go
func TestRealTimePriceUpdates(t *testing.T) {
    // Set up test WebSocket server
    testServer := setupTestWebSocketServer()
    defer testServer.Close()
    
    // Connect test client
    client := NewTestWebSocketClient(testServer.URL)
    client.Connect()
    
    // Subscribe to symbols
    client.Subscribe([]string{"AAPL", "GOOGL"})
    
    // Simulate price updates
    priceService := testServer.PriceService()
    priceService.UpdatePrice("AAPL", 150.25)
    
    // Verify client receives update
    update := client.WaitForUpdate(5 * time.Second)
    assert.Equal(t, "AAPL", update.Symbol)
    assert.Equal(t, 150.25, update.Price)
}
```

### 📋 Implementation Checklist for LLMs

#### Phase 2 Checklist
- [ ] WebSocket server implementation in Go API
- [ ] Real-time price broadcasting service
- [ ] Streamlit WebSocket client integration
- [ ] Redis pub/sub for cache invalidation events
- [ ] Market-hours aware refresh logic
- [ ] Data freshness indicators in UI

#### Phase 3 Checklist
- [ ] Optimistic UI updates for all CRUD operations
- [ ] Versioning and conflict resolution for concurrent updates
- [ ] Smart refresh intervals based on volatility and earnings
- [ ] Error handling and rollback mechanisms
- [ ] User feedback for optimistic updates

#### Phase 4 Checklist
- [ ] Cache warming for popular data
- [ ] Comprehensive metrics and monitoring
- [ ] Load testing for WebSocket connections
- [ ] Performance optimization for high-frequency updates
- [ ] Documentation and runbooks for operations

### 🔧 Key Implementation Files to Create/Modify

```
go-api/
├── internal/websocket/
│   ├── price_server.go          # WebSocket server
│   ├── hub.go                   # Connection management
│   └── client.go                # Client handling
├── internal/services/
│   ├── real_time_service.go     # Real-time price service
│   ├── smart_refresh_service.go # Context-aware refresh
│   └── cache_warming_service.go # Cache warming
├── internal/events/
│   └── cache_invalidator.go     # Event-driven invalidation
├── internal/handlers/
│   └── sse_handler.go           # Server-sent events
└── tests/
    └── realtime_test.go         # Real-time testing

python-worker/
├── streamlit_enhanced_watchlist_portfolio.py
│   ├── RealTimePriceClient      # WebSocket client
│   ├── optimistic_updates()     # Optimistic UI logic
│   └── smart_refresh()          # Enhanced refresh
└── tests/
    └── test_realtime_ui.py      # UI testing
```

This comprehensive roadmap provides LLMs with detailed implementation steps, code examples, and checklists to build a truly real-time trading system that meets industry standards.
