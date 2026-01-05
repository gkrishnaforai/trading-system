# Swing Regime Engine Architecture

Location:
- `python-worker/app/signal_engines/swing_regime_engine.py`

This document describes the **current** Swing Regime Engine design (Yahoo proxies + internal breadth) and an explicit roadmap for future ML upgrades.

## Scope & Goals

- Provide a **regime-aware swing trading signal** with a clear Layer 1→5 breakdown.
- Keep the implementation **DRY** (single-source thresholds, small helper methods) and **SOLID** (single-responsibility helpers, no cross-layer coupling).
- Use **existing data sources only** for now:
  - Yahoo proxies for macro series
  - Internal breadth computed from our stored universe

## Data Dependencies (Current)

### Market / Symbol data (per traded symbol)
- Daily OHLCV: `raw_market_data_daily`
- Daily indicators: `indicators_daily` (at minimum: `rsi`, `macd`, `macd_signal`, `macd_hist`, `atr`, `bb_width`, `sma50`, `sma200`)

### Macro / Market context
Derived nightly via `MacroRefreshService` and stored in `macro_market_data`.

Yahoo proxy tickers:
- NASDAQ trend proxy: `QQQ`
- VIX: `^VIX`
- Rates proxy (current): `^TNX` and `^IRX` (spread = `^TNX - ^IRX`)

Internal breadth proxy:
- `% of symbols above 50d SMA` computed from:
  - `raw_market_data_daily.close`
  - `indicators_daily.sma_50`

## Layered Model (Current)

### Layer 1: Market Regime Detection (MarketContextService)
Inputs (from `macro_market_data`):
- NASDAQ proxy trend: close vs SMA50/SMA200
- VIX
- Yield curve proxy spread
- Breadth proxy (% above 50d)

Outputs:
- `MarketRegime`: `BULL | BEAR | HIGH_VOL_CHOP | NO_TRADE`
- `regime_confidence` (0–1)

### Layer 2: Direction & Confidence (SwingRegimeEngine)
Current state:
- Rule-based scoring using:
  - Momentum (1d/5d/21d returns)
  - Volatility expansion (ATR%, BB width)
  - RSI/MACD with regime awareness
  - Price action patterns

Outputs:
- `direction_score` (signed)
- `confidence` (0–1)

### Layer 3: Allocation Engine
- Converts `confidence` + regime into `position_size_pct` with regime-specific caps.

### Layer 4: Leveraged ETF Reality Adjustments (Chop/Decay)
Purpose:
- Penalize exposure when leveraged ETFs are likely to underperform due to chop + volatility decay.

Current rules (no new APIs):
- High VIX increases decay risk
- High realized vol (ATR%) increases decay risk
- **Chop detection** via:
  - Bollinger squeeze (low `bb_width`)
  - High VIX + low momentum penalty

Output:
- Adjusted position size (may reduce to 0)

### Layer 5: Daily Output (API/Streamlit)
The API returns a structured `layers` payload for Streamlit:
- Regime snapshot
- Direction probabilities (currently derived)
- Allocation decision
- Reality adjustment details
- One clear “Daily Output” summary

## ML Upgrade Path (Future Work)

### Goal
Replace the rule-based Layer 2 direction scoring with a trained model (e.g. XGBoost/LightGBM).

### What ML needs from the data side
1. **Historical training set** (2+ years daily per traded symbol)
   - OHLCV
   - indicators at time *t*
   - macro context at time *t* (join on date)
2. **Target definition**
   - Next-day return classification (UP/DOWN/FLAT) with thresholds (e.g. ±0.5%)
3. **Strict walk-forward validation**
   - Time-based splits (no leakage)
4. **Model artifact storage**
   - Versioned model file (and feature list) accessible to the worker

### Recommended implementation layout (DRY/SOLID)
- `app/ml/swing_direction/feature_builder.py`
- `app/ml/swing_direction/train.py`
- `app/ml/swing_direction/model.py` (load + predict)

### Inference contract
- Engine should accept a `DirectionModel` interface:
  - `predict_proba(features) -> {prob_up, prob_down, prob_flat}`
- If model is missing/unavailable:
  - fallback to current rule-based scoring

## Extension Guidelines

- Keep thresholds/config in one place.
- Keep each layer’s logic in dedicated helpers.
- Avoid adding new external data dependencies without an explicit refresh + persistence plan.
