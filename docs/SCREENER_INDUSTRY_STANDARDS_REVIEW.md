# Stock Screener Industry Standards Review

## Current Status vs Industry Best Practices

### ✅ What We Have

**Moving Averages:**
- ✅ EMA20 (short-term momentum)
- ✅ EMA50 (medium-term trend)
- ✅ SMA50 (medium-term trend)
- ✅ SMA200 (long-term regime)
- ✅ EMA9/EMA21 (fast momentum pair for swing trading)

**Indicators:**
- ✅ RSI (Relative Strength Index)
- ✅ MACD (Momentum Confirmation)
- ✅ ATR (Risk Management)
- ✅ Volume & Volume MA
- ✅ Price vs MA flags (below SMA50, below SMA200)

**Fundamentals:**
- ✅ Fundamental scoring (P/E, PEG, Revenue Growth, EPS Growth, Profit Margin, Debt/Equity)
- ✅ Growth stock flags
- ✅ Exponential growth flags

### ❌ What's Missing (Industry Standards)

**Moving Averages:**
- ❌ SMA100 (intermediate trend - optional but useful)
- ❌ EMA12/EMA26 (MACD base - we calculate MACD but don't store these separately)

**Crossover Detection:**
- ❌ Golden Cross (SMA50 > SMA200)
- ❌ Death Cross (SMA50 < SMA200)
- ❌ EMA9/EMA21 crossover flags
- ❌ EMA20/EMA50 crossover flags
- ❌ EMA12/EMA26 crossover flags

**RSI Zones:**
- ❌ RSI zone classification (oversold < 30, weak 30-45, healthy 45-60, overbought > 70)
- ❌ RSI staying above 40-50 confirmation

**Volume Confirmation:**
- ❌ Volume above average flag
- ❌ Volume spike detection (> 1.5x average)

**MACD Momentum:**
- ❌ MACD above signal flag
- ❌ MACD histogram positive flag

**Price Structure:**
- ❌ Higher highs detection
- ❌ Higher lows detection

**Best-Practice Signal Stack:**
- ❌ Integrated buy/sell signal evaluation
- ❌ Multi-layer confirmation system

## Industry Standard Buy Signal Stack

### ✅ BUY SIGNAL (High Quality) - All Must Align:

1. **Trend:**
   - ✅ Price > 200-day MA
   - ✅ 50-day MA rising

2. **Entry:**
   - ✅ EMA20 pullback OR EMA crossover
   - ⚠️ Need to add: Pullback detection logic

3. **Momentum:**
   - ✅ MACD rising (MACD > Signal, Histogram positive)
   - ✅ RSI between 45-65 (healthy zone)

4. **Confirmation:**
   - ⚠️ Volume above average (need flag)
   - ⚠️ No major resistance overhead (need price structure)

### ❌ SELL SIGNAL:

1. ❌ Price breaks below 50-day MA
2. ❌ EMA short crosses below long EMA
3. ❌ RSI falls below ~45
4. ❌ MACD turns negative
5. ❌ Volume expands on down days

## Implementation Plan

### Phase 1: Add Missing Indicators (Migration 015)

1. **Add SMA100** - Intermediate trend
2. **Add EMA12/EMA26** - MACD base components
3. **Add Crossover Flags:**
   - `ema9_above_ema21` - Fast momentum
   - `ema20_above_ema50` - Swing trend
   - `ema12_above_ema26` - MACD base
   - `sma50_above_sma200` - Golden Cross
   - `price_above_sma200` - Long-term bullish bias

4. **Add RSI Zones:**
   - `rsi_zone`: 'oversold' (< 30), 'weak' (30-45), 'healthy' (45-60), 'overbought' (> 70)

5. **Add Volume Flags:**
   - `volume_above_average` - Volume > Volume MA
   - `volume_spike` - Volume > 1.5x Volume MA

6. **Add MACD Flags:**
   - `macd_above_signal` - MACD line > Signal line
   - `macd_histogram_positive` - Histogram > 0

7. **Add Price Structure:**
   - `higher_highs` - Price making higher highs
   - `higher_lows` - Price making higher lows

### Phase 2: Update Indicator Service

1. Calculate SMA100, EMA12, EMA26
2. Calculate all crossover flags
3. Calculate RSI zones
4. Calculate volume confirmation flags
5. Calculate MACD momentum flags
6. Calculate price structure flags

### Phase 3: Enhance Screener Service

1. Add filters for:
   - Golden Cross / Death Cross
   - EMA crossover filters
   - RSI zone filters
   - Volume confirmation filters
   - MACD momentum filters
   - Price structure filters

2. Add "Best-Practice Buy Signal" preset

### Phase 4: Signal Stack Service

1. Implement `SignalStackService` for integrated buy/sell evaluation
2. Add API endpoint for signal stack evaluation
3. Integrate with screener for "high-quality signals" filter

## UX Presentation (Tier-Based)

### BASIC USER SEES:
```
Trend: Bullish
Signal: BUY PULLBACK
Risk: Medium
Reason:
• Price above long-term trend
• Momentum healthy
• Pullback within trend
```

### PRO USER SEES:
```
EMA20 > SMA50
RSI: 56
MACD: Rising
Volume: Confirmed
```

### ELITE USER SEES:
```
Agent rules
Backtests
Portfolio impact
Signal Stack Breakdown:
- Trend: ✅ (Price > 200MA, 50MA rising)
- Entry: ✅ (EMA20 pullback)
- Momentum: ✅ (MACD rising, RSI 56)
- Confirmation: ✅ (Volume spike)
```

## Next Steps

1. ✅ Create migration 015 for industry-standard indicators
2. ✅ Create SignalStackService
3. ⏳ Update IndicatorService to calculate all flags
4. ⏳ Update ScreenerService with new filters
5. ⏳ Add API endpoints
6. ⏳ Update Streamlit UI with tier-based presentation

