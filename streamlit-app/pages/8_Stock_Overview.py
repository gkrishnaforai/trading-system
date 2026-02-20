"""
Yahoo-like Stock Overview Page
Comprehensive stock dashboard with fundamentals, charts, and news
"""
import streamlit as st
import sys
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar
from api_client import get_go_api_client, APIError

setup_page_config("Stock Overview", "📊")

st.title("📊 Stock Overview")

# Sidebar
subscription_level = render_sidebar()

symbol_from_url = (st.query_params.get("symbol") or "").upper()
alert_event_id = st.query_params.get("alert_event_id")

if symbol_from_url:
    st.session_state["overview_symbol"] = symbol_from_url

# Stock selection
col1, col2 = st.columns([1, 1])
with col1:
    symbol = st.text_input("Enter Stock Symbol", value="AAPL", key="overview_symbol").upper()
with col2:
    if st.button("Load Overview", key="load_overview", type="primary"):
        st.session_state["overview_symbol"] = symbol
        st.rerun()

# Use symbol from session state if available
if "overview_symbol" in st.session_state:
    symbol = st.session_state["overview_symbol"]

if not symbol:
    st.info("👈 Enter a stock symbol to view comprehensive overview")
    st.stop()

try:
    client = get_go_api_client()
    
    # Fetch comprehensive stock data
    with st.spinner(f"Loading data for {symbol}..."):
        params = {"subscription_level": subscription_level}
        if alert_event_id:
            params["alert_event_id"] = alert_event_id

        stock_context = client.get(f"api/v1/stock/{symbol}/alert-context", params=params)
        stock_data = stock_context.get("stock") if isinstance(stock_context, dict) else None
        fundamentals = stock_context.get("fundamentals") if isinstance(stock_context, dict) else None
        news = stock_context.get("news") if isinstance(stock_context, dict) else []
        grade_actions = stock_context.get("grade_actions") if isinstance(stock_context, dict) else []
        
    if not stock_data:
        st.error(f"No data found for symbol: {symbol}")
        st.stop()

    pinned_alert = stock_context.get("pinned_alert") if isinstance(stock_context, dict) else None
    if pinned_alert:
        st.markdown("### 🔔 Alert")
        with st.expander(pinned_alert.get("alert_name") or pinned_alert.get("alert_type") or "Alert", expanded=True):
            st.json(pinned_alert)
    
    # Header with key metrics
    st.header(f"{symbol} Overview")
    
    # Price and basic info
    price_info = (stock_data or {}).get("price_info", {})
    current_price = price_info.get("current_price", 0)
    change = price_info.get("change", 0)
    change_percent = price_info.get("change_percent", 0)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Current Price", f"${current_price:.2f}", f"{change:+.2f} ({change_percent:+.2f}%)")
    with col2:
        market_cap = (fundamentals or {}).get("market_cap", 0) if isinstance(fundamentals, dict) else 0
        st.metric("Market Cap", f"${market_cap/1e9:.1f}B" if market_cap > 1e9 else f"${market_cap/1e6:.1f}M")
    with col3:
        pe_ratio = (fundamentals or {}).get("pe_ratio", "N/A") if isinstance(fundamentals, dict) else "N/A"
        st.metric("P/E Ratio", f"{pe_ratio:.2f}" if isinstance(pe_ratio, (int, float)) else pe_ratio)
    with col4:
        volume = price_info.get("volume", 0)
        st.metric("Volume", f"{volume:,}")
    
    # Tabs for different sections
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Price Chart", "📊 Fundamentals", "📰 News", "📊 Analyst Actions", "🏭 Industry"])
    
    with tab1:
        st.subheader("Price Chart (1 Year)")
        
        # Get historical data from price_info
        historical_data = price_info.get("historical_data", [])
        if historical_data:
            df = pd.DataFrame(historical_data)
            df['date'] = pd.to_datetime(df['date'])
            
            # Create interactive chart
            fig = go.Figure()
            
            # Candlestick or line chart based on data availability
            if all(col in df.columns for col in ['open', 'high', 'low', 'close']):
                fig.add_trace(go.Candlestick(
                    x=df['date'],
                    open=df['open'],
                    high=df['high'],
                    low=df['low'],
                    close=df['close'],
                    name='Price'
                ))
            else:
                fig.add_trace(go.Scatter(
                    x=df['date'],
                    y=df['close'] if 'close' in df.columns else df['price'],
                    mode='lines',
                    name='Price'
                ))
            
            # Add volume if available
            if 'volume' in df.columns:
                fig.add_trace(go.Scatter(
                    x=df['date'],
                    y=df['volume'],
                    mode='lines',
                    name='Volume',
                    yaxis='y2',
                    line=dict(color='rgba(0,0,255,0.3)')
                ))
            
            fig.update_layout(
                title=f"{symbol} Price Chart",
                yaxis_title="Price ($)",
                xaxis_title="Date",
                height=500,
                yaxis2=dict(
                    title="Volume",
                    overlaying='y',
                    side='right'
                ) if 'volume' in df.columns else None
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No historical price data available")
    
    with tab2:
        st.subheader("Fundamental Analysis")
        
        # Key fundamentals
        fund_cols = st.columns(3)
        with fund_cols[0]:
            st.write("**Valuation**")
            st.write(f"P/E Ratio: {(fundamentals or {}).get('pe_ratio', 'N/A') if isinstance(fundamentals, dict) else 'N/A'}")
            st.write(f"P/B Ratio: {(fundamentals or {}).get('pb_ratio', 'N/A') if isinstance(fundamentals, dict) else 'N/A'}")
            st.write(f"P/S Ratio: {(fundamentals or {}).get('ps_ratio', 'N/A') if isinstance(fundamentals, dict) else 'N/A'}")
            
        with fund_cols[1]:
            st.write("**Financial Health**")
            st.write(f"Debt/Equity: {(fundamentals or {}).get('debt_to_equity', 'N/A') if isinstance(fundamentals, dict) else 'N/A'}")
            st.write(f"Current Ratio: {(fundamentals or {}).get('current_ratio', 'N/A') if isinstance(fundamentals, dict) else 'N/A'}")
            st.write(f"Quick Ratio: {(fundamentals or {}).get('quick_ratio', 'N/A') if isinstance(fundamentals, dict) else 'N/A'}")
            
        with fund_cols[2]:
            st.write("**Profitability**")
            st.write(f"ROE: {(fundamentals or {}).get('roe', 'N/A') if isinstance(fundamentals, dict) else 'N/A'}")
            st.write(f"ROA: {(fundamentals or {}).get('roa', 'N/A') if isinstance(fundamentals, dict) else 'N/A'}")
            st.write(f"Net Margin: {(fundamentals or {}).get('net_margin', 'N/A') if isinstance(fundamentals, dict) else 'N/A'}")
        
        # Financial metrics table
        st.write("**Detailed Financial Metrics**")
        financial_metrics = {
            "Market Cap": (fundamentals or {}).get("market_cap", "N/A") if isinstance(fundamentals, dict) else "N/A",
            "Enterprise Value": (fundamentals or {}).get("enterprise_value", "N/A") if isinstance(fundamentals, dict) else "N/A",
            "Revenue (TTM)": (fundamentals or {}).get("revenue_ttm", "N/A") if isinstance(fundamentals, dict) else "N/A",
            "Net Income (TTM)": (fundamentals or {}).get("net_income_ttm", "N/A") if isinstance(fundamentals, dict) else "N/A",
            "EPS (TTM)": (fundamentals or {}).get("eps_ttm", "N/A") if isinstance(fundamentals, dict) else "N/A",
            "Dividend Yield": (fundamentals or {}).get("dividend_yield", "N/A") if isinstance(fundamentals, dict) else "N/A",
            "Beta": (fundamentals or {}).get("beta", "N/A") if isinstance(fundamentals, dict) else "N/A",
            "52 Week High": (fundamentals or {}).get("week_52_high", "N/A") if isinstance(fundamentals, dict) else "N/A",
            "52 Week Low": (fundamentals or {}).get("week_52_low", "N/A") if isinstance(fundamentals, dict) else "N/A",
        }
        
        df_metrics = pd.DataFrame(list(financial_metrics.items()), columns=["Metric", "Value"])
        st.dataframe(df_metrics, use_container_width=True)
    
    with tab3:
        st.subheader("Latest News")
        
        if isinstance(news, list) and news:
            for article in news[:10]:
                with st.expander(f"📰 {article.get('title', 'No Title')}"):
                    st.write(f"**Source:** {article.get('publisher', 'Unknown')}")
                    st.write(f"**Published:** {article.get('published_date', 'Unknown date')}")
                    if article.get('link'):
                        st.write(f"[Read more]({article['link']})")
        else:
            st.info("No recent news available")
    
    with tab4:
        st.subheader("Analyst Actions (Upgrades / Downgrades / Initiations)")

        if isinstance(grade_actions, list) and grade_actions:
            df_actions = pd.DataFrame(
                [
                    {
                        "Date": a.get("grade_date"),
                        "Firm": a.get("grading_company"),
                        "Action": a.get("action"),
                        "From": a.get("previous_grade"),
                        "To": a.get("new_grade"),
                    }
                    for a in grade_actions
                ]
            )
            st.dataframe(df_actions, use_container_width=True, hide_index=True)
        else:
            st.info("No recent analyst actions available")
    
    with tab5:
        st.subheader("Industry & Peers")
        
        # Industry information
        industry = (fundamentals or {}).get("industry") if isinstance(fundamentals, dict) else None
        sector = (fundamentals or {}).get("sector") if isinstance(fundamentals, dict) else None
        industry = industry or "Unknown"
        sector = sector or "Unknown"
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Industry Information**")
            st.write(f"Industry: {industry}")
            st.write(f"Sector: {sector}")
        
        with col2:
            st.write("**Action Buttons**")
            if st.button("Add to Watchlist", key="add_to_watchlist"):
                st.success("✅ Added to watchlist!")
            if st.button("Generate Report", key="generate_report"):
                st.info("📊 Report generation requested...")
        
        # Industry peers (if available via API)
        try:
            peers_data = client.get(f"api/v1/stock/{symbol}/industry-peers")
            if peers_data and peers_data.get("peers"):
                st.write("**Industry Peers**")
                peers = peers_data["peers"][:8]  # Show up to 8 peers
                peer_cols = st.columns(4)
                for i, peer in enumerate(peers):
                    with peer_cols[i % 4]:
                        st.write(f"**{peer.get('symbol', 'N/A')}**")
                        st.write(f"{peer.get('company_name', 'N/A')}")
                        st.write(f"P/E: {peer.get('pe_ratio', 'N/A')}")
        except:
            st.info("Industry peers data not available")

except APIError as e:
    st.error(f"❌ API Error: {e}")
except Exception as e:
    st.error(f"❌ Error loading stock data: {e}")

# Footer
st.markdown("---")
st.markdown("*Data provided by the trading system API. Refresh for latest information.*")
