#!/usr/bin/env python3
"""
Streamlit Admin Dashboard for Trading System
Load and visualize historical, daily, current, intraday data; compute indicators and signals.
"""

import streamlit as st
import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

# Import API client for proper architecture
from api_client import APIClient

from app.providers.yahoo_finance.client import YahooFinanceClient
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.indicators.moving_averages import calculate_sma, calculate_ema
from app.indicators.momentum import calculate_rsi, calculate_macd
from app.indicators.signals_with_reasons import generate_signals_with_reasons
from app.analysis.stock_analysis import generate_stock_analysis
from app.analysis.investment_recommendation import generate_comprehensive_report
from app.observability.logging import get_logger

logger = get_logger("streamlit_admin_dashboard")

st.set_page_config(page_title="Trading System Admin", layout="wide")

@st.cache_data(ttl=600)
def fetch_all_data(symbol):
    """Fetch all available data for a symbol with caching."""
    client = YahooFinanceClient.from_settings()
    source = YahooFinanceSource()
    results = {}
    try:
        results["current_price"] = client.fetch_current_price(symbol)
        results["details"] = client.fetch_symbol_details(symbol)
        
        # Skip fundamentals for swing trading symbols (ETFs, VIX)
        swing_symbols = ['VIX', 'TQQQ', 'QQQ', 'SMH', 'SOFI', 'NVDA', 'GOOGL']
        if symbol not in swing_symbols:
            results["fundamentals"] = client.fetch_fundamentals(symbol)
            results["earnings_history"] = client.fetch_quarterly_earnings_history(symbol)
        
        results["analyst_recs"] = client.fetch_analyst_recommendations(symbol)
        results["news"] = client.fetch_news(symbol, limit=10)
        results["peers"] = client.fetch_industry_peers(symbol)
        results["price_1y"] = client.fetch_price_data(symbol, period="1y")
        results["price_1mo"] = client.fetch_price_data(symbol, period="1mo")
        results["price_5d"] = client.fetch_price_data(symbol, period="5d")
        results["price_1d"] = client.fetch_price_data(symbol, period="1d", interval="15m")
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        logger.error(f"Dashboard fetch error for {symbol}: {e}")
    return results

def compute_indicators(df):
    """Compute technical indicators for a DataFrame."""
    if df is None or df.empty:
        return df
    df = df.copy()
    df["sma20"] = calculate_sma(df["close"], 20)
    df["sma50"] = calculate_sma(df["close"], 50)
    df["sma200"] = calculate_sma(df["close"], 200)
    df["ema20"] = calculate_ema(df["close"], 20)
    df["ema50"] = calculate_ema(df["close"], 50)
    df["rsi"] = calculate_rsi(df["close"], 14)
    macd_line, macd_signal, macd_hist = calculate_macd(df["close"])
    df["macd"] = macd_line
    df["macd_signal"] = macd_signal
    df["macd_histogram"] = macd_hist
    df["volume_ma"] = df["volume"].rolling(20).mean()
    return df

def generate_signals_df(df):
    """Generate signals with reasons for a DataFrame with indicators."""
    if df is None or df.empty or "signal" in df.columns:
        return df
    # Add required inputs for signal generation
    df["volume_ma"] = df["volume"].rolling(20).mean()
    df["trend_long"] = df.apply(lambda row: 'bullish' if row['close'] > row.get('sma200', row['close']) else 'bearish', axis=1)
    df["trend_medium"] = df.apply(lambda row: 'bullish' if row.get('ema20', row['close']) > row.get('sma50', row['close']) else 'bearish', axis=1)
    signals_df = generate_signals_with_reasons(
        price=df["close"],
        ema20=df["ema20"],
        ema50=df["ema50"],
        sma200=df["sma200"],
        macd_line=df["macd"],
        macd_signal=df["macd_signal"],
        macd_histogram=df["macd_histogram"],
        rsi=df["rsi"],
        volume=df["volume"],
        volume_ma=df["volume_ma"],
        long_term_trend=df["trend_long"],
        medium_term_trend=df["trend_medium"]
    )
    df["signal"] = signals_df["signal"]
    df["reason"] = signals_df["reason"]
    df["confidence"] = df["signal"].map({"buy": 0.8, "sell": 0.8, "hold": 0.5})
    return df

st.title("📈 Trading System Admin Dashboard")
st.sidebar.header("Controls")

symbol = st.sidebar.text_input("Symbol", value="CIEN", max_chars=10).upper()

# Swing Trading Quick Load Section
st.sidebar.markdown("---")
st.sidebar.markdown("### 🎯 Swing Trading Analysis")

# Quick load buttons for swing trading symbols
col1, col2 = st.sidebar.columns(2)

with col1:
    if st.button("📊 VIX", help="Load VIX volatility data (Required for market analysis)"):
        symbol = "VIX"
        st.session_state.load_symbol = symbol
        
with col2:
    if st.button("🚀 TQQQ", help="Load TQQQ 3x leveraged ETF data"):
        symbol = "TQQQ"
        st.session_state.load_symbol = symbol

# Additional swing trading symbols
st.sidebar.markdown("**Quick Load Other Symbols:**")
swing_symbols = ["QQQ", "NVDA", "GOOGL", "SMH", "SOFI"]
for swing_symbol in swing_symbols:
    if st.sidebar.button(f"📈 {swing_symbol}", key=f"load_{swing_symbol}"):
        symbol = swing_symbol
        st.session_state.load_symbol = symbol

# Market Data Availability Section
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Market Data Status")

@st.cache_data(ttl=300)  # Cache for 5 minutes
def check_swing_data_availability():
    """Check availability of swing trading data using API calls only"""
    availability = {}
    
    try:
        # Use python-worker API for data availability
        python_api_url = os.getenv("PYTHON_API_URL", "http://python-worker:8001")
        api_client = APIClient(python_api_url, timeout=10)
        
        # Check VIX data using API
        try:
            vix_response = api_client.get("/admin/data-summary/raw_market_data_daily", params={"symbol_filter": "VIX"})
            if vix_response and vix_response.get('success'):
                availability['VIX'] = vix_response.get('data', {}).get('records', [])
            else:
                availability['VIX'] = []
        except Exception as e:
            st.warning(f"VIX data check failed: {str(e)}")
            availability['VIX'] = []
        
        # Check TQQQ data using API
        try:
            tqqq_response = api_client.get("/admin/data-summary/raw_market_data_daily", params={"symbol_filter": "TQQQ"})
            if tqqq_response and tqqq_response.get('success'):
                availability['TQQQ'] = tqqq_response.get('data', {}).get('records', [])
            else:
                availability['TQQQ'] = []
        except Exception as e:
            st.warning(f"TQQQ data check failed: {str(e)}")
            availability['TQQQ'] = []
        
        # Check indicators data using API
        try:
            indicators_response = api_client.get("/admin/data-summary/indicators_daily")
            if indicators_response and indicators_response.get('success'):
                # Filter for swing trading symbols
                all_indicators = indicators_response.get('data', {}).get('records', [])
                swing_indicators = [ind for ind in all_indicators if ind.get('symbol') in ['VIX', 'TQQQ', '^VIX']]
                availability['indicators'] = swing_indicators
            else:
                availability['indicators'] = []
        except Exception as e:
            st.warning(f"Indicators data check failed: {str(e)}")
            availability['indicators'] = []
        
        return availability
        
    except Exception as e:
        st.error(f"Failed to check data availability via API: {str(e)}")
        return {'VIX': [], 'TQQQ': [], 'indicators': []}

data_status = check_swing_data_availability()

# Display data availability status
if not data_status:
    st.sidebar.error("❌ Unable to check data availability")
else:
    # VIX Status
    vix_data = data_status.get('VIX', [])
    if vix_data:
        vix_info = vix_data[0] if isinstance(vix_data, list) else vix_data
        total_records = vix_info.get('total_records', len(vix_data) if isinstance(vix_data, list) else 0)
        latest_date = vix_info.get('latest_date', 'Unknown')
        vix_status = "✅" if total_records > 0 else "⚠️"
        st.sidebar.write(f"{vix_status} **VIX**: {total_records} records, Latest: {latest_date}")
    else:
        st.sidebar.write("❌ **VIX**: No data available")
    
    # TQQQ Status
    tqqq_data = data_status.get('TQQQ', [])
    if tqqq_data:
        tqqq_info = tqqq_data[0] if isinstance(tqqq_data, list) else tqqq_data
        total_records = tqqq_info.get('total_records', len(tqqq_data) if isinstance(tqqq_data, list) else 0)
        latest_date = tqqq_info.get('latest_date', 'Unknown')
        tqqq_status = "✅" if total_records > 0 else "⚠️"
        st.sidebar.write(f"{tqqq_status} **TQQQ**: {total_records} records, Latest: {latest_date}")
    else:
        st.sidebar.write("❌ **TQQQ**: No data available")
    
    # Indicators Status
    indicators_data = data_status.get('indicators', [])
    if indicators_data:
        indicators_count = len(indicators_data) if isinstance(indicators_data, list) else 1
        st.sidebar.write(f"✅ **Indicators**: {indicators_count} symbols available")
    else:
        st.sidebar.write("❌ **Indicators**: No data available")

# Auto-load VIX if no data loaded yet
if 'data' not in st.session_state and not hasattr(st.session_state, 'load_symbol'):
    st.sidebar.info("🔄 Auto-loading VIX for market analysis...")
    symbol = "VIX"
    st.session_state.load_symbol = symbol

# Load swing trading symbols
if hasattr(st.session_state, 'load_symbol') and st.session_state.load_symbol:
    symbol = st.session_state.load_symbol
    st.session_state.load_symbol = None  # Reset after use
    # Auto-trigger data load
    with st.spinner(f"Loading swing trading data for {symbol}..."):
        data = fetch_all_data(symbol)
    st.success(f"Swing trading data loaded for {symbol}!")
elif st.sidebar.button("Load Data"):
    with st.spinner(f"Loading data for {symbol}..."):
        data = fetch_all_data(symbol)
    st.success("Data loaded!")

    # Swing Trading Analysis Section
    if symbol in ['VIX', 'TQQQ', 'QQQ', 'NVDA', 'GOOGL', 'SMH', 'SOFI']:
        st.markdown("---")
        st.subheader(f"🎯 Swing Trading Analysis - {symbol}")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            symbol_types = {
                'VIX': 'Volatility Index',
                'TQQQ': '3x Leveraged ETF',
                'QQQ': 'ETF (NASDAQ-100)',
                'NVDA': 'Tech Stock',
                'GOOGL': 'Tech Stock', 
                'SMH': 'Semiconductor ETF',
                'SOFI': 'Fintech Stock'
            }
            st.metric("Symbol Type", symbol_types.get(symbol, 'Stock/ETF'))
            
        with col2:
            price_data = data.get('price_1y')
            if price_data is not None and not price_data.empty:
                current_price = price_data['Close'].iloc[-1]
                volatility = price_data['Close'].pct_change().std() * 100
                st.metric("Volatility", f"{volatility:.2f}%")
            else:
                st.metric("Volatility", "N/A")
                
        with col3:
            if price_data is not None and not price_data.empty:
                recent_change = (price_data['Close'].iloc[-1] - price_data['Close'].iloc[-5]) / price_data['Close'].iloc[-5] * 100
                st.metric("5-Day Change", f"{recent_change:.2f}%")
            else:
                st.metric("5-Day Change", "N/A")
        
        # Swing Trading Specific Info
        if symbol == 'VIX':
            st.info("📊 **VIX Analysis**: VIX above 20 indicates increased market volatility. Above 30 suggests high market stress. Useful for determining market regime and risk management.")
        elif symbol == 'TQQQ':
            st.info("🚀 **TQQQ Analysis**: 3x leveraged NASDAQ-100 ETF. High volatility instrument requiring aggressive risk management. Best for trend-following and volatility expansion strategies.")
        elif symbol == 'QQQ':
            st.info("📈 **QQQ Analysis**: NASDAQ-100 ETF. Good for tech sector trend analysis. Lower volatility than TQQQ but still responsive to market movements.")
        elif symbol in ['NVDA', 'GOOGL']:
            st.info("💻 **Tech Stock Analysis**: Large-cap tech stocks with high liquidity. Good for swing trading with clear trend patterns and earnings-driven movements.")
        elif symbol == 'SMH':
            st.info("🔌 **SMH Analysis**: Semiconductor ETF. Highly correlated with tech sector cycles and chip demand. Good for sector rotation strategies.")
        elif symbol == 'SOFI':
            st.info("💰 **SOFI Analysis**: Fintech stock with higher volatility. Good for momentum trading but requires careful risk management.")
        
        # Recent price action
        if price_data is not None and not price_data.empty:
            st.subheader("Recent Price Action")
            recent_data = price_data.tail(20)  # Last 20 trading days
            
            # Calculate some swing trading metrics
            recent_data['MA20'] = recent_data['Close'].rolling(20).mean()
            recent_data['MA50'] = recent_data['Close'].rolling(50).mean() if len(recent_data) >= 50 else recent_data['Close'].rolling(len(recent_data)).mean()
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Price vs Moving Averages**")
                current_price = recent_data['Close'].iloc[-1]
                ma20 = recent_data['MA20'].iloc[-1]
                ma50 = recent_data['MA50'].iloc[-1]
                
                st.write(f"Current Price: ${current_price:.2f}")
                st.write(f"20-day MA: ${ma20:.2f}")
                st.write(f"50-day MA: ${ma50:.2f}")
                
                if current_price > ma20 and current_price > ma50:
                    st.success("📈 Above both MAs (Bullish)")
                elif current_price < ma20 and current_price < ma50:
                    st.error("📉 Below both MAs (Bearish)")
                else:
                    st.warning("📊 Mixed Signals (Neutral)")
            
            with col2:
                st.markdown("**Volatility Analysis**")
                daily_returns = recent_data['Close'].pct_change().dropna()
                avg_volatility = daily_returns.std() * 100
                max_daily_change = daily_returns.abs().max() * 100
                
                st.write(f"Average Volatility: {avg_volatility:.2f}%")
                st.write(f"Max Daily Change: {max_daily_change:.2f}%")
                
                if symbol == 'VIX':
                    if current_price > 30:
                        st.error("🔴 High Market Stress")
                    elif current_price > 20:
                        st.warning("🟡 Moderate Volatility")
                    else:
                        st.success("🟢 Low Volatility")
                else:  # TQQQ
                    if avg_volatility > 5:
                        st.error("🔴 High Volatility - Risk Management Priority")
                    elif avg_volatility > 3:
                        st.warning("🟡 Moderate Volatility")
                    else:
                        st.success("🟢 Lower Volatility - Opportunity")
        
        # Swing Trading Signals Section
        st.markdown("---")
        st.subheader(f"🎯 Swing Trading Signals - {symbol}")
        
        # Add date input for testing specific dates
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            test_date = st.date_input(
                "Test Date (leave empty for most recent data)",
                value=None,
                key="swing_test_date",
                help="Test signals for a specific date, or leave empty for most recent data"
            )
        with col2:
            use_specific_date = st.checkbox("Use Specific Date", key="use_specific_date")
        with col3:
            if st.button("🔄 Refresh Signals", key="refresh_signals"):
                st.rerun()
        
        try:
            import requests
            import json
            
            # Debug: Show what we're about to do
            st.write(f"🔍 Debug: Getting signals for {symbol}")
            if use_specific_date and test_date:
                st.write(f"🔍 Debug: Testing specific date: {test_date}")
            else:
                st.write(f"🔍 Debug: Using most recent data")
            
            # Get signals from BOTH engines for comparison
            signals_data = {}
            
            # TQQQ Engine (only for TQQQ symbol)
            if symbol == 'TQQQ':
                tqqq_api_url = "http://127.0.0.1:8001/signal/tqqq"
                # Use specific date if provided, otherwise None for most recent
                tqqq_payload = {"date": test_date.strftime("%Y-%m-%d")} if (use_specific_date and test_date) else None
                
                # Comprehensive API call debugging
                st.markdown("### 🔍 TQQQ Engine API Call Debug")
                col1, col2 = st.columns(2)
                with col1:
                    st.code(f"**API URL:**\n{tqqq_api_url}")
                with col2:
                    st.code(f"**Method:**\nPOST")
                
                st.code(f"**Headers:**\n{{'Content-Type': 'application/json'}}")
                st.code(f"**Payload:**\n{json.dumps(tqqq_payload, indent=2)}")
                st.code(f"**Timeout:**\n5 seconds")
                
                st.write(f"🔍 Debug: Calling TQQQ API at {tqqq_api_url}")
                st.write(f"🔍 Debug: Payload = {tqqq_payload}")
                
                try:
                    # Show request being sent
                    with st.spinner("🚀 Making TQQQ API call..."):
                        tqqq_response = requests.post(
                            tqqq_api_url, 
                            json=tqqq_payload, 
                            headers={'Content-Type': 'application/json'},
                            timeout=5
                        )
                    
                    st.write(f"🔍 Debug: TQQQ Response status = {tqqq_response.status_code}")
                    st.code(f"**Response Status:**\n{tqqq_response.status_code}")
                    st.code(f"**Response Headers:**\n{dict(tqqq_response.headers)}")
                    
                    if tqqq_response.status_code == 200:
                        signals_data['tqqq_engine'] = tqqq_response.json()
                        st.write(f"🔍 Debug: TQQQ API success!")
                        st.success("✅ TQQQ API call successful!")
                        
                        # Show full API response
                        with st.expander("🔍 Full TQQQ API Response"):
                            st.json(signals_data['tqqq_engine'])
                    else:
                        st.write(f"🔍 Debug: TQQQ API failed with status {tqqq_response.status_code}")
                        st.write(f"🔍 Debug: Response = {tqqq_response.text}")
                        st.error(f"❌ TQQQ API failed with status {tqqq_response.status_code}")
                        
                        # Show error response
                        with st.expander("❌ TQQQ Error Response"):
                            st.code(tqqq_response.text)
                        
                except requests.exceptions.Timeout:
                    st.error("🔍 Debug: TQQQ engine timeout after 5 seconds")
                    st.warning("TQQQ engine timeout - try again later")
                except requests.exceptions.ConnectionError:
                    st.error("🔍 Debug: TQQQ engine connection error")
                    st.warning("TQQQ engine unavailable - check if server is running")
                except Exception as e:
                    st.error(f"🔍 Debug: TQQQ engine error: {str(e)}")
                    st.warning(f"TQQQ engine unavailable: {str(e)}")
            
            # Generic Engine (for all symbols)
            generic_api_url = "http://127.0.0.1:8001/signal/generic"
            # Use specific date if provided, otherwise None for most recent
            generic_payload = {"symbol": symbol, "date": test_date.strftime("%Y-%m-%d")} if (use_specific_date and test_date) else {"symbol": symbol, "date": None}
            
            # Comprehensive API call debugging
            st.markdown("### 🔍 Generic Engine API Call Debug")
            col1, col2 = st.columns(2)
            with col1:
                st.code(f"**API URL:**\n{generic_api_url}")
            with col2:
                st.code(f"**Method:**\nPOST")
            
            st.code(f"**Headers:**\n{{'Content-Type': 'application/json'}}")
            st.code(f"**Payload:**\n{json.dumps(generic_payload, indent=2)}")
            st.code(f"**Timeout:**\n5 seconds")
            
            st.write(f"🔍 Debug: Calling Generic API at {generic_api_url}")
            st.write(f"🔍 Debug: Payload = {generic_payload}")
            
            try:
                # Show request being sent
                with st.spinner("🚀 Making Generic API call..."):
                    generic_response = requests.post(
                        generic_api_url, 
                        json=generic_payload, 
                        headers={'Content-Type': 'application/json'},
                        timeout=5
                    )
                
                st.write(f"🔍 Debug: Generic Response status = {generic_response.status_code}")
                st.code(f"**Response Status:**\n{generic_response.status_code}")
                st.code(f"**Response Headers:**\n{dict(generic_response.headers)}")
                
                if generic_response.status_code == 200:
                    signals_data['generic_engine'] = generic_response.json()
                    st.write(f"🔍 Debug: Generic API success!")
                    st.success("✅ Generic API call successful!")
                    
                    # Show full API response
                    with st.expander("🔍 Full Generic API Response"):
                        st.json(signals_data['generic_engine'])
                else:
                    st.write(f"🔍 Debug: Generic API failed with status {generic_response.status_code}")
                    st.write(f"🔍 Debug: Response = {generic_response.text}")
                    st.error(f"❌ Generic API failed with status {generic_response.status_code}")
                    
                    # Show error response
                    with st.expander("❌ Generic Error Response"):
                        st.code(generic_response.text)
                    
            except requests.exceptions.Timeout:
                st.error("🔍 Debug: Generic engine timeout after 5 seconds")
                st.warning("Generic engine timeout - try again later")
            except requests.exceptions.ConnectionError:
                st.error("🔍 Debug: Generic engine connection error")
                st.warning("Generic engine unavailable - check if server is running")
            except Exception as e:
                st.error(f"🔍 Debug: Generic engine error: {str(e)}")
                st.warning(f"Generic engine unavailable: {str(e)}")
            
            # Display comparison
            if signals_data:
                st.markdown("### 🔄 Engine Comparison")
                
                # Create comparison table
                comparison_data = []
                
                for engine_name, signal_response in signals_data.items():
                    if signal_response.get('success'):
                        signal_info = signal_response['data']['signal']
                        analysis_info = signal_response['data']['analysis']
                        
                        comparison_data.append({
                            'Engine': 'TQQQ Specialized' if engine_name == 'tqqq_engine' else 'Generic Adaptive',
                            'Signal': signal_info['signal'].upper(),
                            'Confidence': f"{signal_info['confidence']:.2f}",
                            'Regime': signal_info.get('metadata', {}).get('regime', 'N/A'),
                            'Volatility': analysis_info.get('real_volatility', 'N/A'),
                            'Recent Change': analysis_info.get('recent_change', 'N/A'),
                            'VIX Level': analysis_info.get('vix_level', 'N/A')
                        })
                
                if comparison_data:
                    comparison_df = pd.DataFrame(comparison_data)
                    st.dataframe(comparison_df, use_container_width=True)
                
                # Detailed signal analysis for each engine
                for engine_name, signal_response in signals_data.items():
                    if signal_response.get('success'):
                        signal_info = signal_response['data']['signal']
                        analysis_info = signal_response['data']['analysis']
                        
                        engine_display = 'TQQQ Specialized Engine' if engine_name == 'tqqq_engine' else 'Generic Adaptive Engine'
                        
                        with st.expander(f"🔍 {engine_display} - Detailed Analysis"):
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                signal_color = {
                                    'buy': '🟢',
                                    'sell': '🔴', 
                                    'hold': '🟡'
                                }.get(signal_info['signal'], '⚪')
                                st.metric(f"Signal {signal_color}", signal_info['signal'].upper())
                                
                            with col2:
                                st.metric("Confidence", f"{signal_info['confidence']:.2f}")
                                
                            with col3:
                                st.metric("Regime", signal_info.get('metadata', {}).get('regime', 'N/A'))
                            
                            # Show reasoning
                            st.markdown("**Signal Reasoning:**")
                            for reason in signal_info.get('reasoning', []):
                                st.write(f"• {reason}")
                            
                            # Show market analysis
                            st.markdown("**Market Analysis:**")
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.write(f"Real Volatility: {analysis_info.get('real_volatility', 'N/A')}")
                                st.write(f"Recent Change: {analysis_info.get('recent_change', 'N/A')}")
                                st.write(f"VIX Level: {analysis_info.get('vix_level', 'N/A')}")
                                
                            with col2:
                                st.write(f"Market Stress: {analysis_info.get('market_stress', 'N/A')}")
                                st.write(f"Volatility Level: {analysis_info.get('volatility_level', 'N/A')}")
                            
                            # Engine-specific info
                            if engine_name == 'tqqq_engine':
                                st.info("🚀 **TQQQ Engine**: Specialized 3x leveraged ETF engine with aggressive volatility detection and risk management.")
                            else:
                                engine_type = analysis_info.get('symbol_type', 'Unknown')
                                st.info(f"📊 **Generic Engine**: Adaptive {engine_type} engine with symbol-specific configuration.")
                
                # Signal Consistency Analysis
                if len(comparison_data) > 1:
                    st.markdown("### 📊 Signal Consistency Analysis")
                    
                    signals = [row['Signal'] for row in comparison_data]
                    if len(set(signals)) == 1:
                        st.success(f"✅ **Consistent Signals**: Both engines agree on {signals[0]}")
                    else:
                        st.warning("⚠️ **Divergent Signals**: Engines disagree - review analysis carefully")
                        
                        # Show differences
                        st.markdown("**Key Differences:**")
                        for i, row1 in enumerate(comparison_data):
                            for j, row2 in enumerate(comparison_data):
                                if i < j:  # Avoid duplicate comparisons
                                    if row1['Signal'] != row2['Signal']:
                                        st.write(f"• {row1['Engine']}: {row1['Signal']} vs {row2['Engine']}: {row2['Signal']}")
                                        if row1['Regime'] != row2['Regime']:
                                            st.write(f"  - Regime: {row1['Regime']} vs {row2['Regime']}")
                                        if row1['Confidence'] != row2['Confidence']:
                                            st.write(f"  - Confidence: {row1['Confidence']} vs {row2['Confidence']}")
                
            else:
                st.warning("No swing trading signals available")
                st.write("💡 Make sure the Python Worker API is running on http://127.0.0.1:8001")
                
        except Exception as e:
            st.info(f"Swing trading signals unavailable: {str(e)}")
            st.write("💡 Make sure the Python Worker API is running on http://127.0.0.1:8001")

    # Current price and details
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Current Price", f"{data.get('current_price', 'N/A')}")
    with col2:
        details = data.get("details", {})
        st.metric("Market Cap", f"{details.get('market_cap', 'N/A')}")
    with col3:
        st.metric("PE Ratio", f"{details.get('pe_ratio', 'N/A')}")

    # Fundamentals (skip for swing trading symbols)
    swing_symbols = ['VIX', 'TQQQ', 'QQQ', 'SMH', 'SOFI', 'NVDA', 'GOOGL']
    if symbol not in swing_symbols:
        st.subheader("Fundamentals")
        fundamentals = data.get("fundamentals", {})
        if fundamentals:
            fund_df = pd.DataFrame(list(fundamentals.items()), columns=["Metric", "Value"])
            st.dataframe(fund_df, use_container_width=True)
        else:
            st.info("No fundamentals data available")
    else:
        # Show swing trading specific info instead of fundamentals
        st.subheader("Swing Trading Metrics")
        st.info(f"📊 **{symbol}**: Fundamentals not applicable for swing trading analysis. Focus on technical indicators, volatility, and market regime.")

    # Stock Analysis (TipRanks style) - adapted for swing trading
    st.subheader("Stock Analysis")
    price_df = data.get("price_1y")
    details = data.get("details", {})
    industry_key = details.get("industryKey")
    
    # Handle missing fundamentals for swing trading symbols
    fundamentals = data.get("fundamentals", {})
    if symbol in swing_symbols:
        fundamentals = {}  # Use empty fundamentals for swing trading symbols
    
    try:
        analysis = generate_stock_analysis(symbol, price_df, fundamentals, industry_key)
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### Technical Momentum")
            tm = analysis["technical_momentum"]
            st.metric("Score", f"{tm['score']}/10")
            st.write(tm["summary"])
            with st.expander("Details"):
                st.json(tm["details"])
        
        with col2:
            st.markdown("### Financial Strength")
            fs = analysis["financial_strength"]
            st.metric("Score", f"{fs['score']}/10")
            st.write(fs["summary"])
            with st.expander("Details"):
                st.json(fs["details"])
        
        col3, col4 = st.columns(2)
        with col3:
            st.markdown("### Valuation")
            val = analysis["valuation"]
            st.metric("Score", f"{val['score']}/10")
            st.write(val["summary"])
            with st.expander("Details"):
                st.json(val["details"])
        
        with col4:
            st.markdown("### Trend Strength")
            ts = analysis["trend_strength"]
            st.metric("Score", f"{ts['score']}/10")
            st.write(ts["summary"])
            with st.expander("Details"):
                st.json(ts["details"])

    except Exception as e:
        st.warning(f"Stock analysis unavailable for {symbol}: {str(e)}")
        st.info("📊 Swing trading analysis focuses on technical indicators rather than fundamental analysis.")

    # Comprehensive Investment Recommendation (if analysis succeeded)
    if 'analysis' in locals():
        st.subheader("Investment Recommendation")
        use_llm = st.checkbox("Enable LLM Sentiment Analysis", help="Toggle to analyze news sentiment with AI")
        
        # Generate comprehensive report
        news = data.get("news", [])
        try:
            report = generate_comprehensive_report(symbol, analysis, news, use_llm=use_llm)
            
            # Main recommendation
            rec = report["recommendation"]
            col_main, col_conf = st.columns([2, 1])
            with col_main:
                st.markdown(f"### Overall Signal: {rec['signal']}")
                st.write(rec["rationale"])
            with col_conf:
                st.metric("Confidence", rec["confidence"])
                st.metric("Score", f"{rec['weighted_score']}/10")
            
            # Component scores visualization
            st.markdown("#### Component Analysis")
            comp_scores = rec["component_scores"]
            comp_df = pd.DataFrame([
                {"Component": "Technical Momentum", "Score": comp_scores["technical"]},
                {"Component": "Financial Strength", "Score": comp_scores["financial"]},
                {"Component": "Valuation (Inverted)", "Score": comp_scores["valuation"]},
                {"Component": "Growth", "Score": comp_scores["growth"]}
            ])
            st.dataframe(comp_df, use_container_width=True)
            
        except Exception as e:
            st.warning(f"Comprehensive report unavailable for {symbol}: {str(e)}")
    else:
        st.info("📊 Investment recommendation based on swing trading signals available in the Swing Trading Signals section above.")

    # News section (always available)
    st.subheader("Latest News")
    news = data.get("news", [])
    if news:
        for article in news[:5]:  # Show top 5 articles
            st.markdown(f"**{article.get('title', 'No title')}**")
            st.write(f"📅 {article.get('published_at', 'No date')}")
            st.write(f"🔗 {article.get('url', 'No URL')}")
            st.markdown("---")
    else:
        st.info("No news data available")

else:
    st.info("Enter a symbol and click 'Load Data' to begin.")

st.sidebar.markdown("---")
st.sidebar.markdown("Built with Streamlit + Yahoo Finance + Finnhub fallback")
