# 🎯 TQQQ Signal Engine - Streamlit API Guide

## 📋 Overview

The TQQQ Signal Engine provides a comprehensive API specifically designed for Streamlit integration. This API delivers real-time market analysis, trading signals, and performance metrics in a user-friendly JSON format.

## 🚀 Quick Start

### 1. API Endpoint
```
POST http://127.0.0.1:8001/api/streamlit/signal-analysis
```

### 2. Basic Usage
```python
import requests

# Get latest signal analysis
response = requests.post(
    'http://127.0.0.1:8001/api/streamlit/signal-analysis',
    json={
        'symbol': 'TQQQ',
        'include_historical': True,
        'include_performance': True
    }
)

if response.status_code == 200:
    data = response.json()
    signal = data['data']['signal_summary']
    print(f"Signal: {signal['signal']}")
    print(f"Confidence: {signal['confidence_percent']}%")
```

## 📊 Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `symbol` | string | No | "TQQQ" | Stock symbol to analyze |
| `date` | string | No | null | Specific date (YYYY-MM-DD), null for latest |
| `include_historical` | boolean | No | true | Include historical chart data |
| `include_performance` | boolean | No | true | Include performance statistics |

## 📋 Response Structure

### Signal Summary
```json
{
  "signal_summary": {
    "signal": "BUY|SELL|HOLD",
    "confidence": 0.75,
    "confidence_percent": 75,
    "regime": "Mean Reversion",
    "price": 52.72,
    "daily_change": 2.5,
    "reasoning": ["Oversold stabilization", "RSI oversold: 37.0"]
  }
}
```

### Market Overview
```json
{
  "market_overview": {
    "price": 52.72,
    "daily_change": 2.5,
    "daily_change_percent": "+2.50%",
    "volume": 57199400,
    "volume_formatted": "57,199,400",
    "volatility": 2.6,
    "volatility_status": "Low"
  }
}
```

### Technical Indicators
```json
{
  "technical_indicators": {
    "rsi": 37.0,
    "rsi_status": "OVERSOLD",
    "sma20": 67.60,
    "sma50": 68.04,
    "trend": "DOWNTREND",
    "price_vs_sma20": "BELOW",
    "price_vs_sma50": "BELOW",
    "macd": -0.123,
    "macd_signal": -0.456,
    "macd_histogram": 0.333
  }
}
```

### Risk Assessment
```json
{
  "risk_assessment": {
    "risk_level": "LOW|MODERATE|HIGH",
    "risk_color": "green|orange|red",
    "volatility": 2.6,
    "suggested_position": "LARGE (75%)",
    "position_size_percent": 75
  }
}
```

### Trading Plan
```json
{
  "trading_plan": {
    "action": "BUY|SELL|HOLD",
    "entry_price": 52.72,
    "target_return": "+5-10%",
    "stop_loss": "-3-5%",
    "hold_time": "3-7 days",
    "risk_reward": "1:2 to 1:3"
  }
}
```

### Key Levels
```json
{
  "key_levels": {
    "resistance": 54.20,
    "support": 52.64,
    "sma20": 67.60,
    "sma50": 68.04,
    "current_price": 52.72,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "current_rsi": 37.0
  }
}
```

### Historical Data (for charts)
```json
{
  "historical_data": {
    "dates": ["2025-01-01", "2025-01-02", ...],
    "prices": [45.20, 46.10, ...],
    "rsi": [42.0, 44.5, ...],
    "sma20": [44.80, 45.20, ...],
    "sma50": [46.10, 46.30, ...],
    "volume": [50000000, 52000000, ...],
    "high": [46.50, 47.20, ...],
    "low": [44.20, 45.80, ...]
  }
}
```

### Historical Performance
```json
{
  "historical_performance": {
    "total_signals": 202,
    "buy_signals": {
      "count": 61,
      "avg_return": 0.0294,
      "win_rate": 65.6,
      "success_rate": "Good"
    },
    "sell_signals": {
      "count": 33,
      "avg_return": -0.0626,
      "win_rate": 36.4,
      "success_rate": "Fair"
    },
    "current_regime": {
      "name": "mean_reversion",
      "buy_signals": 58,
      "avg_return": 0.0278,
      "win_rate": 63.8
    },
    "recent_performance": {
      "period": "Last 30 signals",
      "buy_signals": 8,
      "avg_return": 0.0312,
      "win_rate": 62.5
    }
  }
}
```

## 🎨 Streamlit Integration Examples

### 1. Basic Signal Display
```python
import streamlit as st
import requests

def get_signal_analysis():
    response = requests.post(
        'http://127.0.0.1:8001/api/streamlit/signal-analysis',
        json={'symbol': 'TQQQ'}
    )
    
    if response.status_code == 200:
        return response.json()
    return None

# Main app
data = get_signal_analysis()
if data and data['success']:
    signal = data['data']['signal_summary']
    
    # Display signal
    st.metric("Signal", signal['signal'])
    st.metric("Confidence", f"{signal['confidence_percent']}%")
    st.metric("Price", f"${signal['price']}")
```

### 2. Advanced Dashboard
```python
import streamlit as st
import requests
import plotly.graph_objects as go

def create_dashboard():
    data = get_signal_analysis()
    
    if not data or not data['success']:
        st.error("Failed to get signal data")
        return
    
    result = data['data']
    
    # Signal Summary
    col1, col2, col3 = st.columns(3)
    
    with col1:
        signal = result['signal_summary']
        st.metric("Signal", signal['signal'])
        st.metric("Confidence", f"{signal['confidence_percent']}%")
    
    with col2:
        market = result['market_overview']
        st.metric("Price", f"${market['price']}")
        st.metric("Change", market['daily_change_percent'])
    
    with col3:
        risk = result['risk_assessment']
        st.metric("Risk Level", risk['risk_level'])
        st.metric("Position Size", risk['suggested_position'])
    
    # Technical Chart
    if 'historical_data' in result:
        fig = go.Figure()
        hist = result['historical_data']
        
        fig.add_trace(go.Scatter(
            x=hist['dates'],
            y=hist['prices'],
            name='Price'
        ))
        
        fig.add_trace(go.Scatter(
            x=hist['dates'],
            y=hist['sma20'],
            name='SMA20'
        ))
        
        st.plotly_chart(fig, use_container_width=True)
```

### 3. Real-time Updates
```python
import streamlit as st
import time

def auto_refresh_dashboard():
    # Auto-refresh every 5 minutes
    refresh_interval = 300
    
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = 0
    
    current_time = time.time()
    
    if current_time - st.session_state.last_refresh > refresh_interval:
        st.session_state.last_refresh = current_time
        st.rerun()
    
    # Display data
    data = get_signal_analysis()
    # ... rest of dashboard code
```

## 🔧 Error Handling

```python
import streamlit as st
import requests

def safe_api_call():
    try:
        response = requests.post(
            'http://127.0.0.1:8001/api/streamlit/signal-analysis',
            json={'symbol': 'TQQQ'},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                return data
            else:
                st.error(f"API Error: {data.get('error')}")
        else:
            st.error(f"HTTP Error: {response.status_code}")
            
    except requests.exceptions.Timeout:
        st.error("Request timed out")
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to API")
    except Exception as e:
        st.error(f"Unexpected error: {e}")
    
    return None
```

## 📱 Mobile-Friendly Design

```python
import streamlit as st

def mobile_friendly_dashboard():
    # Use columns for mobile layout
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Signal", signal['signal'])
        st.metric("Price", f"${signal['price']}")
    
    with col2:
        st.metric("Confidence", f"{signal['confidence_percent']}%")
        st.metric("Risk", risk['risk_level'])
    
    # Expandable sections for mobile
    with st.expander("📊 Technical Details"):
        st.write(technical_indicators)
    
    with st.expander("📈 Performance History"):
        st.write(historical_performance)
```

## 🚀 Deployment Tips

### 1. Environment Configuration
```python
import os

# API URL configuration
API_BASE_URL = os.getenv('API_BASE_URL', 'http://127.0.0.1:8001')
```

### 2. Caching
```python
import streamlit as st

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_cached_signal_analysis(symbol):
    response = requests.post(
        f'{API_BASE_URL}/api/streamlit/signal-analysis',
        json={'symbol': symbol}
    )
    return response.json()
```

### 3. Loading States
```python
def get_signal_with_loading():
    with st.spinner("Analyzing market data..."):
        data = get_signal_analysis()
    return data
```

## 🎯 Best Practices

1. **Error Handling**: Always check API responses and handle errors gracefully
2. **Caching**: Use Streamlit caching to reduce API calls
3. **Loading States**: Show spinners during API calls
4. **Mobile Design**: Use responsive layouts for mobile users
5. **Auto-refresh**: Implement periodic updates for real-time data
6. **User Feedback**: Provide clear error messages and loading indicators

## 📞 Support

For API issues or questions:
- Check API health: `GET http://127.0.0.1:8001/health`
- View API docs: `http://127.0.0.1:8001/docs`
- Test with: `python test_streamlit_api.py`

---

🎉 **Your Streamlit app is ready to use the TQQQ Signal Engine API!**
