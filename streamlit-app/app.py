"""
Streamlit Dashboard for AI Trading System
Provides tiered subscription-based feature visibility
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os
import logging

from api_client import (
    get_go_api_client,
    get_python_api_client,
    APIError,
    APIConnectionError,
    APIResponseError
)

logger = logging.getLogger(__name__)

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://go-api:8000")
PYTHON_API_URL = os.getenv("PYTHON_API_URL", "http://python-worker:8001")
SUBSCRIPTION_LEVELS = ["basic", "pro", "elite"]

# Page configuration
st.set_page_config(
    page_title="AI Trading System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Add testbed navigation link
st.sidebar.markdown("---")
st.sidebar.markdown("### 🧪 Testing Tools")
# Note: Testbed is automatically available in sidebar navigation
# Click "🧪 Testbed" in the main sidebar to access it
st.sidebar.info("💡 **Testbed Dashboard** is available in the sidebar navigation above ⬆️")

# Custom CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .subscription-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 0.25rem;
        font-weight: bold;
        font-size: 0.875rem;
    }
    .subscription-basic {
        background-color: #e3f2fd;
        color: #1976d2;
    }
    .subscription-pro {
        background-color: #f3e5f5;
        color: #7b1fa2;
    }
    .subscription-elite {
        background-color: #fff3e0;
        color: #e65100;
    }
    </style>
""", unsafe_allow_html=True)


def get_stock_data(symbol: str, subscription_level: str = "basic"):
    """
    Fetch stock data from API
    
    Args:
        symbol: Stock symbol
        subscription_level: User subscription level
    
    Returns:
        Stock data dictionary
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching stock data for {symbol} (subscription: {subscription_level})")
    
    try:
        client = get_go_api_client()
        return client.get(
            f"api/v1/stock/{symbol}",
            params={"subscription_level": subscription_level}
        )
    except APIError as e:
        logger.error(f"Failed to fetch stock data for {symbol}: {e}")
        raise


def get_portfolio_data(user_id: str, portfolio_id: str, subscription_level: str = "basic"):
    """
    Fetch portfolio data from API
    
    Args:
        user_id: User ID
        portfolio_id: Portfolio ID
        subscription_level: User subscription level
    
    Returns:
        Portfolio data dictionary with holdings and signals as lists
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not user_id or not portfolio_id:
        raise ValueError("user_id and portfolio_id cannot be empty")
    
    logger.info(f"Fetching portfolio {portfolio_id} for user {user_id}")
    
    try:
        client = get_go_api_client()
        data = client.get(
            f"api/v1/portfolio/{user_id}/{portfolio_id}",
            params={"subscription_level": subscription_level}
        )
        
        # Ensure holdings and signals are always lists (data validation)
        if data:
            data['holdings'] = data.get('holdings') or []
            data['signals'] = data.get('signals') or []
        
        return data
    except APIError as e:
        logger.error(f"Failed to fetch portfolio {portfolio_id} for user {user_id}: {e}")
        raise


def get_signal(symbol: str, subscription_level: str = "basic"):
    """
    Fetch trading signal
    
    Args:
        symbol: Stock symbol
        subscription_level: User subscription level
    
    Returns:
        Signal data dictionary
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching signal for {symbol}")
    
    try:
        client = get_go_api_client()
        return client.get(
            f"api/v1/signal/{symbol}",
            params={"subscription_level": subscription_level}
        )
    except APIError as e:
        logger.error(f"Failed to fetch signal for {symbol}: {e}")
        raise


def get_llm_blog(symbol: str):
    """
    Fetch LLM-generated blog/report
    
    Args:
        symbol: Stock symbol
    
    Returns:
        Blog/report data dictionary, or None if not found (404) or other non-critical errors
    
    Raises:
        APIError: If API call fails with non-404 error (fail fast for real errors)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching LLM blog for {symbol}")
    
    try:
        client = get_go_api_client()
        return client.get(f"api/v1/llm_blog/{symbol}", timeout=60)
    except APIResponseError as e:
        # 404 is expected when report doesn't exist yet - not an error
        if e.status_code == 404:
            logger.info(f"LLM blog not found for {symbol} (404) - report may not be generated yet")
            return None
        # Other API errors are real errors - fail fast
        logger.error(f"Failed to fetch LLM blog for {symbol}: {e}")
        raise
    except APIError as e:
        # Connection errors, timeouts, etc. - fail fast
        logger.error(f"Failed to fetch LLM blog for {symbol}: {e}")
        raise


def get_stock_report(symbol: str):
    """
    Fetch TipRanks-style stock report
    
    Args:
        symbol: Stock symbol
    
    Returns:
        Report data dictionary, or None if not found (404) or other non-critical errors
    
    Raises:
        APIError: If API call fails with non-404 error (fail fast for real errors)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching stock report for {symbol}")
    
    try:
        client = get_go_api_client()
        return client.get(f"api/v1/report/{symbol}", timeout=60)
    except APIResponseError as e:
        # 404 is expected when report doesn't exist yet - not an error
        if e.status_code == 404:
            logger.info(f"Stock report not found for {symbol} (404) - report may not be generated yet")
            return None
        # Other API errors are real errors - fail fast
        logger.error(f"Failed to fetch stock report for {symbol}: {e}")
        raise
    except APIError as e:
        # Connection errors, timeouts, etc. - fail fast
        logger.error(f"Failed to fetch stock report for {symbol}: {e}")
        raise


def generate_stock_report(symbol: str):
    """
    Trigger report generation via Python worker
    
    Args:
        symbol: Stock symbol
    
    Returns:
        Generated report data dictionary
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Generating stock report for {symbol}")
    
    try:
        client = get_python_api_client()
        return client.post(
            "api/v1/generate-report",
            json_data={
                "symbol": symbol.upper(),
                "include_llm": True
            },
            timeout=120
        )
    except APIError as e:
        logger.error(f"Failed to generate report for {symbol}: {e}")
        raise


def refresh_data(symbol: str, data_types: list = None, force: bool = False):
    """
    Refresh data on-demand with detailed error tracking
    
    Args:
        symbol: Stock symbol
        data_types: List of data types to refresh
        force: Force refresh even if data is recent
    
    Returns:
        Refresh result dictionary
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    if not data_types:
        data_types = ["price_historical", "fundamentals"]
    
    logger.info(f"Refreshing data for {symbol}: {data_types} (force={force})")
    
    try:
        client = get_python_api_client()
        return client.post(
            "api/v1/refresh-data",
            json_data={
                "symbol": symbol.upper(),
                "data_types": data_types,
                "force": force
            },
            timeout=180
        )
    except APIError as e:
        logger.error(f"Failed to refresh data for {symbol}: {e}")
        raise


def fetch_historical_data(symbol: str, period: str = "1y", calculate_indicators: bool = True):
    """
    Fetch historical data and calculate indicators on-demand (legacy endpoint)
    
    Args:
        symbol: Stock symbol
        period: Historical period (1y, 6mo, etc.)
        calculate_indicators: Whether to calculate indicators
    
    Returns:
        Historical data result dictionary
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching historical data for {symbol} (period: {period}, indicators: {calculate_indicators})")
    
    try:
        client = get_python_api_client()
        return client.post(
            "api/v1/fetch-historical-data",
            json_data={
                "symbol": symbol.upper(),
                "period": period,
                "include_fundamentals": True,
                "include_options": True,
                "calculate_indicators": calculate_indicators
            },
            timeout=180
        )
    except APIError as e:
        logger.error(f"Failed to fetch historical data for {symbol}: {e}")
        raise


def get_fundamentals(symbol: str):
    """
    Fetch fundamental data from API
    
    Args:
        symbol: Stock symbol
    
    Returns:
        Fundamentals data dictionary
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching fundamentals for {symbol}")
    
    try:
        client = get_go_api_client()
        return client.get(f"api/v1/stock/{symbol}/fundamentals", timeout=30)
    except APIError as e:
        logger.error(f"Failed to fetch fundamentals for {symbol}: {e}")
        raise


def get_news(symbol: str):
    """
    Fetch news data from API
    
    Args:
        symbol: Stock symbol
    
    Returns:
        List of news articles
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching news for {symbol}")
    
    try:
        client = get_go_api_client()
        data = client.get(f"api/v1/stock/{symbol}/news", timeout=30)
        return data.get('news', [])
    except APIError as e:
        logger.error(f"Failed to fetch news for {symbol}: {e}")
        raise


def get_earnings(symbol: str):
    """
    Fetch earnings data from API
    
    Args:
        symbol: Stock symbol
    
    Returns:
        List of earnings records
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching earnings for {symbol}")
    
    try:
        client = get_go_api_client()
        data = client.get(f"api/v1/stock/{symbol}/earnings", timeout=30)
        return data.get('earnings', [])
    except APIError as e:
        logger.error(f"Failed to fetch earnings for {symbol}: {e}")
        raise


def get_industry_peers(symbol: str):
    """
    Fetch industry and peers data from API
    
    Args:
        symbol: Stock symbol
    
    Returns:
        Industry peers data dictionary
    
    Raises:
        APIError: If API call fails (fail fast)
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    logger.info(f"Fetching industry peers for {symbol}")
    
    try:
        client = get_go_api_client()
        return client.get(f"api/v1/stock/{symbol}/industry-peers", timeout=30)
    except APIError as e:
        logger.error(f"Failed to fetch industry peers for {symbol}: {e}")
        raise


def get_stock_list(subscription_level: str = "basic"):
    """Get list of stocks with signals (for Pro users)"""
    # This would typically come from a watchlist or portfolio
    # For now, return empty - will be populated from user's holdings
    return []


def plot_stock_chart(data: dict):
    """Plot stock chart with indicators"""
    indicators = data.get("indicators", {})
    
    # Create subplots
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=("Price & Indicators", "RSI"),
        row_heights=[0.7, 0.3]
    )
    
    # Price data (simplified - in real app, fetch historical data)
    dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
    # Mock price data - in production, fetch from raw_market_data
    base_price = indicators.get("sma50") or 100
    prices = [base_price + (i * 0.5) for i in range(100)]
    
    # Plot price
    fig.add_trace(
        go.Scatter(x=dates, y=prices, name="Price", line=dict(color="blue")),
        row=1, col=1
    )
    
    # Plot moving averages if available
    if indicators.get("ema20"):
        fig.add_trace(
            go.Scatter(x=dates[-20:], y=[indicators["ema20"]] * 20, 
                      name="EMA20", line=dict(color="orange", dash="dash")),
            row=1, col=1
        )
    
    if indicators.get("sma50"):
        fig.add_trace(
            go.Scatter(x=dates[-50:], y=[indicators["sma50"]] * 50,
                      name="SMA50", line=dict(color="green", dash="dash")),
            row=1, col=1
        )
    
    if indicators.get("sma200"):
        fig.add_trace(
            go.Scatter(x=dates[-200:], y=[indicators["sma200"]] * 200,
                      name="SMA200", line=dict(color="red", dash="dash")),
            row=1, col=1
        )
    
    # Plot pullback zones (Pro/Elite only)
    if indicators.get("pullback_zone_lower") and indicators.get("pullback_zone_upper"):
        fig.add_trace(
            go.Scatter(x=dates, y=[indicators["pullback_zone_lower"]] * 100,
                      name="Pullback Lower", line=dict(color="gray", dash="dot"),
                      showlegend=False),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=dates, y=[indicators["pullback_zone_upper"]] * 100,
                      name="Pullback Upper", line=dict(color="gray", dash="dot"),
                      fill="tonexty", fillcolor="rgba(128,128,128,0.2)"),
            row=1, col=1
        )
    
    # Plot RSI
    rsi_value = indicators.get("rsi", 50)
    fig.add_trace(
        go.Scatter(x=dates, y=[rsi_value] * 100, name="RSI",
                  line=dict(color="purple")),
        row=2, col=1
    )
    
    # Add RSI overbought/oversold lines
    fig.add_hline(y=70, line_dash="dash", line_color="red", 
                  annotation_text="Overbought", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green",
                  annotation_text="Oversold", row=2, col=1)
    
    fig.update_layout(
        height=600,
        title_text="Stock Analysis",
        showlegend=True
    )
    
    return fig


def main():
    """Main Streamlit app"""
    st.markdown('<div class="main-header">📈 AI Trading System</div>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("Settings")
        
        # Subscription level selector
        subscription_level = st.selectbox(
            "Subscription Level",
            SUBSCRIPTION_LEVELS,
            index=0
        )
        
        # Display subscription badge
        badge_class = f"subscription-{subscription_level}"
        st.markdown(
            f'<span class="subscription-badge {badge_class}">{subscription_level.upper()}</span>',
            unsafe_allow_html=True
        )
        
        st.divider()
        
        # Navigation
        page = st.radio(
            "Navigation",
            ["Stock Analysis", "Portfolio Builder", "Stock List", "Reports"]
        )
    
    # Main content
    if page == "Stock Analysis":
        st.header("Stock Analysis")
        
        # Stock symbol input with data fetch button
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            symbol = st.text_input("Enter Stock Symbol", value="AAPL", placeholder="e.g., AAPL, MSFT, GOOGL")
        
        with col2:
            st.write("")  # Spacing
            fetch_data_button = st.button("📥 Fetch Data", help="Fetch historical data and calculate indicators", use_container_width=True)
        
        with col3:
            st.write("")  # Spacing
            period = st.selectbox("Period", ["1y", "6mo", "3mo", "1mo", "2y", "5y"], index=0, help="Historical data period")
        
        # Fetch historical data if button clicked
        if fetch_data_button and symbol:
            with st.spinner(f"📥 Fetching {period} of historical data for {symbol.upper()}... This may take 1-2 minutes."):
                try:
                    fetch_result = fetch_historical_data(symbol.upper(), period=period, calculate_indicators=True)
                    if fetch_result and fetch_result.get('success'):
                        st.success(f"✅ Data fetched successfully!")
                        st.write(f"**Symbol:** {fetch_result.get('symbol')}")
                        st.write(f"**Period:** {fetch_result.get('period')}")
                        st.write(f"**Data Fetched:** {'✅' if fetch_result.get('data_fetched') else '❌'}")
                        st.write(f"**Indicators Calculated:** {'✅' if fetch_result.get('indicators_calculated') else '❌'}")
                        st.balloons()
                        # Refresh to show new data
                        st.rerun()
                    elif fetch_result:
                        st.warning(f"⚠️ {fetch_result.get('message', 'Data fetch may have failed.')}")
                    else:
                        st.error("❌ Failed to fetch data - no response from API")
                except APIError as e:
                    logger.error(f"API error fetching historical data for {symbol}: {e}")
                    st.error(f"❌ Failed to fetch data: {e}")
                    st.stop()  # Stop execution - fail fast
                except Exception as e:
                    logger.error(f"Unexpected error fetching historical data for {symbol}: {e}", exc_info=True)
                    st.error(f"❌ Unexpected error: {e}")
                    st.stop()  # Stop execution - fail fast
        
        if symbol:
            with st.spinner("Fetching data..."):
                try:
                    data = get_stock_data(symbol.upper(), subscription_level)
                except APIError as e:
                    logger.error(f"API error fetching stock data for {symbol}: {e}")
                    st.error(f"❌ Failed to fetch stock data: {e}")
                    st.stop()  # Stop execution - fail fast
                except Exception as e:
                    logger.error(f"Unexpected error fetching stock data for {symbol}: {e}", exc_info=True)
                    st.error(f"❌ Unexpected error: {e}")
                    st.stop()  # Stop execution - fail fast
                
                if data:
                    indicators = data.get("indicators", {})
                    signal_data = data.get("signal")
                    
                    # Display key metrics
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Signal", signal_data.get("type", "N/A").upper() if signal_data else "N/A")
                    
                    with col2:
                        rsi = indicators.get("rsi")
                        st.metric("RSI", f"{rsi:.1f}" if rsi else "N/A")
                    
                    with col3:
                        trend = indicators.get("long_term_trend", "N/A")
                        st.metric("Long-term Trend", trend.upper() if trend else "N/A")
                    
                    with col4:
                        momentum = indicators.get("momentum_score")
                        if momentum and subscription_level in ["pro", "elite"]:
                            st.metric("Momentum Score", f"{momentum:.1f}")
                        else:
                            st.metric("Momentum Score", "Pro/Elite Only")
                    
                    # Chart
                    st.plotly_chart(plot_stock_chart(data), use_container_width=True)
                    
                    # Signal details
                    if signal_data:
                        st.subheader("Trading Signal")
                        st.write(f"**Type:** {signal_data.get('type', 'N/A').upper()}")
                        st.write(f"**Reason:** {signal_data.get('reason', 'N/A')}")
                        
                        if signal_data.get("pullback_zone") and subscription_level in ["pro", "elite"]:
                            pb = signal_data["pullback_zone"]
                            st.write(f"**Pullback Zone:** ${pb.get('lower', 0):.2f} - ${pb.get('upper', 0):.2f}")
                        
                        if signal_data.get("stop_loss") and subscription_level in ["pro", "elite"]:
                            st.write(f"**Stop Loss:** ${signal_data['stop_loss']:.2f}")
                    
                    # Advanced Analysis Section (Collapsible with Tabs)
                    with st.expander("🔬 Advanced Analysis", expanded=False):
                        if subscription_level == "basic":
                            st.warning("⚠️ Advanced Analysis is available for Pro and Elite subscribers only.")
                        else:
                            # Create tabs for different advanced sections
                            tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
                                "📊 Moving Averages",
                                "📉 MACD & RSI",
                                "📈 Volume",
                                "🧮 ATR & Volatility",
                                "🧠 AI Narrative",
                                "📚 Fundamentals",
                                "🏭 Industry & Peers"
                            ])
                            
                            # Tab 1: Moving Averages
                            with tab1:
                                st.subheader("Moving Averages")
                                
                                # Check if indicators are available
                                ma7 = indicators.get('ma7', 0)
                                ma21 = indicators.get('ma21', 0)
                                ema20 = indicators.get('ema20', 0)
                                sma50 = indicators.get('sma50', 0)
                                ema50 = indicators.get('ema50', 0)
                                sma200 = indicators.get('sma200', 0)
                                
                                if all([v == 0 or v is None for v in [ma7, ma21, ema20, sma50, ema50, sma200]]):
                                    st.warning("⚠️ Indicators not calculated yet. Click '📥 Fetch Data' to calculate indicators.")
                                    if st.button("🔄 Calculate Indicators Now", key="calc_indicators_ma"):
                                        with st.spinner("Calculating indicators..."):
                                            refresh_result = refresh_data(
                                                symbol.upper(),
                                                data_types=["indicators"],
                                                force=True
                                            )
                                            if refresh_result and refresh_result.get('summary', {}).get('total_successful', 0) > 0:
                                                st.success("✅ Indicators calculated! Refreshing...")
                                                st.rerun()
                                            else:
                                                st.error("❌ Failed to calculate indicators")
                                else:
                                    col1, col2 = st.columns(2)
                                    
                                    with col1:
                                        st.write("**Short-term:**")
                                        st.metric("MA7", f"{ma7:.2f}" if ma7 and ma7 > 0 else "N/A")
                                        st.metric("MA21", f"{ma21:.2f}" if ma21 and ma21 > 0 else "N/A")
                                        st.metric("EMA20", f"{ema20:.2f}" if ema20 and ema20 > 0 else "N/A")
                                    
                                    with col2:
                                        st.write("**Long-term:**")
                                        st.metric("SMA50", f"{sma50:.2f}" if sma50 and sma50 > 0 else "N/A")
                                        st.metric("EMA50", f"{ema50:.2f}" if ema50 and ema50 > 0 else "N/A")
                                        st.metric("SMA200", f"{sma200:.2f}" if sma200 and sma200 > 0 else "N/A")
                                    
                                    # Moving average comparison
                                    if all([v and v > 0 for v in [ema20, ema50, sma200]]):
                                        st.write("**Trend Analysis:**")
                                        if ema20 > ema50:
                                            st.success("✅ EMA20 > EMA50 (Bullish short-term)")
                                        else:
                                            st.error("❌ EMA20 < EMA50 (Bearish short-term)")
                                        
                                        if sma50 and sma50 > sma200:
                                            st.success("✅ SMA50 > SMA200 (Golden Cross - Long-term bullish)")
                                        elif sma50:
                                            st.error("❌ SMA50 < SMA200 (Long-term bearish)")
                            
                            # Tab 2: MACD & RSI Charts
                            with tab2:
                                st.subheader("MACD & RSI Analysis")
                                
                                macd = indicators.get('macd', 0)
                                macd_signal = indicators.get('macd_signal', 0)
                                macd_hist = indicators.get('macd_histogram', 0)
                                rsi = indicators.get('rsi', 0)
                                
                                if (macd == 0 or macd is None) and (rsi == 0 or rsi is None):
                                    st.warning("⚠️ MACD & RSI indicators not calculated yet. Click '📥 Fetch Data' to calculate indicators.")
                                    if st.button("🔄 Calculate Indicators Now", key="calc_indicators_macd"):
                                        with st.spinner("Calculating indicators..."):
                                            refresh_result = refresh_data(
                                                symbol.upper(),
                                                data_types=["indicators"],
                                                force=True
                                            )
                                            if refresh_result and refresh_result.get('summary', {}).get('total_successful', 0) > 0:
                                                st.success("✅ Indicators calculated! Refreshing...")
                                                st.rerun()
                                            else:
                                                st.error("❌ Failed to calculate indicators")
                                else:
                                    col1, col2 = st.columns(2)
                                    
                                    with col1:
                                        st.write("**MACD:**")
                                        if macd and macd != 0:
                                            st.metric("MACD Line", f"{macd:.4f}")
                                        else:
                                            st.write("MACD Line: N/A")
                                        if macd_signal and macd_signal != 0:
                                            st.metric("Signal Line", f"{macd_signal:.4f}")
                                        else:
                                            st.write("Signal Line: N/A")
                                        if macd_hist is not None and macd_hist != 0:
                                            color = "green" if macd_hist > 0 else "red"
                                            st.metric("Histogram", f"{macd_hist:.4f}", delta=f"{macd_hist:.4f}")
                                        else:
                                            st.write("Histogram: N/A")
                                        
                                        # MACD Chart
                                        if macd and macd != 0 and macd_signal and macd_signal != 0:
                                            fig_macd = go.Figure()
                                            dates = pd.date_range(end=datetime.now(), periods=50, freq='D')
                                            fig_macd.add_trace(go.Scatter(x=dates, y=[macd] * 50, name="MACD", line=dict(color="blue")))
                                            fig_macd.add_trace(go.Scatter(x=dates, y=[macd_signal] * 50, name="Signal", line=dict(color="orange", dash="dash")))
                                            if macd_hist is not None and macd_hist != 0:
                                                fig_macd.add_bar(x=dates, y=[macd_hist] * 50, name="Histogram", marker_color=["green" if x > 0 else "red" for x in [macd_hist] * 50])
                                            fig_macd.update_layout(height=300, title="MACD Analysis")
                                            st.plotly_chart(fig_macd, use_container_width=True)
                                    
                                    with col2:
                                        st.write("**RSI:**")
                                        if rsi and rsi > 0:
                                            st.metric("RSI", f"{rsi:.2f}")
                                            
                                            # RSI interpretation
                                            if rsi > 70:
                                                st.error("🔴 Overbought (>70)")
                                            elif rsi < 30:
                                                st.success("🟢 Oversold (<30)")
                                            else:
                                                st.info("⚪ Neutral (30-70)")
                                            
                                            # RSI Chart
                                            fig_rsi = go.Figure()
                                            dates = pd.date_range(end=datetime.now(), periods=50, freq='D')
                                            fig_rsi.add_trace(go.Scatter(x=dates, y=[rsi] * 50, name="RSI", line=dict(color="purple")))
                                            fig_rsi.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Overbought")
                                            fig_rsi.add_hline(y=30, line_dash="dash", line_color="green", annotation_text="Oversold")
                                            fig_rsi.add_hline(y=50, line_dash="dot", line_color="gray", annotation_text="Neutral")
                                            fig_rsi.update_layout(height=300, title="RSI Analysis", yaxis_range=[0, 100])
                                            st.plotly_chart(fig_rsi, use_container_width=True)
                                        else:
                                            st.write("RSI: N/A")
                            
                            # Tab 3: Volume Confirmation
                            with tab3:
                                st.subheader("Volume Analysis")
                                
                                # Fetch volume data from API
                                try:
                                    client = get_go_api_client()
                                    volume_data = client.get(f"api/v1/stock/{symbol}/volume", timeout=30)
                                except APIError as e:
                                    logger.error(f"Failed to fetch volume data for {symbol}: {e}")
                                    st.error(f"❌ Failed to fetch volume data: {e}")
                                    volume_data = None
                                
                                if not volume_data or not volume_data.get('data'):
                                    st.warning("⚠️ Volume data not available. Click '📥 Fetch Data' to load historical data.")
                                    if st.button("🔄 Refresh Data", key="refresh_volume"):
                                        with st.spinner("Refreshing data..."):
                                            refresh_result = refresh_data(
                                                symbol.upper(),
                                                data_types=["price_historical"],
                                                force=True
                                            )
                                            if refresh_result and refresh_result.get('summary', {}).get('total_successful', 0) > 0:
                                                st.success("✅ Data refreshed! Reloading...")
                                                st.rerun()
                                else:
                                    volume_points = volume_data.get('data', [])
                                    if volume_points:
                                        # Calculate average volume
                                        volumes = [v.get('volume', 0) for v in volume_points if v.get('volume')]
                                        avg_volume = sum(volumes) / len(volumes) if volumes else 0
                                        latest_volume = volumes[-1] if volumes else 0
                                        
                                        col1, col2 = st.columns(2)
                                        
                                        with col1:
                                            st.write("**Volume Metrics:**")
                                            st.metric("Latest Volume", f"{latest_volume:,.0f}" if latest_volume else "N/A")
                                            st.metric("Average Volume (20d)", f"{avg_volume:,.0f}" if avg_volume else "N/A")
                                            volume_ratio = (latest_volume / avg_volume) if avg_volume > 0 else 0
                                            st.metric("Volume Ratio", f"{volume_ratio:.2f}x", delta=f"{((volume_ratio - 1) * 100):.1f}%")
                                        
                                        with col2:
                                            st.write("**Volume Confirmation:**")
                                            if volume_ratio > 1.5:
                                                st.success("✅ High volume - Strong signal confirmation")
                                            elif volume_ratio > 1.0:
                                                st.info("⚪ Above average volume")
                                            else:
                                                st.warning("⚠️ Low volume - Weak signal")
                                        
                                        # Volume chart
                                        if len(volume_points) > 0:
                                            df_vol = pd.DataFrame(volume_points)
                                            df_vol['date'] = pd.to_datetime(df_vol['date'])
                                            
                                            fig_vol = go.Figure()
                                            fig_vol.add_trace(go.Bar(
                                                x=df_vol['date'],
                                                y=df_vol['volume'],
                                                name="Volume",
                                                marker_color="lightblue"
                                            ))
                                            fig_vol.add_hline(y=avg_volume, line_dash="dash", line_color="orange", annotation_text="Avg Volume")
                                            fig_vol.update_layout(height=400, title="Volume Analysis", xaxis_title="Date", yaxis_title="Volume")
                                            st.plotly_chart(fig_vol, use_container_width=True)
                                    else:
                                        st.info("📊 Volume confirmation helps validate price movements and signals.")
                                        st.write("**Volume Indicators:**")
                                        st.write("- Volume spikes confirm breakouts")
                                        st.write("- Above-average volume = stronger signal")
                                        st.write("- Low volume = weak signal")
                            
                            # Tab 4: ATR & Volatility
                            with tab4:
                                st.subheader("ATR & Volatility Analysis")
                                
                                atr = indicators.get('atr', 0)
                                bb_upper = indicators.get('bb_upper', 0)
                                bb_middle = indicators.get('bb_middle', 0)
                                bb_lower = indicators.get('bb_lower', 0)
                                
                                if (atr == 0 or atr is None) and (bb_upper == 0 or bb_upper is None):
                                    st.warning("⚠️ ATR & Volatility indicators not calculated yet. Click '📥 Fetch Data' to calculate indicators.")
                                    if st.button("🔄 Calculate Indicators Now", key="calc_indicators_atr"):
                                        with st.spinner("Calculating indicators..."):
                                            refresh_result = refresh_data(
                                                symbol.upper(),
                                                data_types=["indicators"],
                                                force=True
                                            )
                                            if refresh_result and refresh_result.get('summary', {}).get('total_successful', 0) > 0:
                                                st.success("✅ Indicators calculated! Refreshing...")
                                                st.rerun()
                                            else:
                                                st.error("❌ Failed to calculate indicators")
                                else:
                                    col1, col2 = st.columns(2)
                                    
                                    with col1:
                                        st.write("**Average True Range (ATR):**")
                                        if atr and atr > 0:
                                            st.metric("ATR", f"{atr:.2f}")
                                            st.write("ATR measures volatility:")
                                            st.write("- Higher ATR = More volatile")
                                            st.write("- Lower ATR = Less volatile")
                                            st.write("- Used for stop-loss calculation")
                                            
                                            # Stop loss calculation
                                            current_price = data.get('current_price') or indicators.get('sma50', 0)
                                            if current_price and current_price > 0:
                                                stop_loss_long = current_price - (atr * 2)
                                                stop_loss_short = current_price + (atr * 2)
                                                st.write("**Stop Loss (2x ATR):**")
                                                st.metric("Long Position", f"${stop_loss_long:.2f}")
                                                st.metric("Short Position", f"${stop_loss_short:.2f}")
                                        else:
                                            st.write("ATR: N/A")
                                
                                    with col2:
                                        st.write("**Bollinger Bands:**")
                                        if bb_upper and bb_upper > 0 and bb_middle and bb_middle > 0 and bb_lower and bb_lower > 0:
                                            st.metric("Upper Band", f"{bb_upper:.2f}")
                                            st.metric("Middle Band (SMA20)", f"{bb_middle:.2f}")
                                            st.metric("Lower Band", f"{bb_lower:.2f}")
                                            
                                            current_price = data.get('current_price') or indicators.get('sma50', bb_middle)
                                            if current_price and current_price > 0:
                                                if current_price > bb_upper:
                                                    st.warning("⚠️ Price above upper band (Overbought)")
                                                elif current_price < bb_lower:
                                                    st.success("✅ Price below lower band (Oversold)")
                                                else:
                                                    st.info("⚪ Price within bands (Normal)")
                                            
                                            # Bollinger Bands Chart
                                            fig_bb = go.Figure()
                                            dates = pd.date_range(end=datetime.now(), periods=50, freq='D')
                                            fig_bb.add_trace(go.Scatter(x=dates, y=[bb_upper] * 50, name="Upper", line=dict(color="red", dash="dash")))
                                            fig_bb.add_trace(go.Scatter(x=dates, y=[bb_middle] * 50, name="Middle", line=dict(color="blue")))
                                            fig_bb.add_trace(go.Scatter(x=dates, y=[bb_lower] * 50, name="Lower", line=dict(color="green", dash="dash"), fill="tonexty", fillcolor="rgba(128,128,128,0.1)"))
                                            if current_price and current_price > 0:
                                                fig_bb.add_trace(go.Scatter(x=dates, y=[current_price] * 50, name="Price", line=dict(color="orange")))
                                            fig_bb.update_layout(height=300, title="Bollinger Bands")
                                            st.plotly_chart(fig_bb, use_container_width=True)
                                        else:
                                            st.write("Bollinger Bands: N/A")
                            
                            # Tab 5: AI Narrative
                            with tab5:
                                st.subheader("🧠 AI-Generated Analysis")
                                
                                if subscription_level == "elite":
                                    try:
                                        llm_data = get_llm_blog(symbol)
                                        if llm_data and llm_data.get('content'):
                                            st.markdown(llm_data['content'])
                                        else:
                                            st.info("🤖 AI narrative will be generated after market data is processed.")
                                            st.write("**What AI Analysis Includes:**")
                                            st.write("- Technical analysis summary")
                                            st.write("- Market sentiment")
                                            st.write("- Risk assessment")
                                            st.write("- Trading recommendations")
                                    except APIError as e:
                                        logger.error(f"Error fetching LLM blog for {symbol}: {e}")
                                        st.error(f"❌ Failed to fetch AI narrative: {e}")
                                        st.info("💡 Try generating a report first using the Reports page.")
                                else:
                                    st.warning("🔒 AI Narrative is available for Elite subscribers only.")
                            
                            # Tab 6: Fundamentals
                            with tab6:
                                st.subheader("📚 Fundamental Analysis")
                                
                                fundamentals = get_fundamentals(symbol)
                                
                                if fundamentals and fundamentals.get('data_available') != False:
                                    col1, col2 = st.columns(2)
                                    
                                    with col1:
                                        if fundamentals.get('market_cap'):
                                            market_cap = fundamentals['market_cap']
                                            if market_cap >= 1e12:
                                                st.metric("Market Cap", f"${market_cap/1e12:.2f}T")
                                            elif market_cap >= 1e9:
                                                st.metric("Market Cap", f"${market_cap/1e9:.2f}B")
                                            else:
                                                st.metric("Market Cap", f"${market_cap/1e6:.2f}M")
                                        
                                        if fundamentals.get('pe_ratio'):
                                            st.metric("P/E Ratio", f"{fundamentals['pe_ratio']:.2f}")
                                        
                                        if fundamentals.get('forward_pe'):
                                            st.metric("Forward P/E", f"{fundamentals['forward_pe']:.2f}")
                                        
                                        if fundamentals.get('dividend_yield'):
                                            st.metric("Dividend Yield", f"{fundamentals['dividend_yield']*100:.2f}%")
                                        
                                        if fundamentals.get('eps'):
                                            st.metric("EPS", f"${fundamentals['eps']:.2f}")
                                    
                                    with col2:
                                        if fundamentals.get('revenue'):
                                            revenue = fundamentals['revenue']
                                            if revenue >= 1e12:
                                                st.metric("Revenue", f"${revenue/1e12:.2f}T")
                                            elif revenue >= 1e9:
                                                st.metric("Revenue", f"${revenue/1e9:.2f}B")
                                            else:
                                                st.metric("Revenue", f"${revenue/1e6:.2f}M")
                                        
                                        if fundamentals.get('profit_margin'):
                                            st.metric("Profit Margin", f"{fundamentals['profit_margin']*100:.2f}%")
                                        
                                        if fundamentals.get('debt_to_equity'):
                                            st.metric("Debt-to-Equity", f"{fundamentals['debt_to_equity']:.2f}")
                                        
                                        if fundamentals.get('current_ratio'):
                                            st.metric("Current Ratio", f"{fundamentals['current_ratio']:.2f}")
                                        
                                        if fundamentals.get('sector'):
                                            st.write(f"**Sector:** {fundamentals['sector']}")
                                        if fundamentals.get('industry'):
                                            st.write(f"**Industry:** {fundamentals['industry']}")
                                    
                                    # Additional metrics
                                    if fundamentals.get('revenue_growth'):
                                        st.metric("Revenue Growth", f"{fundamentals['revenue_growth']*100:.2f}%")
                                    if fundamentals.get('earnings_growth'):
                                        st.metric("Earnings Growth", f"{fundamentals['earnings_growth']*100:.2f}%")
                                    
                                    # News section
                                    news = get_news(symbol)
                                    if news and len(news) > 0:
                                        with st.expander("📰 Recent News", expanded=False):
                                            for article in news[:5]:  # Show top 5
                                                st.write(f"**{article.get('title', 'No title')}**")
                                                if article.get('publisher'):
                                                    st.caption(f"Source: {article['publisher']}")
                                                if article.get('published_date'):
                                                    st.caption(f"Date: {article['published_date']}")
                                                if article.get('link'):
                                                    st.markdown(f"[Read more]({article['link']})")
                                                st.divider()
                                    
                                    # Earnings section
                                    earnings = get_earnings(symbol)
                                    if earnings and len(earnings) > 0:
                                        with st.expander("💰 Earnings History", expanded=False):
                                            earnings_df = pd.DataFrame(earnings)
                                            display_cols = ['earnings_date']
                                            if 'eps_estimate' in earnings_df.columns:
                                                display_cols.append('eps_estimate')
                                            if 'eps_actual' in earnings_df.columns:
                                                display_cols.append('eps_actual')
                                            if 'surprise_percentage' in earnings_df.columns:
                                                display_cols.append('surprise_percentage')
                                            st.dataframe(earnings_df[display_cols], use_container_width=True)
                                else:
                                    st.info("📊 No fundamental data available. Click '📥 Fetch Data' to load data for this symbol.")
                                    
                                    # Show what will be available
                                    st.write("**Key Metrics (when available):**")
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        st.write("- Market Cap")
                                        st.write("- P/E Ratio")
                                        st.write("- Forward P/E")
                                        st.write("- Dividend Yield")
                                        st.write("- EPS")
                                    with col2:
                                        st.write("- Revenue")
                                        st.write("- Profit Margins")
                                        st.write("- Debt-to-Equity")
                                        st.write("- Current Ratio")
                                        st.write("- Sector & Industry")
                            
                            # Tab 7: Industry & Peers
                            with tab7:
                                st.subheader("🏭 Industry & Peer Comparison")
                                
                                try:
                                    peers_data = get_industry_peers(symbol)
                                except APIError as e:
                                    logger.error(f"API error fetching industry peers for {symbol}: {e}")
                                    st.error(f"❌ Failed to fetch industry peers: {e}")
                                    peers_data = None
                                except Exception as e:
                                    logger.error(f"Unexpected error fetching industry peers for {symbol}: {e}", exc_info=True)
                                    st.error(f"❌ Unexpected error: {e}")
                                    peers_data = None
                                
                                if peers_data and (peers_data.get('sector') or peers_data.get('peers')):
                                    if peers_data.get('sector'):
                                        st.write(f"**Sector:** {peers_data['sector']}")
                                    if peers_data.get('industry'):
                                        st.write(f"**Industry:** {peers_data['industry']}")
                                    
                                    if peers_data.get('peers') and len(peers_data['peers']) > 0:
                                        st.subheader("Industry Peers")
                                        peers_df = pd.DataFrame(peers_data['peers'])
                                        
                                        # Format market cap
                                        if 'market_cap' in peers_df.columns:
                                            peers_df['market_cap_formatted'] = peers_df['market_cap'].apply(
                                                lambda x: f"${x/1e9:.2f}B" if x and x >= 1e9 else f"${x/1e6:.2f}M" if x else "N/A"
                                            )
                                        
                                        display_cols = ['symbol', 'name']
                                        if 'market_cap_formatted' in peers_df.columns:
                                            display_cols.append('market_cap_formatted')
                                        if 'sector' in peers_df.columns:
                                            display_cols.append('sector')
                                        
                                        st.dataframe(peers_df[display_cols], use_container_width=True)
                                    else:
                                        st.info("No peer data available yet.")
                                else:
                                    st.info("📊 No industry/peer data available. Click '📥 Fetch Data' to load data for this symbol.")
                                    
                                    st.write("**Analysis Includes:**")
                                    st.write("- Sector performance comparison")
                                    st.write("- Industry peers ranking")
                                    st.write("- Relative strength vs. sector")
                                    st.write("- Market position")
                    
                    # Basic view message
                    if subscription_level == "basic":
                        st.info("💡 Upgrade to Pro or Elite to see advanced metrics, pullback zones, and stop-loss levels!")
    
    elif page == "Portfolio View":
        st.header("Portfolio View")
        
        user_id = st.text_input("User ID", value="user1")
        portfolio_id = st.text_input("Portfolio ID", value="portfolio1")
        
        if user_id and portfolio_id:
            with st.spinner("Fetching portfolio data..."):
                portfolio_data = get_portfolio_data(user_id, portfolio_id, subscription_level)
                
                if portfolio_data:
                    portfolio = portfolio_data.get("portfolio") or {}
                    holdings = portfolio_data.get("holdings") or []
                    signals = portfolio_data.get("signals") or []
                    
                    # Ensure they are lists
                    if not isinstance(holdings, list):
                        holdings = []
                    if not isinstance(signals, list):
                        signals = []
                    
                    st.subheader(f"Portfolio: {portfolio.get('portfolio_name', 'N/A')}")
                    
                    # Holdings table
                    if holdings:
                        st.subheader("Holdings")
                        try:
                            df_holdings = pd.DataFrame(holdings)
                            # Select only columns that exist
                            available_cols = ["stock_symbol", "quantity", "avg_entry_price", "position_type"]
                            display_cols = [col for col in available_cols if col in df_holdings.columns]
                            st.dataframe(df_holdings[display_cols])
                        except Exception as e:
                            logger.error(f"Error displaying holdings: {e}", exc_info=True)
                            st.error(f"❌ Error displaying holdings: {e}")
                            st.json(holdings)
                            raise  # Fail fast - don't continue with invalid data
                    else:
                        st.info("No holdings in this portfolio. Use Portfolio Builder to add stocks.")
                    
                    # Signals
                    if signals:
                        st.subheader("Trading Signals")
                        try:
                            df_signals = pd.DataFrame(signals)
                            st.dataframe(df_signals)
                        except Exception as e:
                            logger.error(f"Error displaying signals: {e}", exc_info=True)
                            st.error(f"❌ Error displaying signals: {e}")
                            st.json(signals)
                            raise  # Fail fast - don't continue with invalid data
                    else:
                        st.info("No signals available for this portfolio. Signals are generated after market data is fetched and indicators are calculated.")
    
    elif page == "Portfolio Builder":
        st.header("🏗️ Portfolio Builder")
        
        user_id = st.text_input("User ID", value="user1")
        portfolio_name = st.text_input("Portfolio Name", value="My Portfolio")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Add Holdings")
            symbol_input = st.text_input("Stock Symbol", placeholder="e.g., AAPL", key="builder_symbol")
            quantity = st.number_input("Quantity", min_value=0.0, value=1.0, step=0.1, key="builder_quantity")
            entry_price = st.number_input("Entry Price", min_value=0.0, value=0.0, step=0.01, key="builder_price")
            position_type = st.selectbox("Position Type", ["long", "short", "call_option", "put_option"], key="builder_position")
            strategy_tag = st.selectbox("Strategy Tag", [None, "covered_call", "protective_put"], key="builder_strategy")
            
            if st.button("Add to Portfolio"):
                st.info("💡 Portfolio management API endpoints will be added to Go API")
                st.success(f"Added {quantity} shares of {symbol_input} at ${entry_price}")
        
        with col2:
            st.subheader("Portfolio Summary")
            st.write("**Features:**")
            st.write("✅ Add/Remove holdings")
            st.write("✅ Track entry prices")
            st.write("✅ Set position types")
            st.write("✅ Apply strategies")
            st.write("✅ Generate signals")
            
            st.info("💡 Full portfolio CRUD operations will be available via API")
    
    elif page == "Stock List":
        st.header("📊 Stock List with Signals")
        
        if subscription_level not in ["pro", "elite"]:
            st.warning("⚠️ Stock List with signals is available for Pro and Elite subscribers only.")
        else:
            user_id = st.text_input("User ID", value="user1", key="stock_list_user")
            portfolio_id = st.text_input("Portfolio ID", value="portfolio1", key="stock_list_portfolio")
            
            if user_id and portfolio_id:
                with st.spinner("Loading stock list..."):
                    portfolio_data = get_portfolio_data(user_id, portfolio_id, subscription_level)
                    
                    if portfolio_data:
                        holdings = portfolio_data.get("holdings") or []
                        signals = portfolio_data.get("signals") or []
                        
                        # Ensure holdings and signals are lists
                        if not isinstance(holdings, list):
                            holdings = []
                        if not isinstance(signals, list):
                            signals = []
                        
                        if holdings:
                            # Create DataFrame with signals
                            stock_list = []
                            for holding in holdings:
                                symbol = holding.get('stock_symbol')
                                if not symbol:
                                    continue
                                
                                # Find corresponding signal (ensure signals is iterable)
                                signal = None
                                if signals:
                                    signal = next((s for s in signals if s and s.get('stock_symbol') == symbol), None)
                                
                                stock_list.append({
                                    "Symbol": symbol,
                                    "Quantity": holding.get('quantity', 0),
                                    "Entry Price": f"${holding.get('avg_entry_price', 0):.2f}",
                                    "Signal": signal.get('signal_type', 'hold').upper() if signal else "HOLD",
                                    "Confidence": f"{signal.get('confidence_score', 0) * 100:.0f}%" if signal else "N/A",
                                    "Stop Loss": f"${signal.get('stop_loss', 0):.2f}" if signal and signal.get('stop_loss') else "N/A",
                                    "Allocation": f"{signal.get('suggested_allocation', 0):.1f}%" if signal and signal.get('suggested_allocation') else "N/A"
                                })
                            
                            df = pd.DataFrame(stock_list)
                            
                            # Color code signals
                            def color_signal(val):
                                if val == 'BUY':
                                    return 'background-color: #90EE90'
                                elif val == 'SELL':
                                    return 'background-color: #FFB6C1'
                                else:
                                    return 'background-color: #D3D3D3'
                            
                            styled_df = df.style.applymap(color_signal, subset=['Signal'])
                            st.dataframe(styled_df, use_container_width=True)
                            
                            # Summary stats
                            col1, col2, col3, col4 = st.columns(4)
                            buy_count = len([s for s in stock_list if s['Signal'] == 'BUY'])
                            sell_count = len([s for s in stock_list if s['Signal'] == 'SELL'])
                            hold_count = len([s for s in stock_list if s['Signal'] == 'HOLD'])
                            
                            with col1:
                                st.metric("Total Holdings", len(holdings))
                            with col2:
                                st.metric("BUY Signals", buy_count, delta=f"{buy_count} stocks")
                            with col3:
                                st.metric("SELL Signals", sell_count, delta=f"{sell_count} stocks")
                            with col4:
                                st.metric("HOLD Signals", hold_count, delta=f"{hold_count} stocks")
                        else:
                            st.info("No holdings in this portfolio. Use Portfolio Builder to add stocks.")
                    else:
                        st.error("Could not load portfolio data")
    
    elif page == "Reports":
        st.header("📄 TipRanks-Style Stock Reports")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            symbol = st.text_input("Enter Stock Symbol", value="AAPL", placeholder="e.g., AAPL, MSFT, GOOGL", key="report_symbol")
        
        with col2:
            st.write("")  # Spacing
            fetch_data_button = st.button("📥 Fetch Data", help="Fetch historical data first", use_container_width=True, key="report_fetch_data")
        
        with col3:
            st.write("")  # Spacing
            generate_button = st.button("🔄 Generate Report", type="primary", use_container_width=True, key="report_generate")
        
        # Fetch historical data if button clicked
        if fetch_data_button and symbol:
            with st.spinner(f"📥 Fetching historical data for {symbol.upper()}... This may take 1-2 minutes."):
                # Use new refresh-data endpoint for better error tracking
                try:
                    refresh_result = refresh_data(
                        symbol.upper(),
                        data_types=["price_historical", "fundamentals", "indicators"],
                        force=True
                    )
                except APIError as e:
                    logger.error(f"API error refreshing data for {symbol}: {e}")
                    st.error(f"❌ Failed to refresh data: {e}")
                    st.stop()  # Stop execution - fail fast
                except Exception as e:
                    logger.error(f"Unexpected error refreshing data for {symbol}: {e}", exc_info=True)
                    st.error(f"❌ Unexpected error: {e}")
                    st.stop()  # Stop execution - fail fast
                
                if refresh_result:
                    summary = refresh_result.get('summary', {})
                    results = refresh_result.get('results', {})
                    
                    if summary.get('total_successful', 0) > 0:
                        st.success(f"✅ Data refresh completed for {symbol.upper()}!")
                        st.write(f"**Successful:** {summary.get('total_successful')}/{summary.get('total_requested')}")
                        
                        # Show what succeeded/failed
                        for data_type, result in results.items():
                            if result:
                                status = result.get('status', 'unknown')
                                if status == 'success':
                                    st.success(f"✅ {data_type.replace('_', ' ').title()}: {result.get('message', '')}")
                                elif status == 'failed':
                                    st.error(f"❌ {data_type.replace('_', ' ').title()}: {result.get('message', '')}")
                                    if result.get('error'):
                                        st.caption(f"   Error: {result.get('error')}")
                        
                        st.info("💡 Now you can generate a report using the 'Generate Report' button!")
                    else:
                        st.error(f"❌ All data refreshes failed for {symbol.upper()}")
                        for data_type, result in results.items():
                            if result and result.get('error'):
                                st.error(f"**{data_type}**: {result.get('error')}")
                else:
                    st.error("❌ Failed to connect to data refresh service. Please check Python worker.")
        
        if symbol:
            # Initialize session state for generated reports
            if 'generated_reports' not in st.session_state:
                st.session_state.generated_reports = {}
            
            # Generate report if button clicked
            if generate_button:
                with st.spinner("🔄 Generating report... This may take 30-60 seconds."):
                    # Trigger report generation
                    gen_result = generate_stock_report(symbol.upper())
                    if gen_result and gen_result.get('success'):
                        st.success(f"✅ Report generated successfully for {symbol.upper()}!")
                        st.balloons()  # Celebration!
                        # Store the generated report
                        st.session_state.generated_reports[symbol.upper()] = gen_result.get('report')
                        # Refresh to show the new report
                        st.rerun()
                    elif gen_result:
                        st.warning(f"⚠️ {gen_result.get('message', 'Report generation may have failed. Please try again.')}")
                    else:
                        st.error("❌ Failed to generate report. Please check:")
                        st.write("1. Python worker is running (port 8001)")
                        st.write("2. Market data exists for this symbol")
                        st.write("3. Database is accessible")
            
            # Check for freshly generated report first
            fresh_report = st.session_state.generated_reports.get(symbol.upper())
            
            # Fetch and display report
            if not fresh_report:
                with st.spinner("Loading report..."):
                    try:
                        report_data = get_stock_report(symbol.upper())
                    except APIError as e:
                        logger.error(f"Error fetching stock report for {symbol}: {e}")
                        st.error(f"❌ Failed to fetch report: {e}")
                        report_data = None
            else:
                # Use the freshly generated report
                report_data = {
                    "report": fresh_report,
                    "symbol": symbol.upper(),
                    "data_available": True
                }
            
            if report_data:
                # Check if we have a report to display
                if report_data.get('report') or fresh_report:
                    report = report_data.get('report') or fresh_report
                    
                    # Simple Summary (Layman-friendly)
                    st.subheader("📋 Simple Summary")
                    st.info(report.get('summary', 'No summary available'))
                    
                    # Trend Status
                    st.subheader("📈 Trend Status")
                    trend_status = report.get('trend_status', {})
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.write("**Short-term**")
                        st.write(trend_status.get('short_term', 'N/A'))
                    with col2:
                        st.write("**Medium-term**")
                        st.write(trend_status.get('medium_term', 'N/A'))
                    with col3:
                        st.write("**Long-term**")
                        st.write(trend_status.get('long_term', 'N/A'))
                    
                    # Signal Clarity
                    st.subheader("🎯 Signal Clarity")
                    signal_clarity = report.get('signal_clarity', {})
                    st.write(f"**Signal:** {signal_clarity.get('signal', 'N/A')}")
                    st.write(f"**Confidence:** {signal_clarity.get('confidence', 'N/A')}")
                    st.write(f"**Why:** {signal_clarity.get('why', 'N/A')}")
                    st.write(f"**Action:** {signal_clarity.get('action', 'N/A')}")
                    
                    if signal_clarity.get('key_factors'):
                        st.write("**Key Factors:**")
                        for factor in signal_clarity['key_factors']:
                            st.write(f"- {factor}")
                    
                    # Technical Analysis
                    with st.expander("🔬 Technical Analysis Details"):
                        tech_analysis = report.get('technical_analysis', {})
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write("**Moving Averages:**")
                            ma_data = tech_analysis.get('moving_averages', {})
                            st.write(f"- EMA20: {ma_data.get('ema20', 'N/A')}")
                            st.write(f"- SMA50: {ma_data.get('sma50', 'N/A')}")
                            st.write(f"- SMA200: {ma_data.get('sma200', 'N/A')}")
                            st.write(f"**Analysis:** {ma_data.get('analysis', 'N/A')}")
                        
                        with col2:
                            st.write("**Momentum:**")
                            momentum_data = tech_analysis.get('momentum', {})
                            st.write(f"- RSI: {momentum_data.get('rsi', 'N/A')}")
                            st.write(f"- MACD: {momentum_data.get('macd', 'N/A')}")
                            st.write(f"**Analysis:** {momentum_data.get('analysis', 'N/A')}")
                    
                    # Risk Assessment
                    with st.expander("⚠️ Risk Assessment"):
                        risk = report.get('risk_assessment', {})
                        st.write(f"**Risk Level:** {risk.get('risk_level', 'N/A')}")
                        st.write(f"**Confidence:** {risk.get('confidence', 'N/A')}")
                        st.write(f"**Stop Loss:** ${risk.get('stop_loss', 'N/A')}")
                        st.write(f"**Recommendation:** {risk.get('recommendation', 'N/A')}")
                    
                    # Recommendation
                    st.subheader("💡 Final Recommendation")
                    recommendation = report.get('recommendation', {})
                    action = recommendation.get('action', 'N/A')
                    
                    if action == 'BUY':
                        st.success(f"✅ **{action}** - Confidence: {recommendation.get('confidence', 'N/A')}")
                    elif action == 'SELL':
                        st.error(f"❌ **{action}** - Confidence: {recommendation.get('confidence', 'N/A')}")
                    else:
                        st.info(f"⚪ **{action}** - Confidence: {recommendation.get('confidence', 'N/A')}")
                    
                    st.write(f"**Reasoning:** {recommendation.get('reasoning', 'N/A')}")
                    st.write(f"**Time Horizon:** {recommendation.get('time_horizon', 'N/A')}")
                    
                    # LLM Narrative (if available)
                    if report.get('llm_narrative'):
                        with st.expander("🧠 AI Narrative"):
                            st.markdown(report['llm_narrative'])
                    
                    # Report metadata
                    st.caption(f"Report generated: {report.get('generated_at', 'N/A')} | Strategy: {report.get('strategy_used', 'N/A')}")
                    
                elif report_data and not report_data.get('data_available'):
                    st.info("📊 No report available yet.")
                    
                    st.write("**Click the '🔄 Generate Report' button above to create a report immediately!**")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**💡 Quick Generate**")
                        st.write("Use the button to generate reports on-demand. Reports include:")
                        st.write("✅ Simple summary")
                        st.write("✅ Trend analysis")
                        st.write("✅ Signal clarity")
                        st.write("✅ Technical details")
                        st.write("✅ AI narrative (if LLM enabled)")
                    
                    with col2:
                        st.write("**⏰ Batch Processing**")
                        st.write("Reports are also automatically generated during nightly batch processing (1 AM).")
                        st.write("")
                        st.write("**📝 Command Line**")
                        st.code(f"""
docker-compose exec python-worker python -c "
from app.database import init_database
from app.services.report_generator import ReportGenerator
init_database()
rg = ReportGenerator()
report = rg.generate_stock_report('{symbol}')
rg.save_report(report)
"
                        """)
                else:
                    st.error("Could not load report. Please try again.")


if __name__ == "__main__":
    # For multi-page app, redirect to Home
    # The main app.py will be replaced with a simple redirect
    # All functionality is now in separate page files
    main()

