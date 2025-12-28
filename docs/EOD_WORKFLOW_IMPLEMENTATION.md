# EOD Workflow Implementation

## Overview

**Industry Standard**: End-of-Day workflow that separates daily vs periodic updates

**Key Principle**: Raw data → Derived data → Signals → Insights

---

## What Gets Updated EVERY DAY (EOD)

### ✅ Daily Updates (Time-Series, Market-Driven)

1. **Price & Market Data**
   - Open, High, Low, Close (OHLC)
   - Adjusted Close (dividends/splits adjusted)
   - Volume
   - VWAP (if available)
   - Daily return (%)
   - Gap up / gap down

2. **Technical Indicators** (Recomputed Daily)
   - **Moving Averages**: 9, 20, 50, 200
   - **Momentum**: RSI (14), MACD
   - **Volatility**: ATR, Bollinger Bands
   - **Volume**: Avg Volume (20/50), Volume spike detection
   - **Trend**: Bull / Bear / Sideways
   - **Support / Resistance levels**

   **⚠️ Important**: Indicators are **recomputed** from fresh price data daily, never use stale indicators.

3. **Signals** (Derived from Indicators)
   - MA crossover (Golden / Death cross)
   - RSI overbought / oversold
   - Breakout above resistance
   - Breakdown below support
   - Volume-confirmed moves
   - Trend continuation / reversal signals

### ❌ NOT Updated Daily

- **Fundamentals** (Quarterly / Annually)
- **Earnings** (Quarterly / Event-based)
- **Analyst Ratings** (Event-based)
- **News** (Event-based)

---

## Industry-Standard EOD Workflow

```
Market Close
   ↓
[Stage 1] Load Daily Price + Volume (Raw OHLCV)
   ↓
[Stage 2] Validate & Adjust (splits/dividends)
   ↓
[Stage 3] Recompute Indicators (from fresh price data)
   ↓
[Stage 4] Generate Signals (from indicators)
   ↓
[Stage 5] Update Watchlists & Portfolios
   ↓
[Stage 6] Trigger Alerts
   ↓
[Stage 7] Market Aggregations (movers, sectors, trends)
   ↓
[Stage 8] Generate Reports (optional, LLM)
```

---

## Implementation

### 1. EODWorkflow (`app/workflows/eod_workflow.py`)

**Purpose**: Orchestrates the complete EOD workflow

**Key Features**:
- ✅ Separates daily vs periodic updates
- ✅ Uses WorkflowOrchestrator for robust execution
- ✅ Fail-fast gates between stages
- ✅ Duplicate prevention built-in

**Usage**:
```python
from app.workflows.eod_workflow import EODWorkflow

workflow = EODWorkflow()
result = workflow.execute_daily_eod_workflow(symbols=['AAPL', 'GOOGL'])
```

### 2. UpdateStrategy (`app/workflows/update_strategy.py`)

**Purpose**: Determines what needs updating and when

**Key Features**:
- ✅ Frequency-aware update decisions
- ✅ Daily vs Quarterly vs Event-based logic
- ✅ Last update date tracking

**Usage**:
```python
from app.workflows.update_strategy import UpdateStrategy

strategy = UpdateStrategy()
daily_symbols = strategy.get_symbols_needing_daily_update()
quarterly_symbols = strategy.get_symbols_needing_quarterly_update()
```

### 3. BatchWorker (Refactored)

**Purpose**: Scheduled batch job execution

**Key Changes**:
- ✅ Uses EODWorkflow instead of direct calls
- ✅ Cleaner, more maintainable
- ✅ Follows industry standard workflow
- ✅ DRY: Reuses workflow components

---

## Data Storage Strategy

### ✅ Store (Permanent)

| Data Type | Why Store |
|-----------|-----------|
| Raw OHLCV | Source of truth, audit trail |
| Fundamentals | Slow-changing, quarterly |
| Signals | Audit & explain, user-facing |
| Portfolio/Watchlist data | User data, must persist |

### ⚠️ Store but Recompute Daily

| Data Type | Why |
|-----------|-----|
| Indicators | Performance (caching), but **always recompute from fresh price data** |

**Note**: We store indicators in `aggregated_indicators` for performance, but they are **recomputed daily** from fresh price data. This is acceptable for caching, but we never rely on stale indicators.

### ❌ Don't Store (Regenerate)

| Data Type | Why |
|-----------|-----|
| Explanations/Reports | Regenerate via LLM on-demand |

---

## Computation Strategy

### Batch Jobs (Daily)

- ✅ Run after market close
- ✅ Process all symbols in parallel (where possible)
- ✅ Incremental updates (only new candle)
- ✅ Cache popular indicators (but recompute daily)

### Incremental Updates

- ✅ Only process new data
- ✅ Check last update date before processing
- ✅ Skip if already updated today

### Parallel Processing

- ✅ Process symbols in parallel (future enhancement)
- ✅ Use workflow orchestrator for coordination

---

## DRY & SOLID Principles

### DRY (Don't Repeat Yourself)

✅ **Achieved**:
- `EODWorkflow` reuses `WorkflowOrchestrator`
- `UpdateStrategy` centralizes update logic
- `IdempotentDataSaver` reused for duplicate prevention
- Common database queries in helpers

### SOLID

✅ **Single Responsibility**:
- `EODWorkflow`: Only orchestrates EOD workflow
- `UpdateStrategy`: Only determines update needs
- `BatchWorker`: Only schedules and triggers jobs
- `WorkflowOrchestrator`: Only orchestrates workflow execution

✅ **Open/Closed**: 
- Workflow stages can be extended without modification
- New data types can be added via configuration

✅ **Liskov Substitution**:
- Gates can be substituted (BaseGate interface)
- Data savers can be substituted (IdempotentDataSaver)

✅ **Interface Segregation**:
- Small, focused interfaces (Gate, DataSaver, etc.)

✅ **Dependency Inversion**:
- Depend on abstractions (WorkflowOrchestrator, not concrete implementations)

---

## Key Differences from Previous Implementation

### Before

- ❌ Mixed daily and periodic updates
- ❌ No workflow orchestration
- ❌ No fail-fast gates
- ❌ No duplicate prevention strategy
- ❌ Indicators might be stale

### After

- ✅ Clear separation: Daily vs Periodic
- ✅ Workflow orchestration with gates
- ✅ Fail-fast between stages
- ✅ Duplicate prevention built-in
- ✅ Indicators always recomputed from fresh data

---

## Testing

### Unit Tests

```python
def test_eod_workflow_daily_only():
    """Test that EOD workflow only updates daily data"""
    workflow = EODWorkflow()
    result = workflow.execute_daily_eod_workflow(['AAPL'])
    
    # Should NOT update fundamentals (quarterly)
    assert 'fundamentals' not in result['stages']
```

### Integration Tests

```python
def test_eod_workflow_full_pipeline():
    """Test complete EOD workflow"""
    workflow = EODWorkflow()
    result = workflow.execute_daily_eod_workflow(['AAPL', 'GOOGL'])
    
    assert result['success'] == True
    assert result['stages']['price_loading']['succeeded'] > 0
    assert result['stages']['indicator_recomputation']['succeeded'] > 0
```

---

## Summary

✅ **Implemented**:
- Industry-standard EOD workflow
- Separation of daily vs periodic updates
- DRY and SOLID principles
- Duplicate prevention
- Fail-fast gates
- Workflow orchestration

✅ **Key Features**:
- Daily: Price, Volume, Indicators (recomputed), Signals
- Quarterly: Fundamentals, Earnings
- Event-based: News, Analyst ratings
- Indicators stored for performance but recomputed daily
- Safe to retry/re-run without duplicates

✅ **Production Ready**: Follows industry best practices

