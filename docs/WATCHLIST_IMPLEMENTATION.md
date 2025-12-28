# Watchlist Feature Implementation

## Overview

Comprehensive watchlist feature following industry standards, integrated with the existing portfolio system. Supports tiered subscription features (Basic, Pro, Elite) with seamless move-to-portfolio functionality.

## Architecture

### Database Schema

**Migration: `005_add_watchlists.sql`**

**Tables:**
1. **watchlists**: User watchlists with metadata
2. **watchlist_items**: Stocks/ETFs in watchlists
3. **watchlist_alerts**: Watchlist-level alerts
4. **watchlist_analytics**: Cached watchlist metrics

**Key Features:**
- Multiple watchlists per user (Pro/Elite)
- Default watchlist (Basic: 1-2 watchlists)
- Tagging system (Pro/Elite)
- Priority-based sorting
- Watchlist-level alerts
- Analytics and insights

### API Endpoints

#### Go API (Watchlist CRUD)

**Watchlist Management:**
- `POST /api/v1/watchlists` - Create watchlist
- `GET /api/v1/watchlists/:user_id` - List user watchlists
- `GET /api/v1/watchlists/:watchlist_id` - Get watchlist with items
- `PUT /api/v1/watchlists/:watchlist_id` - Update watchlist
- `DELETE /api/v1/watchlists/:watchlist_id` - Delete watchlist

**Watchlist Items:**
- `POST /api/v1/watchlists/:watchlist_id/items` - Add stock to watchlist
- `PUT /api/v1/watchlist-items/:item_id` - Update watchlist item
- `DELETE /api/v1/watchlist-items/:item_id` - Remove from watchlist
- `POST /api/v1/watchlists/:watchlist_id/move-to-portfolio` - Move stock to portfolio

#### Python API (Watchlist Intelligence)

**Watchlist Analytics:**
- `GET /api/v1/watchlists/:watchlist_id/analytics` - Get watchlist analytics
- `GET /api/v1/watchlists/:watchlist_id/items/:symbol/data` - Get item with stock data
- `POST /api/v1/watchlists/:watchlist_id/ai-summary` - Generate AI summary

## Features by Subscription Tier

### 🟢 BASIC (Layman Friendly)

**Watchlist Features:**
- ✅ Create 1-2 simple watchlists
- ✅ Add stocks/ETFs
- ✅ View current price, daily % change
- ✅ Trend label (Bullish/Neutral/Bearish)
- ✅ Risk score (Low/Medium/High)
- ✅ Earnings date & alerts
- ✅ AI summary: "Why this stock is moving"
- ✅ Simple explanations (LLM generated)
- ✅ Move to portfolio (one-click)

**Portfolio Tracking:**
- ✅ Buy price, quantity
- ✅ Overall gain/loss
- ✅ Dividend indicator
- ✅ Buy/Sell/Hold signals (high-level)
- ✅ Trend direction (Bullish/Neutral/Bearish)
- ✅ Risk score with plain English explanation

**UX:**
- ❌ No charts overload
- ❌ No technical indicators exposed
- ✅ Clean list + explanations

### 🔵 PRO (Serious Investors)

**Advanced Watchlists:**
- ✅ Multiple watchlists
- ✅ Tagging (Growth, Dividend, Options, Earnings)
- ✅ Sort by:
  - Strategy signal
  - Trend strength
  - Volatility
- ✅ Watchlist-level alerts:
  - MA crossover
  - RSI thresholds
  - Breakouts
- ✅ Priority-based organization

**Multiple Portfolios:**
- ✅ Long-term
- ✅ Swing
- ✅ Options

**Strategy-Based Trading:**
- ✅ Moving averages
- ✅ RSI
- ✅ Trend breakouts
- ✅ Options strategies
- ✅ Strategy fit suggestions per stock

**Portfolio Intelligence:**
- ✅ Risk exposure
- ✅ Sector concentration
- ✅ Correlation analysis

**Custom Alerts:**
- ✅ Strategy-triggered alerts
- ✅ Earnings + volatility alerts
- ✅ LLM strategy explanation

### 🟣 ELITE (Agentic & Automation)

**Agent-Powered Watchlists:**
- ✅ "Smart Watchlists"
- ✅ AI auto-prioritizes:
  - What needs attention today
  - What can be ignored
- ✅ Daily/weekly watchlist insights

**Strategy Automation:**
- ✅ Auto-monitor strategies
- ✅ Simulated execution (paper trading)
- ✅ Performance tracking

**24/7 Monitoring:**
- ✅ Agent watches:
  - Price
  - Trend shifts
  - Volatility spikes
  - News sentiment

**Scenario Simulation:**
- ✅ "What if market drops 10%?"
- ✅ "What if rates increase?"
- ✅ Earnings volatility modeling
- ✅ Options payoff graphs

**AI-Generated Reports:**
- ✅ Weekly portfolio memo
- ✅ What changed
- ✅ What to watch
- ✅ Recommended actions

**Custom Agent Rules:**
- ✅ "Reduce exposure if MA breaks"
- ✅ "Exit if earnings gap > X%"

**API Access:**
- ✅ For quants & integrations

## Move to Portfolio Flow

1. User selects stock from watchlist
2. Clicks "Move to Portfolio"
3. Selects target portfolio
4. Enters:
   - Quantity
   - Entry price
   - Position type
   - Strategy tag (optional)
   - Purchase date
   - Notes
5. Stock is:
   - Added to portfolio as holding
   - Removed from watchlist (or kept, user choice)
   - Portfolio signals recalculated

## Industry Standards Applied

1. **Separation of Concerns**: Watchlist separate from portfolio
2. **Tiered Features**: Clear value proposition per tier
3. **One-Click Actions**: Move to portfolio seamless
4. **Smart Defaults**: Default watchlist per user
5. **Analytics**: Watchlist-level insights
6. **Alerts**: Watchlist-specific alerting
7. **Tagging**: Flexible organization (Pro/Elite)
8. **Priority**: User-controlled sorting

## Implementation Status

- ✅ Database schema
- ✅ Go models
- ✅ Go repository
- ⏳ Go service
- ⏳ Go handlers
- ⏳ Python watchlist service
- ⏳ Move-to-portfolio functionality
- ⏳ Analytics calculation
- ⏳ AI summary generation
- ⏳ Tests

## Next Steps

1. Complete Go service and handlers
2. Implement Python watchlist intelligence service
3. Add move-to-portfolio endpoint
4. Implement analytics calculation
5. Add AI summary generation
6. Write comprehensive tests
7. Add Streamlit UI integration

