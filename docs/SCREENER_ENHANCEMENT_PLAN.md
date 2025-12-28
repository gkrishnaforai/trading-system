# Stock Screener Enhancement Plan

## Summary

Based on industry standards review, I've created:

1. ✅ **Migration 015** - Adds all industry-standard indicator columns and flags
2. ✅ **SignalStackService** - Implements best-practice buy/sell signal evaluation
3. ⏳ **Indicator Service Updates** - Need to calculate all new flags
4. ⏳ **Screener Service Updates** - Need to add new filter options

## What's Been Created

### 1. Database Migration (015_add_industry_standard_indicators.sql)

**New Columns:**

- `sma100` - Intermediate trend
- `ema12`, `ema26` - MACD base components
- `ema9_above_ema21` - Fast momentum crossover
- `ema20_above_ema50` - Swing trend crossover
- `ema12_above_ema26` - MACD base crossover
- `sma50_above_sma200` - Golden Cross flag
- `price_above_sma200` - Long-term bullish bias
- `rsi_zone` - RSI classification (oversold/weak/healthy/overbought)
- `volume_above_average` - Volume confirmation
- `volume_spike` - Volume spike detection (> 1.5x)
- `macd_above_signal` - MACD momentum
- `macd_histogram_positive` - MACD histogram direction
- `higher_highs`, `higher_lows` - Price structure

**Indexes:**

- Fast screening indexes for all new flags
- Composite index for best-practice buy signal

### 2. SignalStackService

Implements industry-standard buy/sell signal evaluation:

**Buy Signal (All Must Align):**

1. Trend: Price > 200MA, 50MA rising
2. Entry: EMA20 pullback OR EMA crossover
3. Momentum: MACD rising, RSI 45-65
4. Confirmation: Volume above average

**Sell Signal:**

- Price breaks below 50MA
- EMA cross below
- RSI < 45
- MACD negative
- Volume expanding on down days

### 3. Review Document

Created `SCREENER_INDUSTRY_STANDARDS_REVIEW.md` with:

- Current status vs industry standards
- Missing features identified
- Implementation plan
- UX presentation guidelines

## What Needs to Be Done

### Step 1: Update Indicator Service

Add calculations for:

1. SMA100, EMA12, EMA26 (already added to calculation section)
2. All crossover flags
3. RSI zone classification
4. Volume confirmation flags
5. MACD momentum flags
6. Price structure flags
7. Update SQL INSERT query to include all new fields

### Step 2: Update Screener Service

Add filter options for:

- Golden Cross / Death Cross
- EMA crossover filters
- RSI zone filters
- Volume confirmation
- MACD momentum
- Price structure
- Best-practice buy signal preset

### Step 3: Update Database Migration List

Add `015_add_industry_standard_indicators.sql` to migration list in `database.py`

### Step 4: Update API Endpoints

Add screener endpoints (already created in `api_screener.py` - needs integration)

## Current Status

✅ **Completed:**

- Migration 015 created
- SignalStackService created
- Review document created
- SMA100, EMA12, EMA26 added to calculations
- Indicators dict updated

⏳ **In Progress:**

- Flag calculations in indicator service
- SQL query updates
- Screener service enhancements

## Next Actions

1. Complete indicator service flag calculations
2. Update SQL INSERT query
3. Update screener service with new filters
4. Test with real data
5. Update Streamlit UI
