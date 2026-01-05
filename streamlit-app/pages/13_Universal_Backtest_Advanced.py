#!/usr/bin/env python3
"""
Universal Backtest Dashboard
Advanced backtesting for any asset type using the Universal API
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import json

from utils import setup_page_config, render_sidebar

# Page setup
setup_page_config()
st.title("🚀 Universal Backtest Dashboard")
st.markdown("*Advanced backtesting for any asset type (3x ETFs, Regular ETFs, Stocks)*")

# Sidebar
render_sidebar()

# Asset type selection
st.sidebar.header("Asset Configuration")

asset_type_options = {
    "3x ETF": "3x_etf",
    "Regular ETF": "regular_etf", 
    "Stock": "stock"
}

selected_asset_type_name = st.sidebar.selectbox(
    "Select Asset Type",
    list(asset_type_options.keys()),
    index=0
)

selected_asset_type = asset_type_options[selected_asset_type_name]

# Symbol input with suggestions
st.sidebar.subheader(f"{selected_asset_type_name} Symbol")

# Popular symbols for each asset type
symbol_suggestions = {
    "3x_etf": ["TQQQ", "SOXL", "FNGU", "TECL", "WEBL"],
    "regular_etf": ["QQQ", "SPY", "IWM", "VTI", "GLD"],
    "stock": ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]
}

suggestions = symbol_suggestions.get(selected_asset_type, [])

# Custom symbol input with suggestions
symbol_input = st.sidebar.text_input(
    f"Enter {selected_asset_type_name} Symbol",
    value=suggestions[0] if suggestions else "",
    placeholder=f"e.g., {suggestions[0] if suggestions else 'TQQQ'}"
)

# Show suggestions if available
if suggestions:
    st.sidebar.markdown("**Popular symbols:**")
    cols = st.sidebar.columns(len(suggestions))
    for i, suggestion in enumerate(suggestions):
        if cols[i].button(suggestion, key=f"suggest_{suggestion}_{selected_asset_type}"):
            symbol_input = suggestion
            st.rerun()

# Date selection
st.sidebar.subheader("Date Selection")

# Default to most recent trading day
default_date = datetime.now().date() - timedelta(days=1)
selected_date = st.sidebar.date_input(
    "Select Date",
    value=default_date,
    max_value=datetime.now().date() - timedelta(days=1)
)

# Date range for backtesting
st.sidebar.subheader("Backtest Period")
backtest_days = st.sidebar.slider(
    "Backtest Period (Days)",
    min_value=30,
    max_value=365,
    value=90,
    step=30
)

# Calculate date range
end_date = selected_date
start_date = end_date - timedelta(days=backtest_days)

# Main content area
col1, col2 = st.columns([2, 1])

with col1:
    st.header(f"{selected_asset_type_name} Analysis")
    
    # Current signal section
    st.subheader(f"📊 Current Signal for {symbol_input}")
    
    # Get current signal
    def get_universal_signal(symbol, date, asset_type):
        """Get signal for any asset using universal API"""
        try:
            api_url = "http://127.0.0.1:8001/api/v1/universal/signal/universal"
            payload = {
                "symbol": symbol,
                "date": date.strftime("%Y-%m-%d"),
                "asset_type": asset_type
            }
            
            response = requests.post(api_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data["data"]
                else:
                    return {"error": data.get("error", "Unknown error")}
            else:
                return {"error": f"API Error: {response.status_code} - {response.text}"}
        except Exception as e:
            return {"error": f"Request failed: {str(e)}"}

with col2:
    st.header("Asset Info")
    
    # Asset type information
    asset_info = {
        "3x ETF": {
            "description": "3x leveraged ETFs with high volatility",
            "risk": "Very High",
            "holding_period": "Short-term (1-5 days)",
            "examples": "TQQQ, SOXL, FNGU"
        },
        "Regular ETF": {
            "description": "Standard ETFs with moderate volatility",
            "risk": "Medium",
            "holding_period": "Medium-term (1-4 weeks)",
            "examples": "QQQ, SPY, IWM"
        },
        "Stock": {
            "description": "Individual stocks with varying volatility",
            "risk": "Variable",
            "holding_period": "Depends on stock",
            "examples": "AAPL, MSFT, NVDA"
        }
    }
    
    info = asset_info.get(selected_asset_type_name, {})
    
    st.markdown(f"**Type:** {selected_asset_type_name}")
    st.markdown(f"**Risk Level:** {info.get('risk', 'N/A')}")
    st.markdown(f"**Holding Period:** {info.get('holding_period', 'N/A')}")
    st.markdown(f"**Examples:** {info.get('examples', 'N/A')}")
    
    st.markdown("---")
    st.markdown(f"**Description:**")
    st.markdown(info.get('description', 'N/A'))

# Get and display current signal
signal_data = get_universal_signal(symbol_input, selected_date, selected_asset_type)

if "error" in signal_data:
    st.error(f"❌ {signal_data['error']}")
    st.stop()

# Display signal information
signal = signal_data.get("signal", {})
market_data = signal_data.get("market_data", {})
analysis = signal_data.get("analysis", {})

# Signal display with color coding
signal_value = signal.get("signal", "hold").upper()
confidence = signal.get("confidence", 0.0)

# Color mapping for signals
signal_colors = {
    "BUY": "🟢",
    "SELL": "🔴", 
    "HOLD": "🟡"
}

signal_color = signal_colors.get(signal_value, "⚪")

st.markdown(f"### {signal_color} **{signal_value}** Signal")
st.markdown(f"**Confidence:** {confidence:.1%}")

# Signal reasoning
reasoning = signal.get("reasoning", [])
if reasoning:
    st.markdown("**Reasoning:**")
    for reason in reasoning:
        st.markdown(f"• {reason}")

# Market data display
st.markdown("---")
st.subheader("📈 Market Data")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Current Price", f"${market_data.get('price', 0):.2f}")
with col2:
    st.metric("RSI", f"{market_data.get('rsi', 0):.1f}")
with col3:
    st.metric("SMA 20", f"${market_data.get('sma_20', 0):.2f}")
with col4:
    st.metric("SMA 50", f"${market_data.get('sma_50', 0):.2f}")

# Fear/Greed analysis
metadata = signal.get("metadata", {})
st.markdown("---")
st.subheader("🧠 Fear/Greed Analysis")

fg_state = metadata.get("fear_greed_state", "neutral")
fg_bias = metadata.get("fear_greed_bias", "neutral")
recovery = metadata.get("recovery_detected", False)

# Fear/Greed color coding
fg_colors = {
    "extreme_fear": "🔴",
    "fear": "🟠",
    "neutral": "🟡",
    "greed": "🟢",
    "extreme_greed": "🟢"
}

fg_color = fg_colors.get(fg_state, "⚪")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(f"**State:** {fg_color} {fg_state.replace('_', ' ').title()}")
with col2:
    st.markdown(f"**Bias:** {fg_bias.title()}")
with col3:
    recovery_icon = "✅" if recovery else "❌"
    st.markdown(f"**Recovery:** {recovery_icon} {'Detected' if recovery else 'Not Detected'}")

# Market analysis
st.markdown("---")
st.subheader("📊 Market Analysis")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Volatility Metrics:**")
    st.markdown(f"• Daily Volatility: {analysis.get('real_volatility', '0.00%')}")
    st.markdown(f"• Recent Change: {analysis.get('recent_change', '0.00%')}")
    st.markdown(f"• Intraday Range: {analysis.get('daily_range', '0.00 - 0.00')}")

with col2:
    st.markdown("**Market Conditions:**")
    vix_level = analysis.get('vix_level', 0)
    market_stress = analysis.get('market_stress', False)
    stress_icon = "⚠️" if market_stress else "✅"
    st.markdown(f"• VIX Level: {vix_level:.2f}")
    st.markdown(f"• Market Stress: {stress_icon} {'High' if market_stress else 'Normal'}")
    st.markdown(f"• Volatility Level: {analysis.get('volatility_level', 'NORMAL')}")

# Historical data and backtesting
st.markdown("---")
st.subheader(f"📊 Historical Data & Backtesting ({backtest_days} days)")

def get_historical_data(symbol, start_date, end_date):
    """Get historical data for backtesting"""
    try:
        api_url = f"http://127.0.0.1:8001/api/v1/universal/historical-data/{symbol}"
        params = {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "limit": backtest_days
        }
        
        response = requests.get(api_url, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return data["data"]["historical_data"]
            else:
                return []
        else:
            return []
    except Exception as e:
        return []

# Get historical data
historical_data = get_historical_data(symbol_input, start_date, end_date)

if not historical_data:
    st.warning("⚠️ No historical data available for the selected period")
else:
    # Convert to DataFrame
    df = pd.DataFrame(historical_data)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    # Display data summary
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Records", len(df))
    with col2:
        price_change = (df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0] * 100
        st.metric("Period Return", f"{price_change:.2f}%")
    with col3:
        volatility = df['close'].pct_change().std() * 100
        st.metric("Period Volatility", f"{volatility:.2f}%")
    
    # Price chart
    st.markdown("**Price Chart:**")
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=(f'{symbol_input} Price', 'Volume'),
        row_width=[0.2, 0.7]
    )
    
    # Price candlestick
    fig.add_trace(
        go.Candlestick(
            x=df['date'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Price'
        ),
        row=1, col=1
    )
    
    # Moving averages
    if len(df) >= 20:
        df['sma_20'] = df['close'].rolling(window=20).mean()
        fig.add_trace(
            go.Scatter(
                x=df['date'],
                y=df['sma_20'],
                mode='lines',
                name='SMA 20',
                line=dict(color='blue', width=1)
            ),
            row=1, col=1
        )
    
    if len(df) >= 50:
        df['sma_50'] = df['close'].rolling(window=50).mean()
        fig.add_trace(
            go.Scatter(
                x=df['date'],
                y=df['sma_50'],
                mode='lines',
                name='SMA 50',
                line=dict(color='red', width=1)
            ),
            row=1, col=1
        )
    
    # Volume
    fig.add_trace(
        go.Bar(
            x=df['date'],
            y=df['volume'],
            name='Volume',
            marker_color='rgba(158,158,158,0.5)'
        ),
        row=2, col=1
    )
    
    # Update layout
    fig.update_layout(
        title=f'{symbol_input} ({selected_asset_type_name}) - {backtest_days} Day Chart',
        yaxis_title='Price ($)',
        xaxis_rangeslider_visible=False,
        height=600,
        showlegend=True
    )
    
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Signal backtesting simulation
    st.markdown("---")
    st.subheader("🎯 Signal Backtest Simulation")
    
    # Generate signals for historical period
    def generate_backtest_signals(symbol, dates, asset_type):
        """Generate signals for backtesting"""
        signals = []
        
        for date in dates:
            signal_data = get_universal_signal(symbol, date, asset_type)
            if "error" not in signal_data:
                signal_info = signal_data.get("signal", {})
                signals.append({
                    "date": date,
                    "signal": signal_info.get("signal", "hold"),
                    "confidence": signal_info.get("confidence", 0.0),
                    "price": signal_data.get("market_data", {}).get("price", 0.0)
                })
        
        return signals
    
    # Generate signals for sample dates (every 5 days to reduce API calls)
    sample_dates = [start_date + timedelta(days=i*5) for i in range(backtest_days//5)]
    backtest_signals = generate_backtest_signals(symbol_input, sample_dates, selected_asset_type)
    
    if backtest_signals:
        # Create backtest DataFrame
        backtest_df = pd.DataFrame(backtest_signals)
        backtest_df['date'] = pd.to_datetime(backtest_df['date'])
        
        # Calculate performance
        initial_price = backtest_df['price'].iloc[0]
        final_price = backtest_df['price'].iloc[-1]
        
        # Simple buy/hold simulation
        buy_signals = backtest_df[backtest_df['signal'] == 'buy']
        sell_signals = backtest_df[backtest_df['signal'] == 'sell']
        
        st.markdown(f"**Signal Summary ({len(backtest_signals)} signals generated):**")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Buy Signals", len(buy_signals))
        with col2:
            st.metric("Sell Signals", len(sell_signals))
        with col3:
            hold_signals = len(backtest_df[backtest_df['signal'] == 'hold'])
            st.metric("Hold Signals", hold_signals)
        with col4:
            avg_confidence = backtest_df['confidence'].mean()
            st.metric("Avg Confidence", f"{avg_confidence:.1%}")
        
        # Signal timeline chart
        st.markdown("**Signal Timeline:**")
        
        fig_signals = go.Figure()
        
        # Add price line
        fig_signals.add_trace(
            go.Scatter(
                x=backtest_df['date'],
                y=backtest_df['price'],
                mode='lines',
                name='Price',
                line=dict(color='gray', width=2)
            )
        )
        
        # Add signal markers
        signal_colors_map = {'buy': 'green', 'sell': 'red', 'hold': 'yellow'}
        
        for signal_type in ['buy', 'sell', 'hold']:
            signal_subset = backtest_df[backtest_df['signal'] == signal_type]
            if not signal_subset.empty:
                fig_signals.add_trace(
                    go.Scatter(
                        x=signal_subset['date'],
                        y=signal_subset['price'],
                        mode='markers',
                        name=f'{signal_type.title()} Signals',
                        marker=dict(
                            color=signal_colors_map[signal_type],
                            size=10,
                            symbol='triangle-up' if signal_type == 'buy' else 'triangle-down' if signal_type == 'sell' else 'circle'
                        )
                    )
                )
        
        fig_signals.update_layout(
            title=f'{symbol_input} Signal Timeline - {selected_asset_type_name}',
            xaxis_title='Date',
            yaxis_title='Price ($)',
            height=400,
            showlegend=True
        )
        
        st.plotly_chart(fig_signals, use_container_width=True)
    else:
        st.info("No signals generated for the selected period")

# Engine information
st.markdown("---")
st.subheader("🔧 Engine Information")

engine_info = signal_data.get("engine", {})
st.markdown(f"**Engine:** {engine_info.get('name', 'N/A')}")
st.markdown(f"**Type:** {engine_info.get('type', 'N/A')}")
st.markdown(f"**Description:** {engine_info.get('description', 'N/A')}")

# Configuration details
config = engine_info.get("config", {})
if config:
    st.markdown("**Configuration:**")
    for key, value in config.items():
        st.markdown(f"• {key.replace('_', ' ').title()}: {value}")

# Footer
st.markdown("---")
st.markdown("*Powered by Universal Backtest API v1.0*")
st.markdown("*Data updated in real-time from market sources*")
