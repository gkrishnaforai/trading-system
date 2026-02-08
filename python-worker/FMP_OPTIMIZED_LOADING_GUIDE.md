# Optimized FMP Data Loading Guide

## 🎯 Overview

This guide explains how to use the optimized FMP data loading system that efficiently loads data while minimizing API calls through smart caching and on-demand loading.

## 📊 FMP APIs Used

### Core APIs (Always Used)
- **`/quote?symbol={symbol}`** - Real-time stock quotes
- **`/historical-price-eod/full?symbol={symbol}`** - Historical price data

### On-Demand APIs (Loaded When Needed)
- **`/search-name?query={name}`** - Search for company symbols
- **`/stock-list`** - Get all available stocks
- **`/profile?symbol={symbol}`** - Company profile data
- **`/income-statement?symbol={symbol}`** - Income statement data

## 🚀 Usage Examples

### 1. Load Essential Data (Real-time + Historical)
```python
from app.services.optimized_fmp_loader import optimized_fmp_loader

# Load essential data for symbols
symbols = ["AAPL", "MSFT", "GOOGL"]
results = optimized_fmp_loader.preload_essential_data(symbols)

print(f"Loaded prices for {len(results['real_time_prices'])} symbols")
print(f"Loaded historical data for {len(results['historical_prices'])} symbols")
```

### 2. Get Real-time Price (Always Fresh)
```python
# Get current price (cached for 1 minute)
price = optimized_fmp_loader.get_real_time_price("AAPL")
print(f"AAPL Price: ${price.get('price', 'N/A')}")
```

### 3. Load Company Profile (On-Demand)
```python
# Load profile only when needed (cached for 7 days)
profile = optimized_fmp_loader.get_company_profile("AAPL")
print(f"Company: {profile.get('companyName', 'N/A')}")
print(f"Sector: {profile.get('sector', 'N/A')}")
```

### 4. Search for Symbols
```python
# Search for companies
results = optimized_fmp_loader.search_symbol("apple")
for result in results:
    print(f"{result['name']} ({result['symbol']}) - {result.get('stockExchange', 'N/A')}")
```

### 5. Get Complete Stock List
```python
# Get all available stocks (cached for 24 hours)
all_stocks = optimized_fmp_loader.get_stock_list()
print(f"Total stocks available: {len(all_stocks)}")
```

### 6. Load Financial Data (On-Demand)
```python
# Load income statement (cached for 7 days)
income_stmt = optimized_fmp_loader.get_income_statement("AAPL")
print(f"Revenue: ${income_stmt.get('data', [{}])[0].get('revenue', 'N/A'):,}")

# Load comprehensive financials
financials = optimized_fmp_loader.get_financials("AAPL")
print(f"Market Cap: ${financials.get('marketCap', 'N/A'):,}")
```

## 📋 Command Line Interface

### Load Essential Data
```bash
# Load essential data for default symbols
python load_optimized_fmp_data.py --action essential

# Load for specific symbols
python load_optimized_fmp_data.py --action essential --symbols AAPL MSFT GOOGL
```

### Load Comprehensive Data
```bash
# Load all data including on-demand details
python load_optimized_fmp_data.py --action comprehensive

# Load comprehensive data for specific symbols
python load_optimized_fmp_data.py --action comprehensive --symbols AAPL MSFT
```

### Search and Load
```bash
# Search for symbols and load their data
python load_optimized_fmp_data.py --action search --query "apple"

# Search for multiple queries
python load_optimized_fmp_data.py --action search --query "tesla" --query "microsoft"
```

### Refresh Real-time Prices
```bash
# Refresh prices (clears cache first)
python load_optimized_fmp_data.py --action refresh

# Refresh specific symbols
python load_optimized_fmp_data.py --action refresh --symbols AAPL MSFT
```

### Get Detailed Symbol Data
```bash
# Load all details for a single symbol
python load_optimized_fmp_data.py --action details --symbol AAPL
```

### Cache Management
```bash
# Show cache statistics
python load_optimized_fmp_data.py --cache-stats

# Clear all cache
python load_optimized_fmp_data.py --clear-cache

# Clear specific cache pattern
python load_optimized_fmp_data.py --clear-cache --pattern "price:*"
```

## 🎯 Loading Strategies

### Data Types and Strategies

| Data Type | Cache TTL | Batch Size | On-Demand | Priority |
|-----------|-----------|------------|-----------|----------|
| Real-time Price | 60 seconds | 1 | No | 1 (Highest) |
| Historical Prices | 24 hours | 5 | No | 2 |
| Company Profile | 7 days | 10 | Yes | 3 |
| Financials | 7 days | 5 | Yes | 4 |
| Income Statement | 7 days | 5 | Yes | 5 |
| Stock List | 24 hours | 1 | No | 6 |
| Symbol Search | 1 hour | 1 | Yes | 7 (Lowest) |

### API Call Optimization

#### ✅ What Gets Cached
- **Real-time prices**: 1 minute (fresh enough for trading)
- **Historical data**: 24 hours (doesn't change frequently)
- **Company profiles**: 7 days (rarely changes)
- **Financial statements**: 7 days (quarterly data)
- **Stock list**: 24 hours (updated daily)

#### ✅ On-Demand Loading
- **Company profiles**: Only loaded when explicitly requested
- **Financial data**: Only loaded when needed for analysis
- **Income statements**: Only loaded for specific requests

#### ✅ Bulk Operations
- **Batch processing**: Load multiple symbols efficiently
- **Rate limiting**: Built-in FMP rate limit handling
- **Error handling**: Graceful fallback for failed requests

## 📊 Performance Benefits

### API Call Reduction
- **Real-time data**: Always fresh but cached for 1 minute
- **Historical data**: Loaded once per day, cached for 24 hours
- **Company profiles**: Loaded once per week, cached for 7 days
- **Financial data**: Loaded on-demand, cached for 7 days

### Memory Efficiency
- **Smart caching**: Only cache what's actually used
- **Automatic cleanup**: Cache expires automatically
- **Pattern-based clearing**: Clear specific cache types

### Speed Improvements
- **Cache hits**: Instant data retrieval from cache
- **Batch operations**: Process multiple symbols together
- **Parallel loading**: Load different data types concurrently

## 🛠 Integration Examples

### Streamlit Integration
```python
import streamlit as st
from app.services.optimized_fmp_loader import optimized_fmp_loader

# Real-time price widget
def show_price_widget(symbol):
    price_data = optimized_fmp_loader.get_real_time_price(symbol)
    if price_data:
        st.metric(f"{symbol} Price", f"${price_data['price']:.2f}", 
                 f"{price_data.get('changesPercent', 0):.2f}%")

# Company profile widget
def show_profile_widget(symbol):
    profile = optimized_fmp_loader.get_company_profile(symbol)
    if profile:
        st.write(f"**{profile['companyName']}**")
        st.write(f"Sector: {profile.get('sector', 'N/A')}")
        st.write(f"Industry: {profile.get('industry', 'N/A')}")
```

### API Integration
```python
from fastapi import FastAPI
from app.services.optimized_fmp_loader import optimized_fmp_loader

app = FastAPI()

@app.get("/api/v1/stocks/{symbol}/price")
async def get_stock_price(symbol: str):
    price = optimized_fmp_loader.get_real_time_price(symbol)
    return {"symbol": symbol, "price": price}

@app.get("/api/v1/stocks/{symbol}/profile")
async def get_stock_profile(symbol: str):
    profile = optimized_fmp_loader.get_company_profile(symbol)
    return {"symbol": symbol, "profile": profile}
```

### Background Service Integration
```python
from app.services.optimized_fmp_loader import optimized_fmp_loader

# Background task to refresh prices
def refresh_prices_task():
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
    results = optimized_fmp_loader.refresh_real_time_prices(symbols)
    
    # Process results...
    for symbol, price_data in results["prices"].items():
        # Update database, send notifications, etc.
        pass
```

## 🔧 Configuration

### Environment Variables
```bash
# FMP Configuration
FMP_API_KEY=your_fmp_api_key_here
FMP_ENABLED=true
FMP_BASE_URL=https://financialmodelingprep.com/stable
FMP_TIMEOUT=30
FMP_MAX_RETRIES=3
FMP_RETRY_DELAY=1.0
FMP_RATE_LIMIT_CALLS=60
FMP_RATE_LIMIT_WINDOW=60.0

# Data Source Configuration
PRIMARY_DATA_PROVIDER=fmp
FALLBACK_DATA_PROVIDER=yahoo_finance
DEFAULT_DATA_PROVIDER=fmp
```

### Cache Configuration
```python
# Cache settings (in optimized_fmp_loader.py)
CACHE_TTL_REAL_TIME = 60      # 1 minute
CACHE_TTL_HISTORICAL = 86400  # 24 hours
CACHE_TTL_PROFILE = 604800    # 7 days
CACHE_TTL_FINANCIALS = 604800 # 7 days
```

## 📈 Monitoring and Debugging

### Cache Statistics
```python
from app.services.optimized_fmp_loader import optimized_fmp_loader

# Get cache stats
stats = optimized_fmp_loader.get_cache_stats()
print(f"Cache size: {stats['cache_size']}")
print(f"Cached keys: {stats['cache_keys']}")
```

### Logging
```python
# Enable debug logging
import logging
logging.getLogger("optimized_fmp_loader").setLevel(logging.DEBUG)
```

### Error Handling
```python
# Check for errors in results
results = optimized_fmp_loader.load_all_data_for_symbols(["AAPL", "INVALID"])
if results["errors"]:
    print("Errors occurred:")
    for error in results["errors"]:
        print(f"  - {error}")
```

## 🎯 Best Practices

### 1. Use Essential Loading for Most Cases
```python
# ✅ Good: Load essential data first
results = optimized_fmp_loader.preload_essential_data(symbols)

# ❌ Avoid: Always loading comprehensive data
results = optimized_fmp_loader.load_all_data_for_symbols(symbols, load_on_demand=True)
```

### 2. Load Details On-Demand
```python
# ✅ Good: Load profile only when needed
if user_requests_details:
    profile = optimized_fmp_loader.get_company_profile(symbol)

# ❌ Avoid: Loading all profiles upfront
for symbol in symbols:
    profile = optimized_fmp_loader.get_company_profile(symbol)  # Wasteful
```

### 3. Use Search for Symbol Discovery
```python
# ✅ Good: Search for symbols first
search_results = optimized_fmp_loader.search_symbol("apple")
symbols = [r["symbol"] for r in search_results[:5]]

# ❌ Avoid: Hardcoding symbol lists
symbols = ["AAPL", "AAPL1", "AAPL2"]  # Might be invalid
```

### 4. Monitor Cache Performance
```python
# ✅ Good: Check cache stats regularly
stats = optimized_fmp_loader.get_cache_stats()
if stats["cache_size"] > 1000:
    optimized_fmp_loader.clear_cache()  # Prevent memory bloat
```

### 5. Handle Rate Limits Gracefully
```python
# ✅ Good: Built-in rate limiting handles this automatically
# The loader respects FMP rate limits automatically

# ❌ Avoid: Manual rate limiting
import time
time.sleep(1)  # Not needed - handled by the loader
```

## 🚀 Advanced Usage

### Custom Loading Strategies
```python
# Create custom loading strategy
from app.services.optimized_fmp_loader import LoadStrategy, DataType

custom_strategy = LoadStrategy(
    cache_ttl=3600,     # 1 hour
    batch_size=20,      # Load 20 at once
    on_demand=True,     # Load only when needed
    priority=8          # Lower priority
)
```

### Batch Processing
```python
# Process large symbol lists efficiently
large_symbol_list = get_all_symbols()  # 1000+ symbols

# Process in batches
batch_size = 50
for i in range(0, len(large_symbol_list), batch_size):
    batch = large_symbol_list[i:i+batch_size]
    results = optimized_fmp_loader.preload_essential_data(batch)
    # Process batch results...
```

### Integration with Scheduler
```python
# Use with data refresh scheduler
from app.services.data_refresh_scheduler import scheduler

# Schedule essential data refresh
scheduler.schedule_data_refresh(
    symbols=["AAPL", "MSFT", "GOOGL"],
    data_types=["essential"],
    interval="15min"
)
```

This optimized system ensures you get the best performance while minimizing API costs and providing fresh data when needed!
