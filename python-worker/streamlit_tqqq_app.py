import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
from datetime import datetime, timedelta

# Configuration
st.set_page_config(
    page_title="TQQQ Signal Engine",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Configuration
API_BASE_URL = "http://127.0.0.1:8001"

def get_signal_analysis(symbol="TQQQ", date=None, include_historical=True, include_performance=True):
    """Get signal analysis from API"""
    try:
        payload = {
            "symbol": symbol,
            "date": date,
            "include_historical": include_historical,
            "include_performance": include_performance
        }
        
        response = requests.post(f"{API_BASE_URL}/api/streamlit/signal-analysis", json=payload)
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        st.error(f"Error connecting to API: {e}")
        return None

def create_price_chart(historical_data):
    """Create price chart with technical indicators"""
    if not historical_data:
        return None
    
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=('Price & Moving Averages', 'RSI', 'Volume'),
        row_heights=[0.6, 0.2, 0.2]
    )
    
    # Price and Moving Averages
    fig.add_trace(
        go.Scatter(
            x=historical_data['dates'],
            y=historical_data['prices'],
            name='Price',
            line=dict(color='blue', width=2)
        ),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=historical_data['dates'],
            y=historical_data['sma20'],
            name='SMA20',
            line=dict(color='orange', width=1)
        ),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=historical_data['dates'],
            y=historical_data['sma50'],
            name='SMA50',
            line=dict(color='red', width=1)
        ),
        row=1, col=1
    )
    
    # RSI
    fig.add_trace(
        go.Scatter(
            x=historical_data['dates'],
            y=historical_data['rsi'],
            name='RSI',
            line=dict(color='purple', width=2)
        ),
        row=2, col=1
    )
    
    # Add RSI overbought/oversold lines
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
    
    # Volume
    fig.add_trace(
        go.Bar(
            x=historical_data['dates'],
            y=historical_data['volume'],
            name='Volume',
            marker_color='lightblue'
        ),
        row=3, col=1
    )
    
    fig.update_layout(
        title='TQQQ Technical Analysis',
        height=800,
        showlegend=True
    )
    
    return fig

def main():
    st.title("📈 TQQQ Signal Engine")
    st.markdown("Real-time market intelligence and trading signals")
    
    # Sidebar
    st.sidebar.title("📊 Analysis Settings")
    
    # Symbol selection
    symbol = st.sidebar.selectbox("Symbol", ["TQQQ"], index=0)
    
    # Date selection
    analysis_type = st.sidebar.radio("Analysis Type", ["Latest", "Specific Date"])
    
    if analysis_type == "Specific Date":
        selected_date = st.sidebar.date_input(
            "Select Date",
            value=datetime.now().date() - timedelta(days=1),
            max_value=datetime.now().date()
        )
        date_str = selected_date.strftime("%Y-%m-%d")
    else:
        date_str = None
    
    # Data options
    include_historical = st.sidebar.checkbox("Include Historical Data", value=True)
    include_performance = st.sidebar.checkbox("Include Performance Stats", value=True)
    
    # Refresh button
    if st.sidebar.button("🔄 Refresh Analysis"):
        st.rerun()
    
    # Get signal analysis
    with st.spinner("Analyzing market data..."):
        analysis_data = get_signal_analysis(
            symbol=symbol,
            date=date_str,
            include_historical=include_historical,
            include_performance=include_performance
        )
    
    if not analysis_data or not analysis_data.get('success'):
        st.error("Failed to get signal analysis. Please check API connection.")
        return
    
    data = analysis_data['data']
    
    # Main Signal Summary
    st.header("🎯 Signal Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    
    signal = data['signal_summary']
    signal_color = {
        'BUY': 'green',
        'SELL': 'red',
        'HOLD': 'orange'
    }.get(signal['signal'], 'gray')
    
    with col1:
        st.metric(
            "Signal",
            signal['signal'],
            delta=None,
            delta_color="normal"
        )
        st.markdown(f"**Confidence:** {signal['confidence_percent']}%")
    
    with col2:
        st.metric(
            "Price",
            f"${signal['price']}",
            delta=f"{signal['daily_change']:+.2f}%",
            delta_color="normal"
        )
    
    with col3:
        st.metric(
            "Regime",
            signal['regime'],
            delta=None,
            delta_color="normal"
        )
    
    with col4:
        risk_level = data['risk_assessment']['risk_level']
        risk_color = {
            'LOW': 'green',
            'MODERATE': 'orange',
            'HIGH': 'red'
        }.get(risk_level, 'gray')
        
        st.markdown(f"**Risk Level:**")
        st.markdown(f"<span style='color: {risk_color}; font-weight: bold;'>{risk_level}</span>", unsafe_allow_html=True)
    
    # Signal Reasoning
    st.subheader("🧠 Engine Reasoning")
    for reason in signal['reasoning']:
        st.write(f"• {reason}")
    
    # Market Overview
    st.header("📈 Market Overview")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Volume", data['market_overview']['volume_formatted'])
        st.metric("Volatility", f"{data['market_overview']['volatility']}%")
    
    with col2:
        st.metric("RSI", f"{data['technical_indicators']['rsi']}")
        st.metric("RSI Status", data['technical_indicators']['rsi_status'])
    
    with col3:
        st.metric("Trend", data['technical_indicators']['trend'])
        st.metric("Price vs SMA20", data['technical_indicators']['price_vs_sma20'])
    
    # Trading Plan
    st.header("🎯 Trading Plan")
    
    plan = data['trading_plan']
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Action", plan['action'])
        st.metric("Entry Price", f"${plan['entry_price']}")
    
    with col2:
        st.metric("Target Return", plan['target_return'])
        st.metric("Stop Loss", plan['stop_loss'])
    
    with col3:
        st.metric("Hold Time", plan['hold_time'])
        st.metric("Risk/Reward", plan['risk_reward'])
    
    # Key Levels
    st.header("🔍 Key Levels")
    
    levels = data['key_levels']
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Resistance", f"${levels['resistance']}")
    
    with col2:
        st.metric("Support", f"${levels['support']}")
    
    with col3:
        st.metric("SMA20", f"${levels['sma20']}")
    
    with col4:
        st.metric("SMA50", f"${levels['sma50']}")
    
    # Historical Chart
    if include_historical and 'historical_data' in data:
        st.header("📊 Technical Chart")
        
        fig = create_price_chart(data['historical_data'])
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    
    # Performance Statistics
    if include_performance and 'historical_performance' in data:
        st.header("📊 Performance Statistics")
        
        perf = data['historical_performance']
        
        # Overall Performance
        st.subheader("Overall Performance (2025)")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            buy_data = perf['buy_signals']
            st.metric("BUY Signals", buy_data['count'])
            st.metric("Avg Return", f"{buy_data['avg_return']:+.2%}")
            st.metric("Win Rate", f"{buy_data['win_rate']:.1f}%")
            st.metric("Success Rate", buy_data['success_rate'])
        
        with col2:
            sell_data = perf['sell_signals']
            st.metric("SELL Signals", sell_data['count'])
            st.metric("Avg Return", f"{sell_data['avg_return']:+.2%}")
            st.metric("Win Rate", f"{sell_data['win_rate']:.1f}%")
            st.metric("Success Rate", sell_data['success_rate'])
        
        with col3:
            hold_data = perf['hold_signals']
            st.metric("HOLD Signals", hold_data['count'])
            st.metric("Avg Return", f"{hold_data['avg_return']:+.2%}")
            st.metric("Win Rate", f"{hold_data['win_rate']:.1f}%")
            st.metric("Success Rate", hold_data['success_rate'])
        
        # Current Regime Performance
        if 'current_regime' in perf:
            st.subheader(f"Current Regime Performance ({perf['current_regime']['name']})")
            
            regime_data = perf['current_regime']
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("BUY Signals", regime_data['buy_signals'])
            
            with col2:
                st.metric("Avg Return", f"{regime_data['avg_return']:+.2%}")
            
            with col3:
                st.metric("Win Rate", f"{regime_data['win_rate']:.1f}%")
        
        # Recent Performance
        if 'recent_performance' in perf:
            st.subheader("Recent Performance")
            
            recent_data = perf['recent_performance']
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Period", recent_data['period'])
            
            with col2:
                st.metric("BUY Signals", recent_data['buy_signals'])
            
            with col3:
                st.metric("Win Rate", f"{recent_data['win_rate']:.1f}%")
    
    # Regime Information
    st.header("📋 Regime Information")
    
    regime_info = data['regime_info']
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader(regime_info['name'])
        st.write(regime_info['description'])
    
    with col2:
        st.subheader("Trading Focus")
        st.write(f"**Focus:** {regime_info['focus']}")
        st.write(f"**Best For:** {regime_info['best_for']}")
    
    # Risk Assessment
    st.header("⚠️ Risk Assessment")
    
    risk = data['risk_assessment']
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        risk_color = {
            'LOW': 'green',
            'MODERATE': 'orange',
            'HIGH': 'red'
        }.get(risk['risk_level'], 'gray')
        
        st.markdown(f"**Risk Level:**")
        st.markdown(f"<span style='color: {risk_color}; font-weight: bold; font-size: 1.5em;'>{risk['risk_level']}</span>", unsafe_allow_html=True)
    
    with col2:
        st.metric("Volatility", f"{risk['volatility']}%")
        st.metric("Status", risk['volatility_status'])
    
    with col3:
        st.metric("Position Size", risk['suggested_position'])
    
    # Footer
    st.markdown("---")
    st.markdown("⚠️ **Disclaimer:** This analysis is for educational purposes only. Always do your own research before trading.")
    st.markdown(f"📅 Last Updated: {data['timestamp']}")

if __name__ == "__main__":
    main()
