# Massive.com API Data Coverage

## Overview

This document maps Massive.com REST API endpoints to our database tables and identifies what data we're collecting for trading decisions, alerts, and blog generation.

## API Endpoints Coverage

### ✅ Fully Covered

#### 1. Income Statements
- **API**: `/stocks/financials/v1/income-statements`
- **Table**: `income_statements`
- **Use Cases**: 
  - Earnings analysis for BUY/SELL/HOLD decisions
  - Revenue growth trends for blog content
  - Profit margin analysis for alerts
- **Key Fields**: revenues, net_income, eps, operating_income, gross_profit

#### 2. Balance Sheets
- **API**: `/stocks/financials/v1/balance-sheets`
- **Table**: `balance_sheets`
- **Use Cases**:
  - Financial health assessment
  - Debt analysis for risk alerts
  - Liquidity ratios for trading decisions
- **Key Fields**: total_assets, total_liabilities, total_equity, cash_and_equivalents, debt_current

#### 3. Cash Flow Statements
- **API**: `/stocks/financials/v1/cash-flow-statements`
- **Table**: `cash_flow_statements`
- **Use Cases**:
  - Operating cash flow for quality assessment
  - Free cash flow for valuation
  - Cash burn alerts for risky stocks
- **Key Fields**: operating_cash_flow, free_cash_flow, capital_expenditures

#### 4. Financial Ratios
- **API**: `/stocks/fundamentals/ratios`
- **Table**: `financial_ratios`
- **Use Cases**:
  - Pre-calculated ratios for fast screening
  - Valuation metrics (P/E, P/B, P/S, PEG)
  - Profitability metrics (ROE, ROA, ROIC)
  - Efficiency metrics (asset turnover, inventory turnover)
- **Key Fields**: All valuation, profitability, efficiency, leverage, liquidity ratios

#### 5. Short Interest
- **API**: `/stocks/fundamentals/short-interest`
- **Table**: `short_interest`
- **Use Cases**:
  - Short squeeze alerts
  - Contrarian signals
  - High short interest warnings
- **Key Fields**: short_interest, days_to_cover, average_volume

#### 6. Short Volume
- **API**: `/stocks/fundamentals/short-volume`
- **Table**: `short_volume`
- **Use Cases**:
  - Daily short volume tracking
  - Short volume ratio for sentiment
- **Key Fields**: short_volume, total_volume, short_volume_ratio

#### 7. Float Data
- **API**: `/stocks/fundamentals/float`
- **Table**: `share_float`
- **Use Cases**:
  - Float analysis for volatility assessment
  - Share structure for blog explanations
- **Key Fields**: shares_outstanding, float_shares, float_percentage

#### 8. Risk Factors
- **API**: `/stocks/filings/risk-factors`
- **Table**: `risk_factors`
- **Use Cases**:
  - Risk alerts for portfolio
  - Risk disclosure in blogs
  - Risk factor changes tracking
- **Key Fields**: risk_factor_text, risk_category, severity

#### 9. Risk Categories
- **API**: `/stocks/filings/risk-categories`
- **Table**: `risk_categories`
- **Use Cases**:
  - Categorized risk analysis
  - Risk filtering for screening
- **Key Fields**: category, category_count

#### 10. News
- **API**: `/stocks/news`
- **Table**: `stock_news` (existing)
- **Use Cases**:
  - News sentiment analysis
  - News-based alerts
  - Blog content generation
- **Key Fields**: title, publisher, published_date, sentiment_score

### ✅ Technical Indicators (Covered in aggregated_indicators)

#### 11. Simple Moving Average (SMA)
- **API**: `/stocks/technical-indicators/simple-moving-average`
- **Table**: `aggregated_indicators`
- **Fields**: sma50, sma100, sma200
- **Status**: ✅ Covered

#### 12. Exponential Moving Average (EMA)
- **API**: `/stocks/technical-indicators/exponential-moving-average`
- **Table**: `aggregated_indicators`
- **Fields**: ema9, ema12, ema20, ema21, ema26, ema50
- **Status**: ✅ Covered

#### 13. MACD (Moving Average Convergence Divergence)
- **API**: `/stocks/technical-indicators/moving-average-convergence-divergence`
- **Table**: `aggregated_indicators`
- **Fields**: macd, macd_signal, macd_histogram
- **Status**: ✅ Covered

#### 14. RSI (Relative Strength Index)
- **API**: `/stocks/technical-indicators/relative-strength-index`
- **Table**: `aggregated_indicators`
- **Fields**: rsi, rsi_zone
- **Status**: ✅ Covered

## Enhanced Fundamentals Table (Denormalized)

The `enhanced_fundamentals` table provides a denormalized view combining key metrics from all financial statements for fast queries. This is optimized for:

1. **Fast Screening**: All key metrics in one table
2. **Alert Generation**: Quick access to ratios and metrics
3. **Blog Generation**: Comprehensive data in one query
4. **Trading Decisions**: >90% confidence with all data points

### Key Metrics Included:
- Valuation: P/E, P/B, P/S, PEG, EV/EBITDA
- Profitability: Margins, ROE, ROA, ROIC
- Growth: Revenue, Earnings, EPS growth
- Financial Health: Debt ratios, Liquidity ratios
- Cash Flow: Operating CF, Free CF
- Market Metrics: Float, Short interest, Days to cover

## Data Usage by Feature

### Trading Decisions (>90% Confidence)
**Required Data:**
- ✅ Income statements (revenue, earnings trends)
- ✅ Balance sheets (financial health)
- ✅ Cash flow (operating quality)
- ✅ Financial ratios (valuation, profitability)
- ✅ Technical indicators (price action)
- ✅ Short interest (sentiment)
- ✅ Risk factors (risk assessment)

### Alert Generation
**Required Data:**
- ✅ Earnings surprises (income statements)
- ✅ High short interest (short_interest table)
- ✅ Risk factor changes (risk_factors table)
- ✅ Financial health deterioration (balance_sheets, ratios)
- ✅ Cash flow issues (cash_flow_statements)

### Blog Generation
**Required Data:**
- ✅ All financial statements (comprehensive analysis)
- ✅ Growth trends (income statements over time)
- ✅ Valuation analysis (ratios)
- ✅ Risk factors (risk disclosure)
- ✅ News (context and sentiment)
- ✅ Technical analysis (indicators)

### Swing Trading Decisions
**Required Data:**
- ✅ Technical indicators (trend, momentum)
- ✅ Financial health (balance sheets, ratios)
- ✅ Short interest (squeeze potential)
- ✅ Earnings trends (income statements)
- ✅ Risk factors (risk management)

## Database Schema Summary

### Financial Statements (Normalized)
1. `income_statements` - Quarterly/annual income statements
2. `balance_sheets` - Quarterly/annual balance sheets
3. `cash_flow_statements` - Quarterly/annual/TTM cash flows
4. `financial_ratios` - Pre-calculated ratios

### Market Data (Normalized)
5. `short_interest` - Short interest by settlement date
6. `short_volume` - Daily short volume
7. `share_float` - Shares outstanding and float

### Risk Data (Normalized)
8. `risk_factors` - Individual risk factors from SEC filings
9. `risk_categories` - Categorized risks

### Denormalized (Fast Queries)
10. `enhanced_fundamentals` - Combined key metrics for fast access

### Existing Tables (Already Covered)
11. `stock_news` - News articles
12. `earnings_data` - Earnings calendar/history
13. `aggregated_indicators` - Technical indicators
14. `raw_market_data` - OHLCV price data

## Indexes for Performance

All tables have indexes on:
- `stock_symbol` + `date/period_end` (DESC) for time-series queries
- Composite indexes for common screening queries
- Fiscal year/quarter indexes for financial statement queries

## Next Steps

1. ✅ Database tables created (Migration 019)
2. ⏳ Update data source methods to populate new tables
3. ⏳ Create data refresh jobs for new endpoints
4. ⏳ Update alert system to use new data
5. ⏳ Update blog generation to use comprehensive data
6. ⏳ Create screening queries using new tables

## API Subscription Requirements

Some endpoints require specific subscription tiers:
- **Stocks Advanced** or higher: Financial statements, ratios
- **Financials & Ratios Expansion**: Full financial data access
- Check your subscription tier for endpoint availability

## References

- [Massive.com Income Statements API](https://massive.com/docs/rest/stocks/fundamentals/income-statements)
- [Massive.com Balance Sheets API](https://massive.com/docs/rest/stocks/fundamentals/balance-sheets)
- [Massive.com Cash Flow Statements API](https://massive.com/docs/rest/stocks/fundamentals/cash-flow-statements)
- [Massive.com Ratios API](https://massive.com/docs/rest/stocks/fundamentals/ratios)
- [Massive.com Short Interest API](https://massive.com/docs/rest/stocks/fundamentals/short-interest)
- [Massive.com Short Volume API](https://massive.com/docs/rest/stocks/fundamentals/short-volume)
- [Massive.com Float API](https://massive.com/docs/rest/stocks/fundamentals/float)
- [Massive.com Risk Factors API](https://massive.com/docs/rest/stocks/filings/risk-factors)
- [Massive.com Risk Categories API](https://massive.com/docs/rest/stocks/filings/risk-categories)

