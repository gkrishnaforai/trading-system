# Fear/Greed Engine Analysis & Implementation Plan

## 🔍 Current State Analysis

### **What We Currently Have:**
✅ **VIX Integration**: We already fetch and use VIX levels
✅ **Market Stress Detection**: Basic boolean flag (`market_stress`)
✅ **Volatility Analysis**: Real volatility calculations
✅ **Market Context**: `calculate_market_regime_context()` function

### **What's Missing:**
❌ **Fear/Greed State Machine**: No formal fear/greed classification
❌ **Quantitative Fear/Greed Definitions**: No specific thresholds
❌ **Signal Bias Integration**: Fear/greed not used for signal bias
❌ **UI Display**: No fear/greed visualization in Streamlit

## 📊 Current Implementation Review

### **Existing Market Context (market_data_utils.py):**
```python
def calculate_market_regime_context(symbol: str, target_date: str, db_url: str) -> dict:
    # Calculate symbol-specific metrics
    volatility, recent_change = calculate_real_market_metrics(symbol, target_date, db_url)
    
    # Get VIX level
    vix_level = get_vix_level(target_date, db_url)
    
    # Determine market stress level
    vix_stress = "LOW" if vix_level < 20 else "MODERATE" if vix_level < 30 else "HIGH"
    
    # Determine volatility level
    if volatility > 5.0:
        vol_level = "HIGH"
    elif volatility > 2.5:
        vol_level = "MODERATE"
    else:
        vol_level = "LOW"
    
    return {
        'volatility': float(volatility),
        'recent_change': float(recent_change),
        'vix_level': float(vix_level),
        'vix_stress': vix_stress,
        'volatility_level': vol_level,
        'market_stress': bool(vix_stress == "HIGH" or volatility > 4.0)
    }
```

### **Current Usage:**
- **TQQQ Engine**: Uses `market_stress` for risk management
- **Generic Engine**: Uses market context for signal generation
- **Streamlit**: Displays VIX levels and market stress

## 🎯 Fear/Greed Engine Implementation Plan

### **Step 1: Define Fear/Greed States Quantitatively**

#### **🟥 FEAR (Buy Zone Candidate)**
```python
def is_fear_state(vix_level: float, volatility: float, price: float, sma20: float) -> bool:
    """
    Fear when:
    - VIX ≥ 22
    - AND volatility ≥ 6%
    - AND price < SMA20
    """
    return (vix_level >= 22.0 and 
            volatility >= 6.0 and 
            price < sma20)
```

#### **🟥 EXTREME FEAR (Capitulation)**
```python
def is_extreme_fear_state(vix_level: float, volatility: float, rsi: float) -> bool:
    """
    Extreme Fear when:
    - VIX ≥ 25
    - AND volatility ≥ 7.5%
    - AND RSI ≤ 40
    """
    return (vix_level >= 25.0 and 
            volatility >= 7.5 and 
            rsi <= 40.0)
```

#### **🟦 GREED (Sell Zone Candidate)**
```python
def is_greed_state(rsi: float, price: float, sma20: float) -> bool:
    """
    Greed when:
    - RSI ≥ 65
    - AND price > SMA20
    """
    return (rsi >= 65.0 and price > sma20)
```

#### **🟥 EXTREME GREED (Distribution)**
```python
def is_extreme_greed_state(rsi: float, volatility: float, volatility_trend: str) -> bool:
    """
    Extreme Greed when:
    - RSI ≥ 70
    - AND volatility rising
    """
    return (rsi >= 70.0 and volatility_trend == "rising")
```

### **Step 2: Create Fear/Greed Engine**

#### **New File: app/engines/fear_greed_engine.py**
```python
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

class FearGreedState(Enum):
    EXTREME_FEAR = "extreme_fear"
    FEAR = "fear"
    NEUTRAL = "neutral"
    GREED = "greed"
    EXTREME_GREED = "extreme_greed"

@dataclass
class FearGreedAnalysis:
    state: FearGreedState
    confidence: float
    vix_level: float
    volatility: float
    rsi: float
    price: float
    sma20: float
    reasoning: list
    signal_bias: str  # "bullish", "bearish", "neutral"

class FearGreedEngine:
    """
    Fear/Greed State Machine - Orthogonal to Regimes
    
    Instead of: Regime → Signal
    Use: Regime + Fear/Greed State → Signal Bias
    """
    
    def __init__(self):
        self.thresholds = {
            'vix_fear': 22.0,
            'vix_extreme_fear': 25.0,
            'volatility_fear': 6.0,
            'volatility_extreme_fear': 7.5,
            'rsi_extreme_fear': 40.0,
            'rsi_greed': 65.0,
            'rsi_extreme_greed': 70.0
        }
    
    def calculate_fear_greed_state(self, market_data: Dict) -> FearGreedAnalysis:
        """
        Calculate current fear/greed state and signal bias
        
        Args:
            market_data: {
                'vix_level': float,
                'volatility': float,
                'rsi': float,
                'price': float,
                'sma20': float,
                'volatility_trend': str  # 'rising', 'falling', 'stable'
            }
        """
        
        vix = market_data.get('vix_level', 20.0)
        vol = market_data.get('volatility', 2.0)
        rsi = market_data.get('rsi', 50.0)
        price = market_data.get('price', 0.0)
        sma20 = market_data.get('sma20', 0.0)
        vol_trend = market_data.get('volatility_trend', 'stable')
        
        reasoning = []
        
        # Check Extreme Fear first (most restrictive)
        if self._is_extreme_fear(vix, vol, rsi):
            state = FearGreedState.EXTREME_FEAR
            signal_bias = "strongly_bullish"  # Capitulation = buy opportunity
            confidence = 0.8
            reasoning.extend([
                f"Extreme Fear: VIX {vix:.1f} ≥ {self.thresholds['vix_extreme_fear']}",
                f"Extreme Fear: Volatility {vol:.1f}% ≥ {self.thresholds['volatility_extreme_fear']}%",
                f"Extreme Fear: RSI {rsi:.1f} ≤ {self.thresholds['rsi_extreme_fear']}"
            ])
        
        # Check Fear
        elif self._is_fear(vix, vol, price, sma20):
            state = FearGreedState.FEAR
            signal_bias = "bullish"  # Fear = buy opportunity
            confidence = 0.6
            reasoning.extend([
                f"Fear: VIX {vix:.1f} ≥ {self.thresholds['vix_fear']}",
                f"Fear: Volatility {vol:.1f}% ≥ {self.thresholds['volatility_fear']}%",
                f"Fear: Price ${price:.2f} < SMA20 ${sma20:.2f}"
            ])
        
        # Check Extreme Greed
        elif self._is_extreme_greed(rsi, vol, vol_trend):
            state = FearGreedState.EXTREME_GREED
            signal_bias = "strongly_bearish"  # Distribution = sell signal
            confidence = 0.8
            reasoning.extend([
                f"Extreme Greed: RSI {rsi:.1f} ≥ {self.thresholds['rsi_extreme_greed']}",
                f"Extreme Greed: Volatility {vol_trend}"
            ])
        
        # Check Greed
        elif self._is_greed(rsi, price, sma20):
            state = FearGreedState.GREED
            signal_bias = "bearish"  # Greed = sell opportunity
            confidence = 0.6
            reasoning.extend([
                f"Greed: RSI {rsi:.1f} ≥ {self.thresholds['rsi_greed']}",
                f"Greed: Price ${price:.2f} > SMA20 ${sma20:.2f}"
            ])
        
        # Neutral
        else:
            state = FearGreedState.NEUTRAL
            signal_bias = "neutral"
            confidence = 0.5
            reasoning.append("Neutral: No strong fear/greed signals")
        
        return FearGreedAnalysis(
            state=state,
            confidence=confidence,
            vix_level=vix,
            volatility=vol,
            rsi=rsi,
            price=price,
            sma20=sma20,
            reasoning=reasoning,
            signal_bias=signal_bias
        )
    
    def _is_extreme_fear(self, vix: float, vol: float, rsi: float) -> bool:
        return (vix >= self.thresholds['vix_extreme_fear'] and 
                vol >= self.thresholds['volatility_extreme_fear'] and 
                rsi <= self.thresholds['rsi_extreme_fear'])
    
    def _is_fear(self, vix: float, vol: float, price: float, sma20: float) -> bool:
        return (vix >= self.thresholds['vix_fear'] and 
                vol >= self.thresholds['volatility_fear'] and 
                price < sma20)
    
    def _is_extreme_greed(self, rsi: float, vol: float, vol_trend: str) -> bool:
        return (rsi >= self.thresholds['rsi_extreme_greed'] and 
                vol_trend == "rising")
    
    def _is_greed(self, rsi: float, price: float, sma20: float) -> bool:
        return (rsi >= self.thresholds['rsi_greed'] and price > sma20)
```

### **Step 3: Integrate with Signal Engines**

#### **Enhanced Market Conditions:**
```python
# In signal_calculator_core.py
@dataclass
class MarketConditions:
    # ... existing fields ...
    
    # NEW: Fear/Greed data
    fear_greed_state: Optional[str] = None
    fear_greed_bias: Optional[str] = None  # "bullish", "bearish", "neutral"
    fear_greed_confidence: Optional[float] = None
```

#### **Enhanced Signal Generation:**
```python
# In unified_tqqq_swing_engine.py
from app.engines.fear_greed_engine import FearGreedEngine

class UnifiedTQQQSwingEngine:
    def __init__(self, config: SignalConfig):
        # ... existing init ...
        self.fear_greed_engine = FearGreedEngine()
    
    def generate_signal(self, conditions: MarketConditions) -> SignalResult:
        # ... existing signal generation logic ...
        
        # NEW: Apply Fear/Greed bias
        if conditions.fear_greed_bias:
            final_signal = self._apply_fear_greed_bias(
                base_signal, conditions.fear_greed_bias, conditions.fear_greed_confidence
            )
            
            # Update reasoning
            result.signal = final_signal
            result.reasoning.extend([
                f"Fear/Greed State: {conditions.fear_greed_state}",
                f"Fear/Greed Bias: {conditions.fear_greed_bias}"
            ])
        
        return result
    
    def _apply_fear_greed_bias(self, base_signal: str, bias: str, confidence: float) -> str:
        """
        Apply fear/greed bias to base signal
        
        Logic:
        - Strong bullish bias + HOLD/SELL → BUY
        - Bearish bias + BUY/HOLD → SELL
        - Neutral bias → keep base signal
        """
        
        if bias == "strongly_bullish" and base_signal in ["HOLD", "SELL"]:
            return "BUY"
        elif bias == "bullish" and base_signal == "SELL":
            return "HOLD"
        elif bias == "strongly_bearish" and base_signal in ["BUY", "HOLD"]:
            return "SELL"
        elif bias == "bearish" and base_signal == "BUY":
            return "HOLD"
        else:
            return base_signal  # Keep original signal
```

### **Step 4: API Integration**

#### **Enhanced TQQQ API:**
```python
# In tqqq_engine_api.py
from app.engines.fear_greed_engine import FearGreedEngine

@router.post("/signal/tqqq", response_model=TQQQSignalResponse)
async def generate_tqqq_signal(request: TQQQSignalRequest):
    # ... existing code ...
    
    # NEW: Calculate Fear/Greed state
    fear_greed_engine = FearGreedEngine()
    
    # Prepare market data for fear/greed analysis
    fear_greed_data = {
        'vix_level': market_context['vix_level'],
        'volatility': market_context['volatility'],
        'rsi': row['rsi_14'],
        'price': row['close'],
        'sma20': row['ema_20'],
        'volatility_trend': 'rising'  # TODO: Calculate actual trend
    }
    
    fear_greed_analysis = fear_greed_engine.calculate_fear_greed_state(fear_greed_data)
    
    # Add to response
    response_data['fear_greed'] = {
        'state': fear_greed_analysis.state.value,
        'bias': fear_greed_analysis.signal_bias,
        'confidence': fear_greed_analysis.confidence,
        'reasoning': fear_greed_analysis.reasoning
    }
    
    # ... existing code ...
```

### **Step 5: Streamlit UI Integration**

#### **New Fear/Greed Display Component:**
```python
# In streamlit-app/pages/9_Trading_Dashboard.py

def display_fear_greed_analysis(fear_greed_data: dict):
    """Display fear/greed analysis in UI"""
    
    st.markdown("### 🎭 Fear & Greed Analysis")
    
    state = fear_greed_data.get('state', 'neutral')
    bias = fear_greed_data.get('bias', 'neutral')
    confidence = fear_greed_data.get('confidence', 0.5)
    
    # State indicator
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Color-coded state display
        if state == 'extreme_fear':
            st.error("🟥 EXTREME FEAR")
        elif state == 'fear':
            st.warning("🟨 FEAR")
        elif state == 'greed':
            st.info("🟩 GREED")
        elif state == 'extreme_greed':
            st.error("🟥 EXTREME GREED")
        else:
            st.info("⚪ NEUTRAL")
    
    with col2:
        st.metric("Signal Bias", bias.upper())
    
    with col3:
        st.metric("Confidence", f"{confidence:.1%}")
    
    # Reasoning
    if 'reasoning' in fear_greed_data:
        st.markdown("**Analysis:**")
        for reason in fear_greed_data['reasoning']:
            st.write(f"• {reason}")
    
    # Visual gauge (optional)
    st.markdown("**Fear/Greed Gauge:**")
    fear_greed_gauge(state)

def fear_greed_gauge(state: str):
    """Create a visual fear/greed gauge"""
    # Simple text-based gauge for now
    gauge_states = {
        'extreme_fear': "🟥🟥🟥🟥🟥⚪⚪⚪⚪⚪",
        'fear': "🟥🟥🟥🟥⚪⚪⚪⚪⚪⚪",
        'neutral': "🟥🟥🟥⚪⚪⚪⚪🟩🟩🟩",
        'greed': "⚪⚪⚪⚪⚪⚪🟩🟩🟩🟩",
        'extreme_greed': "⚪⚪⚪⚪⚪⚪⚪⚪🟥🟥"
    }
    
    st.markdown(gauge_states.get(state, "⚪⚪⚪⚪⚪⚪⚪⚪⚪⚪"))
```

### **Step 6: Volatility Trend Calculation**

#### **Enhanced Market Data Utils:**
```python
# In market_data_utils.py

def calculate_volatility_trend(symbol: str, target_date: str, db_url: str) -> str:
    """
    Calculate if volatility is rising, falling, or stable
    
    Returns: 'rising', 'falling', 'stable'
    """
    
    try:
        conn = psycopg2.connect(db_url)
        
        # Get 14 days of volatility data
        query = """
            SELECT date, close
            FROM raw_market_data_daily 
            WHERE symbol = %s 
            AND date <= %s::date
            ORDER BY date DESC
            LIMIT 14
        """
        
        df = pd.read_sql(query, conn, params=(symbol, target_date))
        conn.close()
        
        if len(df) < 7:
            return "stable"
        
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # Calculate rolling volatility
        df['daily_return'] = df['close'].pct_change()
        df['rolling_vol'] = df['daily_return'].rolling(window=5).std() * 100
        
        # Compare recent vs older volatility
        recent_vol = df['rolling_vol'].iloc[-3:].mean()
        older_vol = df['rolling_vol'].iloc[-7:-3].mean()
        
        vol_change = (recent_vol - older_vol) / older_vol
        
        if vol_change > 0.1:  # 10% increase
            return "rising"
        elif vol_change < -0.1:  # 10% decrease
            return "falling"
        else:
            return "stable"
        
    except Exception as e:
        print(f"Error calculating volatility trend: {e}")
        return "stable"
```

## 🚀 Implementation Timeline

### **Phase 1: Core Engine (2-3 days)**
1. Create `fear_greed_engine.py`
2. Implement state detection logic
3. Add comprehensive tests

### **Phase 2: Integration (2-3 days)**
1. Enhance `MarketConditions` dataclass
2. Update signal engines to use fear/greed bias
3. Modify API responses

### **Phase 3: UI & Visualization (1-2 days)**
1. Add Streamlit components
2. Create fear/greed gauge
3. Add to existing dashboards

### **Phase 4: Testing & Validation (1-2 days)**
1. Test with historical data
2. Validate signal improvements
3. Performance analysis

## 📊 Expected Benefits

### **Signal Quality Improvements:**
- **Better Entry Points**: Fear states identify buying opportunities
- **Better Exit Points**: Greed states identify selling opportunities
- **Reduced False Signals**: Bias confirmation reduces noise

### **Risk Management:**
- **Contrarian Signals**: Buy when others are fearful
- **Profit Taking**: Sell when others are greedy
- **Regime Awareness**: Combines with market regimes for better context

### **User Experience:**
- **Intuitive Display**: Easy-to-understand fear/greed states
- **Professional Analysis**: Institutional-grade market psychology
- **Actionable Insights**: Clear bias recommendations

## ✅ Summary

**Current State**: We have basic VIX and volatility analysis but no formal fear/greed engine.

**Implementation**: Add a comprehensive fear/greed state machine that works alongside existing regimes.

**Key Innovation**: Use `Regime + Fear/Greed State → Signal Bias` instead of just `Regime → Signal`.

**Timeline**: 6-10 days total for full implementation with testing.

**Impact**: Significant improvement in signal quality and user experience.

This implementation will bring our system closer to how discretionary professional traders actually operate - using both technical regimes AND market psychology! 🎯
