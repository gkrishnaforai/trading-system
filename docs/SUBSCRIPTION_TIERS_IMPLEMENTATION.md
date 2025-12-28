# Subscription Tiers Implementation Guide

## ✅ Completed

### 1. Integration Tests with Real Data
- **File**: `python-worker/tests/test_integration_real_data.py`
- **Tests**: Comprehensive integration tests using real market data for AAPL, GOOGL, NVDA
- **Coverage**:
  - Data quality validation
  - RSI calculation accuracy (Wilder's smoothing)
  - MACD calculation accuracy
  - Moving averages accuracy
  - ATR calculation accuracy
  - Bollinger Bands accuracy
  - Trend detection
  - Signal generation
  - Strategy execution
  - Pullback zones and stop-loss

### 2. Indicator Calculation Fixes
- **RSI**: Fixed to use Wilder's smoothing method (industry standard)
- **Function Signatures**: Fixed `calculate_pullback_zones` and `calculate_stop_loss` to return proper types

### 3. Pro Tier Services
- **Composite Score Service**: `python-worker/app/services/composite_score_service.py`
  - Calculates unified decision scores (0-100)
  - Trend score, momentum score, confirmation score
  - Human-readable explanations
  
- **Actionable Levels Service**: `python-worker/app/services/actionable_levels_service.py`
  - Entry zones (pullback zones)
  - Stop-loss calculation
  - First target/exit zones
  - Risk level assessment

## 🚧 To Be Implemented

### Basic Tier Features
1. **Simple Stock Overview**
   - Current price
   - Clear signal (BUY/HOLD/SELL)
   - Trend direction (simple text)
   - Confidence meter (Low/Medium/High)
   - 1-sentence reason
   - Simple visuals (Price + 50/200 MA only)

2. **Education-Driven AI**
   - "Why is this a BUY?" explanations
   - Simple, layman-friendly language
   - No advanced jargon

3. **Portfolio (Read-Only)**
   - Track up to 5 stocks
   - Gain/loss
   - Trend status
   - No strategy suggestions

### Pro Tier Features (Partially Done)
1. ✅ **Composite Score** - DONE
2. ✅ **Actionable Levels** - DONE
3. **Alerts System**
   - Trend change alerts
   - EMA crossover alerts
   - Stop-loss hit alerts
   - Database table for alerts
   - Notification service

4. **Advanced Charts**
   - EMA 9/21/50
   - RSI + MACD charts
   - Volume confirmation charts

5. **Portfolio Intelligence**
   - Up to 20 stocks
   - Portfolio risk score
   - Sector concentration warnings

6. **AI Narratives**
   - Auto-generated analysis
   - Technical summary
   - Market sentiment
   - Risk assessment

### Elite Tier Features
1. **Multi-Timeframe Intelligence**
   - Daily + Weekly trend alignment
   - Early trend reversal detection
   - "Trend aging" score

2. **Strategy Engine**
   - Long-term investing
   - Swing trading
   - Covered calls
   - Protective puts
   - Cash-secured puts

3. **Backtesting Engine**
   - Test strategies on past 5-10 years
   - Win rate calculation
   - Max drawdown
   - CAGR calculation

4. **Portfolio Risk Engine**
   - VaR (Value at Risk)
   - Max drawdown projection
   - Correlation matrix
   - Stress testing

5. **AI Agents**
   - "Why did this stock move today?"
   - "What changed overnight?"
   - "What should I do tomorrow?"

6. **Real-Time Alerts**
   - Pre-market signals
   - Intraday momentum shifts
   - News-triggered risk alerts

7. **Personalized Newsletter**
   - Weekly portfolio report
   - Action items
   - Risk warnings
   - Strategy suggestions

8. **API Access**
   - Programmatic signal access
   - Integration with external tools

## 📋 Implementation Steps

### Step 1: Run Integration Tests
```bash
cd python-worker
python -m pytest tests/test_integration_real_data.py -v
```

### Step 2: Integrate Composite Score into Go API
1. Add endpoint: `GET /api/v1/stock/{symbol}/composite-score?subscription_level=pro`
2. Call Python service to calculate composite score
3. Return JSON with scores and explanation

### Step 3: Integrate Actionable Levels into Go API
1. Add endpoint: `GET /api/v1/stock/{symbol}/actionable-levels?subscription_level=pro`
2. Call Python service to calculate levels
3. Return JSON with entry zone, stop-loss, targets

### Step 4: Update Streamlit UI for Basic Tier
1. Simplify stock overview page
2. Show only essential metrics
3. Add education-driven explanations
4. Limit portfolio to 5 stocks

### Step 5: Update Streamlit UI for Pro Tier
1. Show composite score prominently
2. Display actionable levels
3. Add advanced charts
4. Show portfolio intelligence

### Step 6: Implement Alerts System
1. Create `alerts` table in database
2. Create alert service
3. Add alert endpoints
4. Implement notification system

### Step 7: Implement Elite Tier Features
1. Multi-timeframe analysis service
2. Strategy engine with multiple strategies
3. Backtesting engine
4. Portfolio risk engine
5. AI agents for advanced analysis

## 🔧 API Endpoints to Add

### Pro Tier
- `GET /api/v1/stock/{symbol}/composite-score`
- `GET /api/v1/stock/{symbol}/actionable-levels`
- `GET /api/v1/portfolio/{user_id}/{portfolio_id}/risk-score`
- `POST /api/v1/alerts` (create alert)
- `GET /api/v1/alerts/{user_id}` (get user alerts)

### Elite Tier
- `GET /api/v1/stock/{symbol}/multi-timeframe`
- `GET /api/v1/stock/{symbol}/strategies`
- `POST /api/v1/backtest` (run backtest)
- `GET /api/v1/portfolio/{user_id}/{portfolio_id}/risk-analysis`
- `GET /api/v1/ai-agent/why-moved/{symbol}`
- `GET /api/v1/newsletter/{user_id}`

## 📊 Database Schema Updates Needed

### Alerts Table
```sql
CREATE TABLE alerts (
    alert_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    stock_symbol TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    condition TEXT NOT NULL,
    triggered BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    triggered_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
```

### Backtest Results Table
```sql
CREATE TABLE backtest_results (
    backtest_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    stock_symbol TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    win_rate REAL,
    max_drawdown REAL,
    cagr REAL,
    results_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 🧪 Testing

### Run Integration Tests
```bash
cd python-worker
python -m pytest tests/test_integration_real_data.py -v -s
```

### Test Individual Indicators
```bash
python -m pytest tests/test_indicators.py -v
```

### Test with Real Data
The integration tests fetch real data from Yahoo Finance for AAPL, GOOGL, and NVDA, so ensure you have internet connectivity.

## 📝 Notes

1. **RSI Calculation**: Now uses Wilder's smoothing (industry standard) instead of simple moving average
2. **Composite Score**: Weighted average of trend (40%), momentum (35%), and confirmation (25%)
3. **Actionable Levels**: Based on EMA20 pullback zones and ATR-based stop-loss
4. **Subscription Checks**: All endpoints should check `subscription_level` parameter and return appropriate data

## 🎯 Next Steps

1. Run integration tests to verify calculations
2. Integrate composite score into Go API
3. Integrate actionable levels into Go API
4. Update Streamlit UI for Basic tier (simplify)
5. Update Streamlit UI for Pro tier (add composite score, actionable levels)
6. Implement alerts system
7. Implement Elite tier features (multi-timeframe, backtesting, risk engine)

