# Schema Enhancements for Traders and Analysts

## Overview

Comprehensive database schema enhancements to support professional traders and analysts. Based on industry standards from Bloomberg Terminal, TradingView, Interactive Brokers, and other professional trading platforms.

## Migration: `006_enhance_portfolio_watchlist_for_traders.sql`

## Portfolio Enhancements

### New Fields Added

| Field | Type | Description | Use Case |
|-------|------|-------------|----------|
| `portfolio_type` | TEXT | Type: long_term, swing, day_trading, options, crypto, mixed | Categorize portfolios by trading style |
| `currency` | TEXT | Portfolio currency (default: USD) | Multi-currency support |
| `benchmark_symbol` | TEXT | Benchmark for comparison (e.g., SPY, QQQ) | Performance comparison |
| `target_allocation` | JSON | Target sector/asset allocation | Rebalancing targets |
| `risk_tolerance` | TEXT | conservative, moderate, aggressive | Risk management |
| `investment_horizon` | TEXT | short_term, medium_term, long_term | Strategy alignment |
| `is_taxable` | BOOLEAN | Taxable vs tax-advantaged account | Tax optimization |
| `tax_strategy` | TEXT | Tax-loss harvesting strategy | Tax optimization |
| `rebalancing_frequency` | TEXT | daily, weekly, monthly, quarterly, annually, manual | Rebalancing automation |
| `last_rebalanced` | DATE | Last rebalancing date | Rebalancing tracking |
| `color_code` | TEXT | UI organization color | Visual organization |
| `is_archived` | BOOLEAN | Archive old portfolios | Portfolio lifecycle |
| `metadata` | JSON | Additional flexible metadata | Extensibility |

## Holdings Enhancements

### New Fields Added

| Field | Type | Description | Use Case |
|-------|------|-------------|----------|
| `current_price` | REAL | Cached current price | Real-time valuation |
| `current_value` | REAL | quantity * current_price | Position value |
| `cost_basis` | REAL | Total cost basis | Tax reporting |
| `unrealized_gain_loss` | REAL | Unrealized P&L | Performance tracking |
| `unrealized_gain_loss_percent` | REAL | Unrealized P&L % | Performance tracking |
| `realized_gain_loss` | REAL | Realized P&L | Tax reporting |
| `exit_price` | REAL | Exit price | Closed position tracking |
| `exit_date` | DATE | Exit date | Closed position tracking |
| `commission` | REAL | Trading commission | Cost tracking |
| `tax_lot_id` | TEXT | Tax lot tracking | Tax optimization |
| `cost_basis_method` | TEXT | FIFO, LIFO, average, specific_lot | Tax reporting |
| `sector` | TEXT | Cached sector | Sector analysis |
| `industry` | TEXT | Cached industry | Industry analysis |
| `market_cap_category` | TEXT | mega, large, mid, small, micro | Market cap analysis |
| `dividend_yield` | REAL | Cached dividend yield | Income tracking |
| `target_price` | REAL | Target exit price | Exit strategy |
| `stop_loss_price` | REAL | Stop loss price | Risk management |
| `take_profit_price` | REAL | Take profit price | Profit taking |
| `allocation_percent` | REAL | % of portfolio | Portfolio analysis |
| `target_allocation_percent` | REAL | Target % allocation | Rebalancing |
| `last_updated_price` | TIMESTAMP | Price update timestamp | Data freshness |
| `is_closed` | BOOLEAN | Closed position flag | Position lifecycle |
| `closed_reason` | TEXT | Why position was closed | Analysis |
| `metadata` | JSON | Additional flexible metadata | Extensibility |

## Watchlist Enhancements

### New Fields Added

| Field | Type | Description | Use Case |
|-------|------|-------------|----------|
| `color_code` | TEXT | UI organization color | Visual organization |
| `sort_order` | INTEGER | Custom sort order | Custom organization |
| `view_preferences` | JSON | Column visibility, sort preferences | UI customization |
| `is_archived` | BOOLEAN | Archive old watchlists | Watchlist lifecycle |
| `metadata` | JSON | Additional flexible metadata | Extensibility |

## Watchlist Items Enhancements

### New Fields Added

| Field | Type | Description | Use Case |
|-------|------|-------------|----------|
| `price_when_added` | REAL | Price when added | Performance tracking |
| `target_price` | REAL | Target entry price | Entry strategy |
| `target_date` | DATE | Target date for entry | Entry timing |
| `watch_reason` | TEXT | Why watching this stock | Analysis notes |
| `analyst_rating` | TEXT | strong_buy, buy, hold, sell, strong_sell | Analyst consensus |
| `analyst_price_target` | REAL | Analyst consensus price target | Price target tracking |
| `current_price` | REAL | Cached current price | Real-time tracking |
| `price_change_since_added` | REAL | Price change since added | Performance tracking |
| `price_change_percent_since_added` | REAL | % change since added | Performance tracking |
| `sector` | TEXT | Cached sector | Sector analysis |
| `industry` | TEXT | Cached industry | Industry analysis |
| `market_cap_category` | TEXT | mega, large, mid, small, micro | Market cap analysis |
| `dividend_yield` | REAL | Cached dividend yield | Income tracking |
| `earnings_date` | DATE | Next earnings date | Event tracking |
| `last_updated_price` | TIMESTAMP | Price update timestamp | Data freshness |
| `metadata` | JSON | Additional flexible metadata | Extensibility |

## New Tables

### Portfolio Performance

Tracks daily/weekly/monthly portfolio performance snapshots.

**Fields:**
- `portfolio_id`, `snapshot_date`
- `total_value`, `cost_basis`, `total_gain_loss`, `total_gain_loss_percent`
- `cash_balance`, `invested_amount`
- `day_change`, `week_change`, `month_change`, `year_change` (with %)
- `max_drawdown`, `sharpe_ratio`, `beta`, `alpha`
- `sector_allocation`, `top_holdings` (JSON)

**Use Cases:**
- Historical performance analysis
- Risk metrics tracking
- Benchmark comparison
- Performance attribution

### Watchlist Performance

Tracks watchlist-level performance metrics.

**Fields:**
- `watchlist_id`, `snapshot_date`
- `total_stocks`, `avg_price_change`, `avg_price_change_percent`
- `bullish_count`, `bearish_count`, `neutral_count`
- `high_risk_count`, `medium_risk_count`, `low_risk_count`
- `sector_distribution`, `top_gainers`, `top_losers` (JSON)

**Use Cases:**
- Watchlist performance tracking
- Sector analysis
- Stock screening effectiveness

### Trading Activity Log

Comprehensive audit log of all trading activities.

**Fields:**
- `activity_id`, `user_id`, `portfolio_id`, `watchlist_id`
- `stock_symbol`, `activity_type` (buy, sell, add_to_watchlist, etc.)
- `quantity`, `price`, `commission`
- `notes`, `metadata` (JSON)
- `created_at`

**Use Cases:**
- Audit trail
- Compliance reporting
- Activity analysis
- Pattern recognition

## Industry Standards Alignment

### Bloomberg Terminal Features
✅ Portfolio performance tracking
✅ Sector allocation analysis
✅ Risk metrics (Sharpe, Beta, Alpha)
✅ Tax lot tracking
✅ Benchmark comparison

### TradingView Features
✅ Watchlist organization (color codes, sorting)
✅ Price targets and alerts
✅ Performance tracking
✅ Custom metadata

### Interactive Brokers Features
✅ Cost basis methods (FIFO, LIFO, Average)
✅ Tax reporting fields
✅ Commission tracking
✅ Position lifecycle tracking

### Robinhood/Webull Features
✅ Real-time P&L tracking
✅ Unrealized/realized gains
✅ Dividend tracking
✅ Earnings date tracking

## Use Cases Enabled

### For Traders
1. **Position Management**: Track entry/exit prices, P&L, stop-loss, take-profit
2. **Risk Management**: Stop-loss, position sizing, sector allocation
3. **Performance Analysis**: Historical performance, drawdown, Sharpe ratio
4. **Tax Optimization**: Tax lot tracking, cost basis methods, tax-loss harvesting
5. **Strategy Tracking**: Portfolio types, rebalancing, target allocations

### For Analysts
1. **Research Organization**: Watchlist reasons, analyst ratings, price targets
2. **Performance Tracking**: Price changes since added, earnings dates
3. **Sector Analysis**: Sector/industry breakdown, market cap categories
4. **Benchmark Comparison**: Portfolio vs benchmark performance
5. **Activity Analysis**: Trading activity logs, pattern recognition

## Migration Notes

- All new fields are nullable to support existing data
- Default values provided where appropriate
- Indexes created for performance
- JSON fields for flexible metadata
- Backward compatible with existing code

## Next Steps

1. Update Go models to include new fields
2. Update Python services to populate new fields
3. Add API endpoints for performance tracking
4. Implement rebalancing logic
5. Add tax reporting features
6. Create analytics dashboards

