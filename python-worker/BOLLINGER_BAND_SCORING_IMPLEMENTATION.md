# Bollinger Band Scoring System Implementation Guide

## 🎯 Overview

This document outlines the implementation of a Bollinger Band scoring system that enhances existing signal quality without disrupting current functionality. The system adds normalized BB context and confidence adjustment on top of existing calculations.

## 📊 What We Already Have (✅ Keep As-Is)

### **Existing BB Calculations:**
```sql
-- indicators_daily table (already exists)
bb_upper REAL,    -- Bollinger Bands upper
bb_middle REAL,   -- Bollinger Bands middle (SMA20)
bb_lower REAL,    -- Bollinger Bands lower
bb_width REAL,    -- Bollinger Band width
```

### **Existing BB Usage:**
- ✅ **Regime scoring** using BB width
- ✅ **Chop detection** with squeeze thresholds
- ✅ **Position sizing** penalties on squeeze
- ✅ **UI explanations** and visualizations

**👉 DO NOT remove or change any existing functionality**

## 🆕 What We Add (Layer on Top)

### **Two New Derived Metrics:**

#### **A️⃣ %B (Band Position Score)**
```python
def calculate_bb_position(price: float, bb_upper: float, bb_lower: float) -> float:
    """
    Calculate %B - where price sits within Bollinger Bands
    
    Range: 0 → 1
    Meaning: 0 = at lower band, 0.5 = middle, 1 = upper band
    """
    if bb_upper == bb_lower:
        return 0.5  # Edge case: no band width
    
    bb_position = (price - bb_lower) / (bb_upper - bb_lower)
    return max(0.0, min(1.0, bb_position))  # Clamp to [0,1]
```

#### **B️⃣ BB Width Percentile (Historical Context)**
```python
def calculate_bb_width_percentile(current_bb_width: float, historical_widths: List[float]) -> float:
    """
    Calculate percentile rank of current BB width vs historical context
    
    Range: 0 → 1
    Meaning: 0 = very tight (squeeze), 1 = very wide (chaos)
    """
    if not historical_widths:
        return 0.5  # Default to middle if no history
    
    # Calculate percentile rank
    count_lower = sum(1 for w in historical_widths if w <= current_bb_width)
    percentile = count_lower / len(historical_widths)
    return max(0.0, min(1.0, percentile))
```

## 🎯 BB Scoring System

### **1. Sub-Scores (0-1 each)**

#### **A️⃣ Position Score (from %B)**
```python
def calculate_position_score(bb_position: float) -> float:
    """
    Convert %B to position score
    
    High score = stretched down (oversold)
    Low score = stretched up (overbought)
    """
    if bb_position <= 0.15:
        return 1.0  # At/near lower band
    elif bb_position <= 0.35:
        return 0.7  # Lower half
    elif bb_position <= 0.65:
        return 0.5  # Middle zone
    elif bb_position <= 0.85:
        return 0.3  # Upper half
    else:
        return 0.0  # At/near upper band
```

#### **B️⃣ Width Score (from Percentile)**
```python
def calculate_width_score(bb_width_pct_rank: float) -> float:
    """
    Convert BB width percentile to width score
    
    High score = energy building (tight bands)
    Low score = late/unstable (wide bands)
    """
    if bb_width_pct_rank <= 0.20:
        return 1.0  # Very tight (squeeze)
    elif bb_width_pct_rank <= 0.40:
        return 0.7  # Tight
    elif bb_width_pct_rank <= 0.60:
        return 0.5  # Normal
    elif bb_width_pct_rank <= 0.80:
        return 0.3  # Wide
    else:
        return 0.0  # Very wide (chaos)
```

#### **C️⃣ Expansion Direction Score**
```python
def calculate_expansion_score(bb_width_current: float, bb_width_previous: float, 
                            price_direction: str, regime: str) -> float:
    """
    Score based on BB expansion direction and alignment with regime
    
    Conditions:
    - Width expanding with regime = 1.0
    - Width stable = 0.6
    - Width expanding against regime = 0.2
    - Width spiking = 0.0
    """
    width_change = (bb_width_current - bb_width_previous) / bb_width_previous
    
    # Detect spike (extreme expansion)
    if width_change > 0.5:  # 50%+ increase in width
        return 0.0
    
    # Stable width
    if abs(width_change) < 0.1:  # <10% change
        return 0.6
    
    # Expanding width
    if width_change > 0:
        # Check alignment with regime
        if regime in ["BREAKOUT", "VOLATILITY_EXPANSION"]:
            return 1.0  # Expansion aligns with regime
        elif regime == "MEAN_REVERSION":
            return 0.2  # Expansion against regime
        else:  # TREND_CONTINUATION
            return 0.7  # Moderately aligned
    else:
        # Contracting width
        return 0.4  # Neutral
```

### **2. Regime-Aware BB Score (0-1)**
```python
def calculate_bb_score(position_score: float, width_score: float, 
                      expansion_score: float, regime: str) -> float:
    """
    Calculate composite BB score with regime-aware weighting
    
    Different regimes value BB characteristics differently
    """
    if regime == "MEAN_REVERSION":
        # Mean reversion cares most about position (oversold/overbought)
        bb_score = 0.6 * position_score + 0.3 * width_score + 0.1 * expansion_score
    
    elif regime == "TREND_CONTINUATION":
        # Trend continuation values expansion direction most
        bb_score = 0.3 * position_score + 0.2 * width_score + 0.5 * expansion_score
    
    elif regime == "BREAKOUT":
        # Breakout values width expansion most
        bb_score = 0.2 * position_score + 0.5 * width_score + 0.3 * expansion_score
    
    elif regime == "VOLATILITY_EXPANSION":
        # Volatility expansion heavily weights width
        bb_score = 0.2 * position_score + 0.6 * width_score + 0.2 * expansion_score
    
    else:  # Default/unknown regime
        bb_score = 0.4 * position_score + 0.3 * width_score + 0.3 * expansion_score
    
    return max(0.0, min(1.0, bb_score))
```

## 🔧 Implementation Plan

### **Phase 1: Database Layer (1-2 days)**

#### **A. Add New Columns to indicators_daily:**
```sql
ALTER TABLE indicators_daily ADD COLUMN bb_position REAL;
ALTER TABLE indicators_daily ADD COLUMN bb_width_pct_rank REAL;
```

#### **B. Update Indicator Calculation:**
```python
# In load_one_year_data_fixed.py or similar
def calculate_bollinger_indicators(df):
    """Enhanced BB calculation with new metrics"""
    
    # Existing BB calculation (keep as-is)
    df['bb_middle'] = df['sma_20']
    bb_std = df['close'].rolling(window=20, min_periods=1).std()
    df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
    df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
    
    # NEW: Calculate %B
    df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
    df['bb_position'] = df['bb_position'].fillna(0.5)  # Default to middle
    
    # NEW: Calculate BB width percentile (60-day rolling)
    df['bb_width_pct_rank'] = df['bb_width'].rolling(window=60, min_periods=20).apply(
        lambda x: (x.iloc[-1] <= x).sum() / len(x), raw=False
    )
    df['bb_width_pct_rank'] = df['bb_width_pct_rank'].fillna(0.5)  # Default to middle
    
    return df
```

#### **C. Backfill Script:**
```python
def backfill_bb_metrics():
    """One-time script to backfill new BB metrics for historical data"""
    
    symbols = ['TQQQ', 'QQQ', 'SPY', 'IWM']  # Add your symbols
    
    for symbol in symbols:
        # Get historical data
        df = get_historical_indicators(symbol)
        
        # Calculate new metrics
        df = calculate_bollinger_indicators(df)
        
        # Update database
        update_indicators_with_bb_metrics(symbol, df)
```

### **Phase 2: BB Scoring Utilities (1-2 days)**

#### **A. Create New Utility Module:**
```python
# app/utils/bollinger_scoring.py

class BollingerScoringUtils:
    """Utilities for Bollinger Band scoring and analysis"""
    
    @staticmethod
    def calculate_all_bb_scores(price: float, bb_upper: float, bb_middle: float, 
                               bb_lower: float, bb_width: float, bb_width_pct_rank: float,
                               bb_width_previous: float, regime: str) -> Dict[str, float]:
        """
        Calculate all BB scores in one call
        
        Returns:
        {
            'bb_position': float,
            'position_score': float,
            'width_score': float,
            'expansion_score': float,
            'bb_score': float
        }
        """
        # Calculate %B
        bb_position = calculate_bb_position(price, bb_upper, bb_lower)
        
        # Calculate sub-scores
        position_score = calculate_position_score(bb_position)
        width_score = calculate_width_score(bb_width_pct_rank)
        
        # Determine price direction (simplified)
        price_direction = "neutral"  # Could be enhanced with actual price trend
        
        # Calculate expansion score
        expansion_score = calculate_expansion_score(
            bb_width, bb_width_previous, price_direction, regime
        )
        
        # Calculate composite BB score
        bb_score = calculate_bb_score(position_score, width_score, expansion_score, regime)
        
        return {
            'bb_position': bb_position,
            'position_score': position_score,
            'width_score': width_score,
            'expansion_score': expansion_score,
            'bb_score': bb_score
        }
    
    @staticmethod
    def adjust_confidence_with_bb(engine_confidence: float, bb_score: float) -> float:
        """
        Adjust signal confidence based on BB score
        
        Formula: final_confidence = engine_confidence * (0.7 + 0.6 * bb_score)
        
        Effects:
        - BB can boost confidence by up to +60%
        - Bad BB setups naturally decay trades
        - Confidence remains capped at 1.0
        """
        confidence_multiplier = (0.7 + 0.6 * bb_score)
        final_confidence = engine_confidence * confidence_multiplier
        return min(1.0, max(0.0, final_confidence))
```

### **Phase 3: Signal Engine Integration (1-2 days)**

#### **A. Modify Signal Engines:**
```python
# In unified_tqqq_swing_engine.py or similar

from app.utils.bollinger_scoring import BollingerScoringUtils

class UnifiedTQQQSwingEngine:
    def generate_signal(self, conditions: MarketConditions) -> SignalResult:
        """
        Generate signal with BB-enhanced confidence
        """
        # Existing signal generation logic (keep as-is)
        # ... existing code ...
        
        # NEW: Get BB data from conditions
        bb_data = conditions.bb_data  # Add BB data to MarketConditions
        
        # NEW: Calculate BB scores
        bb_scores = BollingerScoringUtils.calculate_all_bb_scores(
            price=conditions.current_price,
            bb_upper=bb_data.get('bb_upper'),
            bb_middle=bb_data.get('bb_middle'),
            bb_lower=bb_data.get('bb_lower'),
            bb_width=bb_data.get('bb_width'),
            bb_width_pct_rank=bb_data.get('bb_width_pct_rank'),
            bb_width_previous=bb_data.get('bb_width_previous'),
            regime=self.current_regime
        )
        
        # NEW: Adjust confidence with BB score
        original_confidence = result.confidence
        enhanced_confidence = BollingerScoringUtils.adjust_confidence_with_bb(
            original_confidence, bb_scores['bb_score']
        )
        
        # NEW: Add BB reasoning to metadata
        result.metadata.update({
            'bb_scores': bb_scores,
            'original_confidence': original_confidence,
            'bb_confidence_boost': enhanced_confidence - original_confidence,
            'bb_reasoning': self._generate_bb_reasoning(bb_scores)
        })
        
        # Update confidence
        result.confidence = enhanced_confidence
        
        return result
```

#### **B. Update MarketConditions:**
```python
# In signal_calculator_core.py

@dataclass
class MarketConditions:
    # ... existing fields ...
    
    # NEW: BB data
    bb_data: Dict[str, float] = None  # {'bb_upper', 'bb_lower', 'bb_width', etc.}
```

### **Phase 4: Quality-Based Optimizer (2-3 days)**

#### **A. Enhance QualityBasedOptimizer:**
```python
# In swing_regime_engine.py or similar

class QualityBasedOptimizer:
    def calculate_quality_score(self, signal_result: SignalResult, 
                              bb_score: float, regime: str) -> float:
        """
        Calculate overall signal quality score
        
        Formula:
        quality_score = 0.6 * final_confidence + 0.3 * bb_score + 0.1 * regime_stability
        """
        final_confidence = signal_result.confidence
        regime_stability = self._calculate_regime_stability(regime)
        
        quality_score = (
            0.6 * final_confidence + 
            0.3 * bb_score + 
            0.1 * regime_stability
        )
        
        return quality_score
    
    def get_position_size_multiplier(self, quality_score: float) -> float:
        """
        Convert quality score to position size multiplier
        
        Quality Buckets:
        - ≥ 0.75: Full size (1.0x)
        - 0.55-0.75: Reduced (0.7x)
        - 0.40-0.55: HOLD (0.3x)
        - < 0.40: Reject (0.0x)
        """
        if quality_score >= 0.75:
            return 1.0  # Full size
        elif quality_score >= 0.55:
            return 0.7  # Reduced size
        elif quality_score >= 0.40:
            return 0.3  # Small size
        else:
            return 0.0  # Reject signal
```

### **Phase 5: UI Enhancements (1 day)**

#### **A. Add BB Score Display:**
```python
# In streamlit-app/app.py or similar

def display_bb_scores(bb_scores: Dict[str, float]):
    """Display BB scoring information in UI"""
    
    st.markdown("### 📊 Bollinger Band Analysis")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("BB Position", f"{bb_scores['bb_position']:.2f}")
        st.metric("Position Score", f"{bb_scores['position_score']:.2f}")
    
    with col2:
        st.metric("Width Score", f"{bb_scores['width_score']:.2f}")
        st.metric("Expansion Score", f"{bb_scores['expansion_score']:.2f}")
    
    with col3:
        st.metric("BB Score", f"{bb_scores['bb_score']:.2f}")
        
        # Quality indicator
        if bb_scores['bb_score'] >= 0.7:
            st.success("🟢 High Quality")
        elif bb_scores['bb_score'] >= 0.4:
            st.warning("🟡 Medium Quality")
        else:
            st.error("🔴 Low Quality")
    
    # BB reasoning
    if 'bb_reasoning' in bb_scores:
        st.markdown("**BB Analysis:**")
        for reason in bb_scores['bb_reasoning']:
            st.write(f"• {reason}")
```

## 📋 Testing Strategy

### **Unit Tests:**
```python
def test_bb_position_calculation():
    """Test %B calculation edge cases"""
    # Test at lower band
    assert calculate_bb_position(100, 120, 100) == 0.0
    
    # Test at upper band
    assert calculate_bb_position(120, 120, 100) == 1.0
    
    # Test at middle
    assert calculate_bb_position(110, 120, 100) == 0.5

def test_confidence_adjustment():
    """Test confidence adjustment formula"""
    # Test maximum boost
    final_conf = adjust_confidence_with_bb(0.5, 1.0)
    assert final_conf == 0.8  # 0.5 * (0.7 + 0.6 * 1.0) = 0.8
    
    # Test no boost
    final_conf = adjust_confidence_with_bb(0.5, 0.0)
    assert final_conf == 0.35  # 0.5 * (0.7 + 0.6 * 0.0) = 0.35
```

### **Integration Tests:**
```python
def test_bb_scoring_integration():
    """Test BB scoring with real market data"""
    
    # Load test data
    test_data = load_test_tqqq_data()
    
    # Calculate BB scores
    bb_scores = BollingerScoringUtils.calculate_all_bb_scores(
        price=test_data['close'],
        bb_upper=test_data['bb_upper'],
        bb_middle=test_data['bb_middle'],
        bb_lower=test_data['bb_lower'],
        bb_width=test_data['bb_width'],
        bb_width_pct_rank=test_data['bb_width_pct_rank'],
        bb_width_previous=test_data['bb_width_previous'],
        regime="MEAN_REVERSION"
    )
    
    # Validate score ranges
    assert 0.0 <= bb_scores['bb_score'] <= 1.0
    assert 0.0 <= bb_scores['position_score'] <= 1.0
    assert 0.0 <= bb_scores['width_score'] <= 1.0
    assert 0.0 <= bb_scores['expansion_score'] <= 1.0
```

### **Performance Tests:**
```python
def test_bb_scaling_performance():
    """Test BB scoring performance with large datasets"""
    
    # Generate large dataset
    large_dataset = generate_test_data(n=10000)
    
    # Time BB scoring calculations
    start_time = time.time()
    
    for data in large_dataset:
        bb_scores = BollingerScoringUtils.calculate_all_bb_scores(**data)
    
    elapsed_time = time.time() - start_time
    
    # Should process < 100ms per signal
    assert elapsed_time < 1.0  # 10000 signals in < 1 second
```

## 📊 Monitoring & Validation

### **Key Metrics to Track:**
1. **BB Score Distribution**: Ensure scores are well-distributed across 0-1 range
2. **Confidence Boost Impact**: Track how often BB scores boost/reduce confidence
3. **Quality Bucket Performance**: Monitor win rates by quality bucket
4. **False Breakout Reduction**: Track reduction in false breakout signals

### **Validation Checklist:**
- [ ] BB position values are within [0,1] range
- [ ] BB width percentiles are historically accurate
- [ ] Composite BB scores make sense for each regime
- [ ] Confidence adjustments don't overfit
- [ ] Quality buckets show meaningful performance differences
- [ ] UI displays are accurate and helpful

## 🚀 Deployment Strategy

### **Phase 1: Shadow Mode**
- Calculate BB scores alongside existing signals
- Don't affect trading decisions yet
- Collect performance data

### **Phase 2: A/B Testing**
- Enable BB scoring for 10% of signals
- Compare performance vs control group
- Gradually increase based on results

### **Phase 3: Full Rollout**
- Enable BB scoring for all signals
- Monitor performance closely
- Fine-tune parameters as needed

## 📚 Reference Implementation

### **Complete Example:**
```python
# Example: Complete BB scoring workflow
def enhanced_signal_generation(symbol: str, date: str) -> SignalResult:
    """Complete example of enhanced signal generation with BB scoring"""
    
    # 1. Get market data (existing)
    market_data = get_market_data(symbol, date)
    
    # 2. Get BB indicators (existing + new)
    bb_indicators = get_bb_indicators(symbol, date)
    
    # 3. Determine regime (existing)
    regime = determine_market_regime(market_data, bb_indicators)
    
    # 4. Generate base signal (existing)
    base_signal = generate_base_signal(market_data, regime)
    
    # 5. Calculate BB scores (NEW)
    bb_scores = BollingerScoringUtils.calculate_all_bb_scores(
        price=market_data['close'],
        bb_upper=bb_indicators['bb_upper'],
        bb_middle=bb_indicators['bb_middle'],
        bb_lower=bb_indicators['bb_lower'],
        bb_width=bb_indicators['bb_width'],
        bb_width_pct_rank=bb_indicators['bb_width_pct_rank'],
        bb_width_previous=bb_indicators['bb_width_previous'],
        regime=regime
    )
    
    # 6. Adjust confidence (NEW)
    enhanced_confidence = BollingerScoringUtils.adjust_confidence_with_bb(
        base_signal.confidence, bb_scores['bb_score']
    )
    
    # 7. Calculate quality score (NEW)
    quality_score = QualityBasedOptimizer().calculate_quality_score(
        base_signal, bb_scores['bb_score'], regime
    )
    
    # 8. Determine position size (NEW)
    position_multiplier = QualityBasedOptimizer().get_position_size_multiplier(
        quality_score
    )
    
    # 9. Return enhanced signal
    return SignalResult(
        signal=base_signal.signal,
        confidence=enhanced_confidence,
        reasoning=base_signal.reasoning + bb_scores['bb_reasoning'],
        metadata={
            **base_signal.metadata,
            'bb_scores': bb_scores,
            'quality_score': quality_score,
            'position_multiplier': position_multiplier
        }
    )
```

## ✅ Summary

This implementation adds a sophisticated Bollinger Band scoring system that:

1. **Preserves all existing functionality** (no breaking changes)
2. **Adds normalized BB context** through %B and width percentiles
3. **Provides regime-aware scoring** for different market conditions
4. **Enhances confidence calibration** with BB-based adjustments
5. **Enables quality-based position sizing** for better risk management
6. **Improves explainability** with detailed BB reasoning

The system is designed for **gradual implementation** with **minimal risk** and **maximum impact** on signal quality.

**Estimated Timeline: 2-3 weeks total**
**Risk Level: Very Low**
**Expected Impact: High**
