# Stock Screener Implementation

## Overview

Comprehensive stock screener system that allows users to filter stocks based on:

- **Price vs Moving Averages**: Below 50-day or 200-day average
- **Fundamental Quality**: Good fundamentals, growth stocks, exponential growth
- **Technical Indicators**: RSI, MACD, trend filters
- **Custom Combinations**: User-defined screener strategies

## Industry Standards Research

### Good Fundamentals Criteria

Based on financial analyst standards:

1. **P/E Ratio**: < 25 (good), < 15 (excellent value)
2. **PEG Ratio**: < 1.5 (good), < 1.0 (excellent)
3. **Revenue Growth**: > 10% YoY (good), > 25% (high growth)
4. **EPS Growth**: > 15% YoY (good), > 30% (high growth)
5. **Profit Margin**: > 10% (good), > 20% (excellent)
6. **Debt-to-Equity**: < 1.0 (low debt)
7. **Current Ratio**: > 1.5 (good liquidity)

### Growth vs Exponential Growth

**Growth Stock:**

- Revenue Growth: 15-25% YoY
- EPS Growth: 20-30% YoY
- Consistent growth over multiple quarters

**Exponential Growth:**

- Revenue Growth: > 25% YoY
- EPS Growth: > 30% YoY
- Accelerating growth rates
- Often in emerging sectors (AI, biotech, etc.)

## Database Schema

### New Columns in `aggregated_indicators`

```sql
price_below_sma50 BOOLEAN          -- Price < 50-day average
price_below_sma200 BOOLEAN         -- Price < 200-day average
has_good_fundamentals BOOLEAN      -- Meets fundamental criteria
is_growth_stock BOOLEAN            -- Growth stock criteria
is_exponential_growth BOOLEAN      -- Exponential growth criteria
fundamental_score REAL              -- 0-100 fundamental score
```

### Indexes for Fast Screening

```sql
CREATE INDEX idx_screener_below_sma50 ON aggregated_indicators(price_below_sma50, date DESC);
CREATE INDEX idx_screener_below_sma200 ON aggregated_indicators(price_below_sma200, date DESC);
CREATE INDEX idx_screener_good_fundamentals ON aggregated_indicators(has_good_fundamentals, date DESC);
CREATE INDEX idx_screener_composite ON aggregated_indicators(
    has_good_fundamentals,
    price_below_sma50,
    price_below_sma200,
    is_growth_stock,
    date DESC
);
```

## Architecture

### 1. Fundamental Scorer Service

**File:** `python-worker/app/services/fundamental_scorer.py`

**Purpose:** Scores stocks based on fundamental metrics

**Scoring Criteria:**

- P/E Ratio: 20 points max
- PEG Ratio: 15 points max
- Revenue Growth: 20 points max
- EPS Growth: 20 points max
- Profit Margin: 15 points max
- Debt-to-Equity: 10 points max

**Flags Generated:**

- `has_good_fundamentals`: All criteria met + score >= 60
- `is_growth_stock`: Revenue 15-25%, EPS 20-30%
- `is_exponential_growth`: Revenue > 25%, EPS > 30%

### 2. Indicator Service Updates

**File:** `python-worker/app/services/indicator_service.py`

**Changes:**

- Calculates `price_below_sma50` and `price_below_sma200` flags
- Calls `FundamentalScorer` for latest date only (performance optimization)
- Stores all screener flags in `aggregated_indicators` table

### 3. Stock Screener Service

**File:** `python-worker/app/services/stock_screener_service.py`

**Purpose:** Main screening service with SQL-based filtering

**Features:**

- Fast SQL queries using indexed flags
- Multiple filter combinations
- Predefined presets (value below 50MA, growth below 200MA, etc.)
- Returns detailed stock data with discount percentages

### 4. Screener Strategy

**File:** `python-worker/app/strategies/screener_strategy.py`

**Purpose:** Pluggable strategy for user-defined screening

**Usage:**

```python
config = {
    'price_below_sma50': True,
    'has_good_fundamentals': True,
    'min_fundamental_score': 60.0
}
strategy = ScreenerStrategy(config=config)
result = strategy.generate_signal(indicators, context=context)
```

## API Endpoints

### GET `/api/v1/screener/stocks`

Screen stocks based on criteria.

**Query Parameters:**

- `price_below_sma50`: Boolean - Filter for stocks below 50-day average
- `price_below_sma200`: Boolean - Filter for stocks below 200-day average
- `has_good_fundamentals`: Boolean - Filter for good fundamentals
- `is_growth_stock`: Boolean - Filter for growth stocks
- `is_exponential_growth`: Boolean - Filter for exponential growth
- `min_fundamental_score`: Float (0-100) - Minimum fundamental score
- `min_rsi`: Float - Minimum RSI value
- `max_rsi`: Float - Maximum RSI value
- `trend_filter`: String - 'bullish', 'bearish', 'neutral'
- `min_market_cap`: Float - Minimum market cap
- `max_pe_ratio`: Float - Maximum P/E ratio
- `limit`: Integer - Maximum results (default: 100)

**Example:**

```
GET /api/v1/screener/stocks?price_below_sma50=true&has_good_fundamentals=true&limit=50
```

**Response:**

```json
{
  "success": true,
  "count": 25,
  "stocks": [
    {
      "symbol": "AAPL",
      "current_price": 175.5,
      "sma50": 180.0,
      "sma200": 185.0,
      "discount_from_sma50_pct": 2.5,
      "discount_from_sma200_pct": 5.1,
      "fundamental_score": 75.5,
      "has_good_fundamentals": true,
      "is_growth_stock": false,
      "is_exponential_growth": false,
      "price_below_sma50": true,
      "price_below_sma200": true,
      "rsi": 45.2,
      "long_term_trend": "bullish",
      "fundamentals": {
        "pe_ratio": 28.5,
        "revenue_growth_yoy": 12.5,
        "eps_growth_yoy": 18.2,
        "profit_margin": 25.8
      }
    }
  ],
  "criteria": {
    "price_below_sma50": true,
    "has_good_fundamentals": true,
    "limit": 50
  }
}
```

### GET `/api/v1/screener/presets`

Get predefined screener presets.

**Response:**

```json
{
  "success": true,
  "presets": {
    "value_below_50ma": {
      "name": "Value Stocks Below 50-Day Average",
      "description": "Stocks with good fundamentals trading below 50-day moving average",
      "config": {
        "price_below_sma50": true,
        "has_good_fundamentals": true,
        "min_fundamental_score": 60.0
      }
    },
    "growth_below_50ma": {
      "name": "Growth Stocks Below 50-Day Average",
      "description": "Growth stocks trading below 50-day moving average",
      "config": {
        "price_below_sma50": true,
        "is_growth_stock": true
      }
    }
  }
}
```

## Usage Examples

### Example 1: Value Stocks Below 50-Day Average

```python
# Find stocks with good fundamentals trading below 50-day average
results = stock_screener_service.screen_stocks(
    price_below_sma50=True,
    has_good_fundamentals=True,
    min_fundamental_score=60.0,
    limit=50
)
```

### Example 2: Growth Stocks Below 200-Day Average

```python
# Find growth stocks trading below 200-day average
results = stock_screener_service.screen_stocks(
    price_below_sma200=True,
    is_growth_stock=True,
    limit=100
)
```

### Example 3: Oversold with Good Fundamentals

```python
# Find oversold stocks (RSI < 30) with good fundamentals
results = stock_screener_service.screen_stocks(
    max_rsi=30.0,
    has_good_fundamentals=True,
    min_fundamental_score=60.0,
    limit=50
)
```

## Daily Calculation

Screener flags are calculated **automatically** during indicator calculation:

1. **Price Flags**: Calculated for every date

   - `price_below_sma50`: Current price < SMA50
   - `price_below_sma200`: Current price < SMA200

2. **Fundamental Flags**: Calculated for latest date only (performance)
   - `has_good_fundamentals`: Based on fundamental scorer
   - `is_growth_stock`: Based on growth criteria
   - `is_exponential_growth`: Based on exponential growth criteria
   - `fundamental_score`: 0-100 score

## Performance

- **Indexed Queries**: All screener flags are indexed for fast filtering
- **Composite Index**: Common filter combinations use composite index
- **Latest Date Only**: Fundamental scoring only for latest date (avoids performance issues)
- **SQL-Based**: Fast SQL queries instead of Python filtering

## Integration with Strategy System

Users can create custom screener strategies:

```python
from app.strategies import get_strategy

# Create custom screener strategy
config = {
    'price_below_sma50': True,
    'has_good_fundamentals': True,
    'min_fundamental_score': 70.0,
    'trend_filter': 'bullish'
}

strategy = get_strategy('screener', config=config)
result = strategy.generate_signal(indicators, context=context)
```

## Migration

Run migration to add screener flags:

```bash
# Migration file: db/migrations/014_add_screener_flags.sql
# Automatically runs on database initialization
```

## Next Steps

1. **Streamlit UI**: Add screener interface to Streamlit
2. **Save Screener Configs**: Allow users to save custom screener configurations
3. **Alerts**: Set up alerts for stocks matching screener criteria
4. **Backtesting**: Backtest screener strategies
5. **Portfolio Integration**: Add screened stocks directly to portfolio
