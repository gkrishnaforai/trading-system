# Trading System Testbed Guide

## Overview

The Testbed Dashboard is a comprehensive QA testing interface that allows you to test all features of the trading system end-to-end. It's designed for QA engineers and developers to verify system functionality, data availability, and feature completeness.

## Accessing the Testbed

### Option 1: From Main App
1. Open the Streamlit dashboard
2. Click "Open Testbed Dashboard" in the sidebar

### Option 2: Direct Access
```bash
streamlit run streamlit-app/testbed.py
```

## Testbed Sections

### 1. 🏥 System Health
**Purpose**: Check API connectivity and data availability

**Features**:
- API Health Check (Go API, Python API)
- Data Availability Check (for any symbol)
- Real-time status indicators

**Usage**:
1. Click "Check API Health" to verify all APIs are running
2. Enter a symbol (e.g., "AAPL") and click "Check Data Availability"
3. Review which data types are available

**Dependencies**: None (first thing to check)

---

### 2. 📊 Data Sources
**Purpose**: Test data fetching from all sources

**Features**:
- Test individual data types
- View data counts
- Error reporting

**Data Types**:
- `price_historical`: Historical OHLCV data
- `price_current`: Real-time current price
- `fundamentals`: Company fundamentals
- `news`: Stock news articles
- `earnings`: Earnings data
- `industry_peers`: Industry peer information

**Usage**:
1. Enter symbol (e.g., "AAPL")
2. Select data types to test
3. Click "Test Data Sources"
4. Review results (success/failure, data counts)

**Dependencies**: 
- System Health must be green
- Data source must be configured (Yahoo Finance, Finnhub, etc.)

---

### 3. 🧮 Calculations
**Purpose**: Test indicator and calculation services

**Features**:
- Test indicator calculations
- Test signal generation
- Test composite scores
- Test actionable levels

**Calculation Types**:
- `indicators`: Technical indicators (RSI, MACD, SMA, EMA, etc.)
- `signals`: Trading signals (BUY/SELL/HOLD)
- `composite_score`: Pro tier composite scores
- `actionable_levels`: Entry zones, stop-loss, targets

**Usage**:
1. Enter symbol
2. Select calculations to test
3. Click "Test Calculations"
4. Review calculation results

**Dependencies**:
- Historical price data must be available
- Data Sources section should pass first

---

### 4. 🎯 Strategies
**Purpose**: Test strategy signal generation

**Features**:
- Test technical strategy
- Test hybrid LLM strategy
- Test swing trend strategy
- View signal and confidence

**Strategies**:
- `technical`: Technical analysis strategy
- `hybrid_llm`: LLM-enhanced strategy
- `swing_trend`: Swing trading trend strategy

**Usage**:
1. Enter symbol
2. Select strategies to test
3. Click "Test Strategies"
4. Review signals and confidence levels

**Dependencies**:
- Calculations must work (indicators required)
- For LLM strategy: LLM API keys must be configured

---

### 5. 📋 Watchlist CRUD
**Purpose**: Test watchlist create, read, update, delete operations

**Features**:
- Create watchlist
- Read/watchlists
- Update watchlist
- Delete watchlist
- View all watchlist columns

**Usage**:
1. Select tab (Create/Read/Update/Delete)
2. Enter required fields
3. Click action button
4. Review JSON response

**Dependencies**:
- Go API must be healthy
- Database must be accessible

---

### 6. 💼 Portfolio CRUD
**Purpose**: Test portfolio create, read, update, delete operations

**Features**:
- Create portfolio
- Read portfolios
- Update portfolio
- Delete portfolio
- View all portfolio columns

**Usage**:
1. Select tab (Create/Read/Update/Delete)
2. Enter required fields
3. Click action button
4. Review JSON response

**Dependencies**:
- Go API must be healthy
- Database must be accessible

---

### 7. 📈 Swing Trading
**Purpose**: Test swing trading features

**Features**:
- Generate swing trading signals
- View entry/exit levels
- Check risk parameters
- Test multi-timeframe analysis

**Usage**:
1. Enter symbol (e.g., "TQQQ" for leveraged ETF)
2. Enter user ID
3. Click "Generate Swing Signal"
4. Review signal, entry price, stop-loss, take-profit

**Dependencies**:
- Multi-timeframe data must be available
- Swing strategy must be configured
- Risk manager must be working

---

### 8. 📝 Blog Generation
**Purpose**: Test blog generation workflow

**Features**:
- Generate blog topics
- Build context
- Generate blog content
- View audit trail

**Usage**:
1. Enter user ID
2. Optionally enter symbol
3. Select topic type
4. Click "Generate Blog"
5. Review generated content

**Dependencies**:
- User must have portfolios/watchlists
- LLM API keys must be configured
- Blog services must be initialized

---

### 9. 🌐 Market Features
**Purpose**: Test market-wide features

**Features**:
- Market Movers (gainers, losers, most active)
- Sector Performance
- Stock Comparison
- Analyst Ratings
- Market Overview
- Market Trends

**Usage**:
1. Select feature from dropdown
2. Enter required parameters (if any)
3. Click action button
4. Review results

**Dependencies**:
- Live price data must be available
- Market data services must be running

---

### 10. 🔄 End-to-End Workflows
**Purpose**: Test complete workflows from start to finish

**Workflows**:
1. **Complete Stock Analysis**
   - Fetch data → Calculate indicators → Generate signal → Get fundamentals → Get news
   
2. **Portfolio Setup & Analysis**
   - Create portfolio → Add holdings → Calculate metrics → Generate analysis
   
3. **Watchlist to Portfolio**
   - Create watchlist → Add stocks → Move stock to portfolio
   
4. **Swing Trade Execution**
   - Generate signal → Check risk limits → Execute trade → Track performance
   
5. **Blog Generation Workflow**
   - Rank topics → Build context → Generate blog → Save draft

**Usage**:
1. Select workflow
2. Enter required parameters
3. Click "Run Workflow"
4. Review step-by-step results

**Dependencies**: All previous sections should pass

---

## Testing Best Practices

### 1. Start with System Health
Always check system health first to ensure APIs are running.

### 2. Test in Order
Follow the natural dependency order:
1. System Health
2. Data Sources
3. Calculations
4. Strategies
5. CRUD Operations
6. Advanced Features
7. End-to-End Workflows

### 3. Use Real Symbols
Test with real symbols like:
- `AAPL` (Apple) - Good for general testing
- `GOOGL` (Google) - Good for fundamentals
- `NVDA` (NVIDIA) - Good for volatility
- `TQQQ` (Leveraged ETF) - Good for swing trading

### 4. Check Dependencies
Each section shows dependencies. Make sure prerequisites are met before testing.

### 5. Review Error Messages
If a test fails, review the error message carefully. It will indicate:
- Missing data
- Configuration issues
- API errors
- Database errors

### 6. Test Edge Cases
- Empty portfolios
- Symbols with no data
- Invalid user IDs
- Missing API keys

---

## Common Issues and Solutions

### Issue: "API Health Check Failed"
**Solution**: 
- Check if Docker containers are running: `docker-compose ps`
- Check API logs: `docker-compose logs go-api` or `docker-compose logs python-worker`
- Verify API URLs in environment variables

### Issue: "No Data Available"
**Solution**:
- Run data refresh: Use Data Sources section to fetch data
- Check data source configuration (Yahoo Finance, Finnhub)
- Verify database has data: `scripts/inspect_db.sh`

### Issue: "Calculation Failed"
**Solution**:
- Ensure historical price data exists
- Check indicator service logs
- Verify sufficient data points (need at least 200 days for some indicators)

### Issue: "Strategy Failed"
**Solution**:
- Ensure calculations work first
- Check strategy configuration
- For LLM strategy: Verify LLM API keys are set

### Issue: "CRUD Operation Failed"
**Solution**:
- Check Go API health
- Verify database connection
- Check user ID exists
- Review API response for specific error

---

## Integration with CI/CD

The testbed can be used in automated testing:

```python
# Example: Automated test script
from api_client import get_python_api_client

def test_data_source(symbol, data_type):
    client = get_python_api_client()
    response = client.get(f"api/v1/data/{symbol}/{data_type}")
    assert response is not None
    return response

# Run tests
test_data_source("AAPL", "price_historical")
test_data_source("AAPL", "fundamentals")
```

---

## Architecture Compliance

The testbed follows the same architecture principles:

- ✅ **DRY**: Reuses API client functions
- ✅ **SOLID**: Single responsibility per test function
- ✅ **Fail Fast**: Shows errors immediately
- ✅ **No Mocks**: Tests against real APIs and data
- ✅ **Observability**: Logs all test results

---

## Next Steps

1. **Add More Workflows**: Extend end-to-end workflows
2. **Performance Testing**: Add timing metrics
3. **Load Testing**: Test with multiple concurrent requests
4. **Visual Regression**: Compare charts and visualizations
5. **Data Validation**: Validate data quality and completeness

---

## Support

For issues or questions:
1. Check logs: `docker-compose logs`
2. Review API documentation: `docs/API_ENDPOINTS_WITH_ERROR_HANDLING.md`
3. Check test cases: `python-worker/tests/`

