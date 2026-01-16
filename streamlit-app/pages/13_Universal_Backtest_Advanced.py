#!/usr/bin/env python3
"""
Universal Backtest Dashboard - Enhanced Version
Advanced backtesting for any asset type using the Universal API
Enhanced with stock management, database integration, and beautiful UI
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
from api_client import get_go_api_client, APIClient, APIError
from api_config import api_config

# Page setup
setup_page_config("Universal Backtest Dashboard", "🚀")

# 🎨 Enhanced Header
st.markdown("""
<div style="
    background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
    padding: 30px;
    border-radius: 15px;
    margin-bottom: 25px;
    text-align: center;
    color: white;
">
    <h1 style="margin: 0; font-size: 3em;">🚀 Universal Backtest Dashboard</h1>
    <p style="margin: 10px 0; font-size: 1.3em;">Advanced backtesting for any asset type (3x ETFs, Regular ETFs, Stocks)</p>
    <p style="margin: 0; opacity: 0.9;">Professional Stock Analysis & Signal Generation</p>
</div>
""", unsafe_allow_html=True)

# Sidebar
render_sidebar()

# Initialize API client
python_api_url = api_config.python_worker_url
python_client = APIClient(python_api_url, timeout=30)

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

# Check for transferred symbol from Portfolio Analysis
transferred_symbol = st.session_state.get('transfer_symbol', None)
if transferred_symbol:
    st.sidebar.success(f"📊 Symbol transferred from Portfolio: {transferred_symbol}")
    # Clear the transfer after displaying
    if 'transfer_symbol' in st.session_state:
        del st.session_state['transfer_symbol']

# 🎯 Professional Stock Analysis Section
st.markdown("### 🎯 Professional Stock Analysis")

# Stock Selection Section with Database Integration
col1, col2 = st.columns([2, 1])

with col1:
    # Get available stocks from database
    st.markdown("#### 📊 Stock Selection")
    
    # If symbol was transferred, show it prominently
    if transferred_symbol:
        st.info(f"🎯 Analyzing transferred symbol: **{transferred_symbol}**")
        symbol_input = transferred_symbol
    else:
        try:
            stocks_response = python_client.get("api/v1/stocks/available")
            if stocks_response and isinstance(stocks_response, list):
                available_stocks = stocks_response
                
                # Create display options with company names
                stock_options = []
                stock_map = {}
                
                for stock in available_stocks:
                    display_name = f"{stock['symbol']} - {stock.get('company_name', 'Unknown Company')}"
                    stock_options.append(display_name)
                    stock_map[display_name] = stock
                
                # Stock selector with search
                selected_display = st.selectbox(
                    "🔍 Select Stock for Analysis",
                    options=stock_options,
                    index=0,
                    key="stock_selector"
                )
                
                # Get the actual symbol from selection
                selected_stock = stock_map[selected_display]
                symbol_input = selected_stock['symbol']
                
                # Also show manual input option
                st.markdown("**Or enter symbol manually:**")
                symbol_input = st.text_input(
                    "📝 Symbol (e.g., AAPL, TSLA, QQQ)",
                    value=symbol_input,  # Pre-fill with selected symbol
                    key="symbol_input"
                ).upper()
            else:
                # Fallback to manual input only
                symbol_input = st.text_input(
                    "📝 Enter Symbol (e.g., AAPL, TSLA, QQQ)",
                    placeholder="e.g., AAPL, TSLA, QQQ",
                    key="symbol_input_fallback"
                ).upper()
        except Exception as e:
            st.error(f"❌ Error loading stocks: {str(e)}")
            # Fallback to manual input
            symbol_input = st.text_input(
                "📝 Enter Symbol (e.g., AAPL, TSLA, QQQ)",
                placeholder="e.g., AAPL, TSLA, QQQ",
                key="symbol_input_error"
            ).upper()

with col2:
    # Asset type selection
    st.markdown("#### ⚙️ Asset Configuration")
    
    selected_asset_type_name = st.selectbox(
        "Asset Type",
        list(asset_type_options.keys()),
        index=0,
        key="enhanced_asset_type",
        help="Select the asset type for analysis parameters"
    )
    
    selected_asset_type = asset_type_options[selected_asset_type_name]
    
    # Asset type information card
    asset_info = {
        "3x ETF": {
            "description": "3x leveraged ETFs with high volatility",
            "risk": "Very High",
            "holding_period": "Short-term (1-5 days)",
            "examples": "TQQQ, SOXL, FNGU",
            "color": "#FF4444"
        },
        "Regular ETF": {
            "description": "Standard ETFs with moderate volatility",
            "risk": "Medium",
            "holding_period": "Medium-term (1-4 weeks)",
            "examples": "QQQ, SPY, IWM",
            "color": "#FF8800"
        },
        "Stock": {
            "description": "Individual stocks with varying volatility",
            "risk": "Variable",
            "holding_period": "Depends on stock",
            "examples": "AAPL, MSFT, NVDA",
            "color": "#00C851"
        }
    }
    
    info = asset_info.get(selected_asset_type_name, {})
    
    # 🎨 Asset Info Card
    st.markdown(f"""
    <div style="
        background: {info.get('color', '#667eea')};
        padding: 15px;
        border-radius: 10px;
        color: white;
        margin-bottom: 15px;
    ">
        <h4 style="margin: 0;">{selected_asset_type_name}</h4>
        <p style="margin: 5px 0; font-size: 0.9em; opacity: 0.9;">{info.get('description', 'N/A')}</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"**⚠️ Risk Level:** {info.get('risk', 'N/A')}")
    st.markdown(f"**⏱️ Holding Period:** {info.get('holding_period', 'N/A')}")
    st.markdown(f"**📋 Examples:** {info.get('examples', 'N/A')}")
    
    # Add new stock functionality
    st.markdown("---")
    st.markdown("#### ➕ Add New Stock")
    
    new_symbol = st.text_input(
        "Add Symbol",
        placeholder="e.g., GME, AMC, PLTR",
        key="new_symbol_input_enhanced",
        help="Add a new symbol to our database (auto-fills company info)"
    )
    
    if st.button("🔍 Add Stock", key="add_stock_button_enhanced", use_container_width=True):
        if new_symbol and len(new_symbol.strip()) >= 1:
            with st.spinner(f"Adding {new_symbol.upper()} to database..."):
                try:
                    add_response = python_client.post(
                        "api/v1/stocks/add",
                        json_data={"symbol": new_symbol.strip()}
                    )
                    
                    if add_response and add_response.get('symbol'):
                        st.success(f"✅ Successfully added {new_symbol.upper()}!")
                        st.info(f"🏢 Company: {add_response.get('company_name', 'N/A')}")
                        st.rerun()
                    else:
                        st.error(f"❌ Failed to add {new_symbol.upper()}")
                except Exception as e:
                    st.error(f"❌ Error adding stock: {e}")
        else:
            st.warning("⚠️ Please enter a valid symbol")
    
    # Load today's data button
    st.markdown("---")
    st.markdown("#### 🔄 Data Management")
    
    if st.button("📊 Load Today's Data", key="load_today_data", use_container_width=True, help="Refresh data for selected stock"):
        with st.spinner(f"Loading today's data for {symbol_input}..."):
            try:
                refresh_response = python_client.post(
                    "refresh",
                    json_data={
                        "symbols": [symbol_input],
                        "data_types": ["price_historical", "indicators"],
                        "force": True
                    },
                    timeout=300
                )
                
                if refresh_response and refresh_response.get("success"):
                    st.success(f"✅ Today's data loaded for {symbol_input}!")
                    st.info("📊 Data refreshed successfully")
                    st.json(refresh_response)
                else:
                    st.warning(f"⚠️ Data refresh completed with warnings for {symbol_input}")
                    if refresh_response:
                        st.json(refresh_response)
            except Exception as e:
                st.error(f"❌ Failed to load data: {e}")

# 📅 Date Selection and Analysis Controls
st.markdown("---")
st.markdown("### 📅 Analysis Configuration")

date_col1, date_col2, date_col3 = st.columns(3)

with date_col1:
    # Date selection
    default_date = datetime.now().date() - timedelta(days=1)
    selected_date = st.date_input(
        "📅 Select Analysis Date",
        value=default_date,
        max_value=datetime.now().date(),
        help="Choose date for signal analysis"
    )

with date_col2:
    # Backtest period
    backtest_days = st.slider(
        "📊 Backtest Period (Days)",
        min_value=30,
        max_value=365,
        value=90,
        step=30,
        help="Period for historical analysis"
    )

with date_col3:
    # Calculate date range info
    end_date = selected_date
    start_date = end_date - timedelta(days=backtest_days)
    
    st.markdown("**📈 Analysis Range:**")
    st.markdown(f"**From:** {start_date.strftime('%m/%d/%Y')}")
    st.markdown(f"**To:** {end_date.strftime('%m/%d/%Y')}")
    st.markdown(f"**Days:** {backtest_days}")

# 🚀 Run Analysis Button
st.markdown("---")

analysis_col1, analysis_col2, analysis_col3 = st.columns([1, 2, 1])

with analysis_col2:
    run_analysis = st.button(
        "🚀 Run Analysis", 
        type="primary", 
        use_container_width=True,
        help="Generate comprehensive signal analysis and backtest"
    )

# Quick refresh option (if symbol is already analyzed)
if 'last_analyzed_symbol' in st.session_state and 'last_analysis_data' in st.session_state:
    if st.session_state.last_analyzed_symbol == symbol_input:
        st.markdown("---")
        refresh_col1, refresh_col2, refresh_col3 = st.columns([1, 2, 1])
        
        with refresh_col2:
            refresh_analysis = st.button(
                "🔄 Refresh Signal Only", 
                type="secondary",
                use_container_width=True,
                help="Refresh signal analysis without reloading data (faster)"
            )
            
            if refresh_analysis:
                with st.spinner(f"🔄 Refreshing signal analysis for {symbol_input}..."):
                    try:
                        # Get fresh signal without data reload
                        signal_data = get_universal_signal(symbol_input, selected_date, selected_asset_type)
                        
                        if signal_data and not signal_data.get('error'):
                            # Update session state with fresh data
                            st.session_state.last_analysis_data = signal_data
                            st.session_state.last_analyzed_symbol = symbol_input
                            
                            st.success(f"✅ Signal refreshed for {symbol_input}!")
                            st.rerun()
                        else:
                            st.error(f"❌ Error refreshing signal: {signal_data.get('error', 'Unknown error')}")
                    except Exception as e:
                        st.error(f"❌ Failed to refresh signal: {str(e)}")

# Only proceed if user clicks Run Analysis
if not run_analysis:
    st.info("👆 Click 'Run Analysis' to generate signal and backtest data")
    st.stop()

# 🎯 Enhanced Signal Analysis Section
st.markdown("---")
st.markdown("### 🎯 Enhanced Signal Analysis")

# Get current signal
def get_universal_signal(symbol, date, asset_type):
    """Get signal for any asset using universal API"""
    try:
        api_url = f"{python_api_url}/api/v1/universal/signal/universal"
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

# Get signal data
with st.spinner(f"🔄 Generating signal analysis for {symbol_input}..."):
    signal_data = get_universal_signal(symbol_input, selected_date, selected_asset_type)

if "error" in signal_data:
    st.error(f"❌ {signal_data['error']}")
    st.stop()

# Use shared analysis display component
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from components.analysis_display import display_signal_analysis

# Display the analysis using the shared component
display_signal_analysis(symbol_input, signal_data, show_header=True, show_debug=True)

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
