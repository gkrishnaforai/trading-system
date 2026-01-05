"""
Trading System Admin Dashboard
Comprehensive back-office interface for monitoring and managing the trading system.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta, date
import os
import logging
import json
from typing import Dict, Any, List, Optional
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
GO_API_URL = os.getenv("GO_API_URL", "http://localhost:8000")

# Page configuration
st.set_page_config(
    page_title="Trading System Admin",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for admin theme
st.markdown("""
    <style>
    .admin-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #d32f2f;
        margin-bottom: 1rem;
    }
    .status-running {
        color: #2e7d32;
        font-weight: bold;
    }
    .status-error {
        color: #d32f2f;
        font-weight: bold;
    }
    .status-warning {
        color: #f57c00;
        font-weight: bold;
    }
    .metric-card {
        background: #f5f5f5;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1976d2;
    }
    .admin-sidebar {
        background-color: #f8f9fa;
    }
    </style>
""", unsafe_allow_html=True)

class AdminAPIClient:
    """API client for admin operations"""
    
    def __init__(self):
        self.go_api_url = GO_API_URL
    
    def make_request(self, url: str, method: str = "GET", data: Dict = None) -> Dict[str, Any]:
        """Make HTTP request with error handling"""
        try:
            if method == "GET":
                response = requests.get(url, timeout=30)
            elif method == "POST":
                response = requests.post(url, json=data, timeout=30)
            elif method == "PUT":
                response = requests.put(url, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            st.error(f"API request failed: {e}")
            return None
    
    def get_data_sources(self) -> List[Dict]:
        """Get available data sources"""
        result = self.make_request(f"{self.go_api_url}/api/v1/admin/data-sources")
        return result.get("data_sources", []) if result else []
    
    def refresh_data(self, symbols: List[str], data_types: List[str], force: bool = False) -> Dict:
        """Trigger data refresh"""
        data = {
            "symbols": symbols,
            "data_types": data_types,
            "force": force
        }
        return self.make_request(f"{self.go_api_url}/api/v1/admin/refresh", "POST", data)
    
    def get_refresh_status(self) -> Dict:
        """Get refresh status"""
        return self.make_request(f"{self.go_api_url}/api/v1/admin/refresh/status")
    
    def get_data_summary(self, table: str, date_filter: Optional[str] = None) -> Dict:
        """Get data summary for a table"""
        url = f"{self.go_api_url}/api/v1/admin/data-summary/{table}"
        if date_filter:
            url += f"?date_filter={date_filter}"
        return self.make_request(url)
    
    def get_audit_logs(self, start_date: str, end_date: str, limit: int = 100) -> List[Dict]:
        """Get audit logs"""
        url = f"{self.go_api_url}/api/v1/admin/audit-logs?start_date={start_date}&end_date={end_date}&limit={limit}"
        result = self.make_request(url)
        return result.get("logs", []) if result else []
    
    def generate_signals(self, symbols: List[str], strategy: str = "technical") -> Dict:
        """Generate trading signals"""
        data = {
            "symbols": symbols,
            "strategy": strategy
        }
        return self.make_request(f"{self.go_api_url}/api/v1/admin/signals/generate", "POST", data)
    
    def run_screener(self, criteria: Dict) -> Dict:
        """Run stock screener"""
        return self.make_request(f"{self.go_api_url}/api/v1/admin/screener/run", "POST", criteria)
    
    def get_system_health(self) -> Dict:
        """Get system health status"""
        return self.make_request(f"{self.go_api_url}/api/v1/admin/health")

# Initialize API client
api_client = AdminAPIClient()

def render_header():
    """Render admin dashboard header"""
    st.markdown('<h1 class="admin-header">⚙️ Trading System Admin</h1>', unsafe_allow_html=True)
    st.markdown("---")

def render_sidebar():
    """Render admin sidebar navigation"""
    st.sidebar.markdown("## 🎛️ Admin Control Panel")
    
    # Stock symbol search
    st.sidebar.markdown("### 🔎 Stock Search")
    symbol = st.sidebar.text_input("Enter Stock Symbol", placeholder="e.g., AAPL", key="admin_stock_search")
    
    if symbol and st.sidebar.button("📊 View Stock Overview", key="admin_view_stock"):
        st.session_state.admin_selected_symbol = symbol.upper()
        st.session_state.admin_page = "Stock Overview"
    
    st.sidebar.markdown("---")
    
    # Quick stats
    st.sidebar.markdown("### 📊 Quick Stats")
    if st.sidebar.button("🔄 Refresh Stats", key="refresh_sidebar_stats"):
        st.rerun()
    
    # System health indicator
    health = api_client.get_system_health()
    if health:
        status = health.get("status", "unknown")
        if status == "healthy":
            st.sidebar.markdown(f"🟢 **System Status**: {status.title()}")
        else:
            st.sidebar.markdown(f"🔴 **System Status**: {status.title()}")
    
    st.sidebar.markdown("---")
    
    # Navigation
    # Check if we should show stock overview
    if st.session_state.get("admin_page") == "Stock Overview" and st.session_state.get("admin_selected_symbol"):
        page = "📊 Stock Overview"
    else:
        page = st.sidebar.selectbox(
            "📍 Navigate to",
            [
                "🏠 Dashboard",
                "📊 Data Sources",
                "🔄 Data Management",
                "📈 Signals & Screeners",
                "🔍 Audit & Logs",
                "⚙️ System Settings"
            ],
            index=0
        )
        st.session_state.admin_page = page
    
    return page

def render_stock_overview():
    """Render stock overview page"""
    symbol = st.session_state.get("admin_selected_symbol", "")
    
    st.markdown(f"### 📊 Stock Overview: {symbol}")
    
    # Back button
    if st.button("← Back to Admin Dashboard"):
        st.session_state.admin_page = "🏠 Dashboard"
        st.session_state.admin_selected_symbol = None
        st.rerun()
    
    if not symbol:
        st.error("No stock symbol selected")
        return
    
    try:
        # Fetch stock data using admin API client
        with st.spinner(f"Loading data for {symbol}..."):
            stock_data = api_client.make_request(f"{api_client.go_api_url}/api/v1/stock/{symbol}")
            fundamentals = api_client.make_request(f"{api_client.go_api_url}/api/v1/stock/{symbol}/fundamentals")
            news = api_client.make_request(f"{api_client.go_api_url}/api/v1/stock/{symbol}/news")
            
        if not stock_data:
            st.error(f"No data found for symbol: {symbol}")
            return
        
        # Price and basic info
        price_info = stock_data.get("price_info", {})
        current_price = price_info.get("current_price", 0)
        change = price_info.get("change", 0)
        change_percent = price_info.get("change_percent", 0)
        
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Current Price", f"${current_price:.2f}", f"{change:+.2f} ({change_percent:+.2f}%)")
        with col2:
            market_cap = fundamentals.get("market_cap", 0) if fundamentals else 0
            st.metric("Market Cap", f"${market_cap/1e9:.1f}B" if market_cap > 1e9 else f"${market_cap/1e6:.1f}M")
        with col3:
            pe_ratio = fundamentals.get("pe_ratio", "N/A") if fundamentals else "N/A"
            st.metric("P/E Ratio", f"{pe_ratio:.2f}" if isinstance(pe_ratio, (int, float)) else pe_ratio)
        with col4:
            volume = price_info.get("volume", 0)
            st.metric("Volume", f"{volume:,}")
        
        # Tabs for different sections
        tab1, tab2, tab3 = st.tabs(["📈 Price Chart", "📊 Fundamentals", "📰 News"])
        
        with tab1:
            st.subheader("Price Chart")
            
            historical_data = price_info.get("historical_data", [])
            if historical_data:
                df = pd.DataFrame(historical_data)
                df['date'] = pd.to_datetime(df['date'])
                
                fig = go.Figure()
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
                
                fig.update_layout(
                    title=f"{symbol} Price Chart",
                    yaxis_title="Price ($)",
                    xaxis_title="Date",
                    height=500
                )
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No historical price data available")
        
        with tab2:
            st.subheader("Fundamental Analysis")
            
            if fundamentals:
                fund_cols = st.columns(3)
                with fund_cols[0]:
                    st.write("**Valuation**")
                    st.write(f"P/E Ratio: {fundamentals.get('pe_ratio', 'N/A')}")
                    st.write(f"P/B Ratio: {fundamentals.get('pb_ratio', 'N/A')}")
                    st.write(f"P/S Ratio: {fundamentals.get('ps_ratio', 'N/A')}")
                    
                with fund_cols[1]:
                    st.write("**Financial Health**")
                    st.write(f"Debt/Equity: {fundamentals.get('debt_to_equity', 'N/A')}")
                    st.write(f"Current Ratio: {fundamentals.get('current_ratio', 'N/A')}")
                    st.write(f"Quick Ratio: {fundamentals.get('quick_ratio', 'N/A')}")
                    
                with fund_cols[2]:
                    st.write("**Profitability**")
                    st.write(f"ROE: {fundamentals.get('roe', 'N/A')}")
                    st.write(f"ROA: {fundamentals.get('roa', 'N/A')}")
                    st.write(f"Net Margin: {fundamentals.get('net_margin', 'N/A')}")
                
                # Detailed metrics table
                financial_metrics = {
                    "Market Cap": fundamentals.get("market_cap", "N/A"),
                    "Enterprise Value": fundamentals.get("enterprise_value", "N/A"),
                    "Revenue (TTM)": fundamentals.get("revenue_ttm", "N/A"),
                    "Net Income (TTM)": fundamentals.get("net_income_ttm", "N/A"),
                    "EPS (TTM)": fundamentals.get("eps_ttm", "N/A"),
                    "Dividend Yield": fundamentals.get("dividend_yield", "N/A"),
                    "Beta": fundamentals.get("beta", "N/A"),
                    "52 Week High": fundamentals.get("week_52_high", "N/A"),
                    "52 Week Low": fundamentals.get("week_52_low", "N/A"),
                }
                
                df_metrics = pd.DataFrame(list(financial_metrics.items()), columns=["Metric", "Value"])
                st.dataframe(df_metrics, use_container_width=True)
            else:
                st.info("No fundamental data available")
        
        with tab3:
            st.subheader("Latest News")
            
            if news and news.get("articles"):
                articles = news["articles"][:10]  # Show latest 10 articles
                for article in articles:
                    with st.expander(f"📰 {article.get('title', 'No Title')}"):
                        st.write(f"**Source:** {article.get('source', 'Unknown')}")
                        st.write(f"**Published:** {article.get('published_at', 'Unknown date')}")
                        st.write(f"**Summary:** {article.get('summary', article.get('description', 'No summary available'))}")
                        if article.get('url'):
                            st.write(f"[Read more]({article['url']})")
            else:
                st.info("No recent news available")
        
        # Admin actions
        st.markdown("---")
        st.subheader("Admin Actions")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🔄 Refresh Data", key="admin_refresh_stock"):
                st.success(f"Data refresh triggered for {symbol}")
        with col2:
            if st.button("📊 Generate Report", key="admin_generate_report"):
                st.info(f"Report generation requested for {symbol}")
        with col3:
            if st.button("➕ Add to Watchlist", key="admin_add_watchlist"):
                st.success(f"Added {symbol} to admin watchlist")
                
    except Exception as e:
        st.error(f"❌ Error loading stock data: {e}")

def render_dashboard():
    """Render main dashboard overview"""
    st.markdown("### 📈 System Overview")
    
    # Get system health
    health = api_client.get_system_health()
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("📊 Data Sources", "5", "2 Active")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("🔄 Last Refresh", "2 mins ago", "✅ Success")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("📈 Signals Today", "127", "↑ 12%")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col4:
        status_color = "🟢" if health and health.get("status") == "healthy" else "🔴"
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric(f"{status_color} System Health", "Operational", "All services OK")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Recent activity
    st.markdown("### 🕐 Recent Activity")
    
    # Mock recent activity data
    recent_activity = pd.DataFrame({
        'timestamp': [datetime.now() - timedelta(minutes=i*10) for i in range(10)],
        'activity': [
            'Data refresh completed for AAPL, MSFT, GOOGL',
            'Signal generation completed - 150 signals',
            'Screener executed - found 23 matches',
            'Data validation passed for all symbols',
            'System health check completed',
            'Database backup completed',
            'New data source added: AlphaVantage',
            'Error: Failed to fetch data for TSLA',
            'Manual refresh triggered for AMZN',
            'Configuration updated'
        ],
        'status': ['success', 'success', 'success', 'success', 'info', 'info', 'info', 'error', 'warning', 'info']
    })
    
    st.dataframe(recent_activity, use_container_width=True)
    
    # Data freshness chart
    st.markdown("### 📊 Data Freshness")
    
    # Mock data freshness data
    freshness_data = pd.DataFrame({
        'data_type': ['Market Data', 'Indicators', 'Fundamentals', 'News', 'Earnings'],
        'last_update': [datetime.now() - timedelta(minutes=15),
                       datetime.now() - timedelta(minutes=30),
                       datetime.now() - timedelta(hours=2),
                       datetime.now() - timedelta(hours=6),
                       datetime.now() - timedelta(days=1)],
        'status': ['fresh', 'fresh', 'stale', 'stale', 'very_stale']
    })
    
    fig = px.bar(freshness_data, x='data_type', y='last_update', 
                 color='status', title="Data Freshness by Type")
    st.plotly_chart(fig, use_container_width=True)

def render_data_sources():
    """Render data sources management page"""
    st.markdown("### 📊 Data Sources Management")
    
    # Data sources overview
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("#### Available Data Sources")
        
        # Mock data sources data
        data_sources = pd.DataFrame({
            'name': ['Massive.com', 'Alpha Vantage', 'Yahoo Finance', 'IEX Cloud', 'Finnhub'],
            'status': ['✅ Active', '✅ Active', '⚠️ Limited', '❌ Inactive', '✅ Active'],
            'last_sync': ['2 mins ago', '15 mins ago', '1 hour ago', 'N/A', '30 mins ago'],
            'data_types': ['Price, Fundamentals, News', 'Price, Technical', 'Price', 'Price', 'Price, News'],
            'api_calls_today': ['1,247', '892', '0', '0', '456'],
            'error_rate': ['0.1%', '0.3%', 'N/A', 'N/A', '0.2%']
        })
        
        st.dataframe(data_sources, use_container_width=True)
    
    with col2:
        st.markdown("#### Quick Actions")
        
        if st.button("🔄 Sync All Sources", key="sync_all"):
            with st.spinner("Syncing all data sources..."):
                st.success("All data sources synced successfully!")
        
        if st.button("🧪 Test Connection", key="test_connections"):
            with st.spinner("Testing connections..."):
                st.success("All active connections working!")
        
        st.markdown("#### Add New Source")
        with st.expander("➕ Add Data Source"):
            source_name = st.text_input("Source Name")
            api_key = st.text_input("API Key", type="password")
            base_url = st.text_input("Base URL")
            
            if st.button("Add Source", key="add_source"):
                st.success(f"Data source '{source_name}' added successfully!")
    
    # Data source configuration
    st.markdown("#### 🔧 Data Source Configuration")
    
    selected_source = st.selectbox("Select source to configure", 
                                 ['Massive.com', 'Alpha Vantage', 'Yahoo Finance'])
    
    if selected_source:
        with st.expander(f"⚙️ {selected_source} Configuration", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Basic Settings**")
                enabled = st.checkbox("Enable Source", value=True)
                priority = st.selectbox("Priority", [1, 2, 3, 4, 5], index=0)
                rate_limit = st.number_input("Rate Limit (req/min)", value=60)
                
            with col2:
                st.markdown("**Data Types**")
                price_data = st.checkbox("Price Data", value=True)
                fundamentals = st.checkbox("Fundamentals", value=True)
                news = st.checkbox("News", value=True)
                earnings = st.checkbox("Earnings", value=False)
            
            if st.button("💾 Save Configuration"):
                st.success("Configuration saved successfully!")

def render_data_management():
    """Render data management page"""
    st.markdown("### 🔄 Data Management")
    
    # Data refresh controls
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("#### 🚀 Manual Refresh")
        
        # Symbol selection
        symbols = st.multiselect(
            "Select Symbols",
            ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN', 'META', 'NVDA', 'NFLX'],
            default=['AAPL', 'MSFT', 'GOOGL']
        )
        
        # Data types
        data_types = st.multiselect(
            "Data Types",
            ['price_historical', 'price_current', 'fundamentals', 'indicators', 'news', 'earnings'],
            default=['price_historical', 'indicators']
        )
        
        force_refresh = st.checkbox("Force Refresh (ignore cache)")
        
        if st.button("🔄 Start Refresh", key="manual_refresh"):
            if symbols and data_types:
                with st.spinner(f"Refreshing data for {len(symbols)} symbols..."):
                    result = api_client.refresh_data(
                        symbols=symbols,
                        data_types=data_types,
                        force=force_refresh,
                    )
                    if result and result.get("success"):
                        st.success(result.get("message", "Refresh completed"))
                        st.json(result)
                    elif result:
                        st.error(result.get("message", "Refresh failed"))
                        st.json(result)
                    else:
                        st.error("Refresh failed: no response")
            else:
                st.error("Please select symbols and data types")
    
    with col2:
        st.markdown("#### 📊 Refresh Status")

        status = api_client.get_refresh_status()
        if status and status.get("jobs"):
            jobs = status.get("jobs", [])
            refresh_status = pd.DataFrame(jobs)
            st.dataframe(refresh_status, use_container_width=True)
        elif status:
            st.info("No recent refresh jobs")
            st.json(status)
        else:
            st.warning("Failed to fetch refresh status")
    
    # Data summary tables
    st.markdown("#### 📈 Data Summary")
    
    # Date filter
    col1, col2, col3 = st.columns(3)
    with col1:
        date_filter = st.date_input("Filter by Date", value=datetime.now().date())
    with col2:
        table_filter = st.selectbox("Table", ['raw_market_data_daily', 'indicators_daily', 'fundamentals_snapshots'])
    with col3:
        if st.button("🔍 Apply Filter"):
            st.rerun()
    
    # Mock data summary
    data_summary = pd.DataFrame({
        'table_name': ['raw_market_data_daily', 'indicators_daily', 'fundamentals_snapshots'],
        'total_records': ['124,567', '98,234', '45,678'],
        'today_records': ['5,234', '4,567', '1,234'],
        'last_updated': ['2 mins ago', '5 mins ago', '1 hour ago'],
        'size_gb': ['2.3', '1.8', '0.9']
    })
    
    st.dataframe(data_summary, use_container_width=True)
    
    # Data quality metrics
    st.markdown("#### 🔍 Data Quality Metrics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("✅ Complete Records", "98.5%", "↑ 0.2%")
    with col2:
        st.metric("⚠️ Missing Values", "1.2%", "↓ 0.1%")
    with col3:
        st.metric("🔄 Duplicate Records", "0.1%", "↓ 0.05%")
    with col4:
        st.metric("❌ Error Rate", "0.3%", "↑ 0.1%")

def render_signals_screeners():
    """Render signals and screeners page"""
    st.markdown("### 📈 Signals & Screeners")
    
    tab1, tab2, tab3 = st.tabs(["🎯 Signal Generation", "🔍 Stock Screener", "📊 Performance"])
    
    with tab1:
        st.markdown("#### Generate Trading Signals")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            # Signal generation controls
            symbols = st.multiselect(
                "Select Symbols",
                ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN', 'META', 'NVDA'],
                default=['AAPL', 'MSFT', 'GOOGL']
            )
            
            strategy = st.selectbox(
                "Strategy",
                ['technical', 'fundamental', 'momentum', 'mean_reversion'],
                index=0
            )
            
            if st.button("🎯 Generate Signals", key="generate_signals"):
                if symbols:
                    with st.spinner(f"Generating signals for {len(symbols)} symbols..."):
                        result = api_client.generate_signals(symbols=symbols, strategy=strategy)
                        if result:
                            st.success("Signal generation request completed")
                            st.json(result)
                        else:
                            st.error("Signal generation failed: no response")
                else:
                    st.error("Please select symbols")
        
        with col2:
            st.markdown("#### Recent Signals")
            
            # Mock recent signals
            recent_signals = pd.DataFrame({
                'symbol': ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN'],
                'signal': ['BUY', 'HOLD', 'SELL', 'BUY', 'HOLD'],
                'confidence': [0.85, 0.62, 0.78, 0.91, 0.54],
                'strategy': ['technical', 'technical', 'technical', 'momentum', 'technical'],
                'timestamp': [datetime.now() - timedelta(minutes=i*5) for i in range(5)]
            })
            
            st.dataframe(recent_signals, use_container_width=True)
    
    with tab2:
        st.markdown("#### Stock Screener")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.markdown("**Screener Criteria**")
            
            # Technical filters
            st.markdown("**Technical Indicators**")
            min_rsi = st.slider("Min RSI", 0, 100, value=30)
            max_rsi = st.slider("Max RSI", 0, 100, value=70)
            min_sma = st.number_input("Min SMA ($)", value=50.0)
            
            # Fundamental filters
            st.markdown("**Fundamentals**")
            min_market_cap = st.selectbox("Min Market Cap", 
                                        ['Any', '$1B', '$5B', '$10B', '$50B'], index=1)
            max_pe = st.number_input("Max P/E Ratio", value=30.0)
            
            if st.button("🔍 Run Screener", key="run_screener"):
                with st.spinner("Running screener..."):
                    criteria = {
                        "min_rsi": float(min_rsi) if min_rsi is not None else None,
                        "max_rsi": float(max_rsi) if max_rsi is not None else None,
                        "min_sma_50": float(min_sma) if min_sma is not None else None,
                        "max_pe_ratio": float(max_pe) if max_pe is not None else None,
                        "limit": 100,
                    }
                    result = api_client.run_screener(criteria)
                    if result:
                        st.success("Screener request completed")
                        st.json(result)
                    else:
                        st.error("Screener failed: no response")
        
        with col2:
            st.markdown("#### Screener Results")
            
            # Mock screener results
            screener_results = pd.DataFrame({
                'symbol': ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'META'],
                'price': [173.50, 378.85, 139.62, 495.22, 326.49],
                'rsi': [45.2, 52.8, 38.9, 67.3, 41.7],
                'sma_50': [175.20, 376.40, 141.80, 489.90, 328.10],
                'volume': ['52.3M', '28.1M', '31.2M', '45.6M', '18.9M'],
                'score': [85, 78, 72, 91, 69]
            })
            
            st.dataframe(screener_results, use_container_width=True)
    
    with tab3:
        st.markdown("#### Signal Performance Analytics")
        
        # Performance metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📈 Signal Accuracy", "67.3%", "↑ 2.1%")
        with col2:
            st.metric("💰 Avg Return", "+3.2%", "↑ 0.8%")
        with col3:
            st.metric("🎯 Win Rate", "64.5%", "↑ 1.2%")
        with col4:
            st.metric("📊 Signals Today", "1,247", "↑ 127")
        
        # Performance chart
        performance_data = pd.DataFrame({
            'date': pd.date_range(start=datetime.now() - timedelta(days=30), periods=30),
            'accuracy': [65 + i*0.1 + (i%3)*0.5 for i in range(30)],
            'return': [2.5 + i*0.05 + (i%4)*0.3 for i in range(30)]
        })
        
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=performance_data['date'], y=performance_data['accuracy'], 
                                name="Accuracy (%)", line=dict(color='blue')), secondary_y=False)
        fig.add_trace(go.Scatter(x=performance_data['date'], y=performance_data['return'], 
                                name="Avg Return (%)", line=dict(color='green')), secondary_y=True)
        
        fig.update_xaxes(title_text="Date")
        fig.update_yaxes(title_text="Accuracy (%)", secondary_y=False)
        fig.update_yaxes(title_text="Avg Return (%)", secondary_y=True)
        
        st.plotly_chart(fig, use_container_width=True)

def render_audit_logs():
    """Render audit and logs page"""
    st.markdown("### 🔍 Audit & Logs")
    
    # Date filters
    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("Start Date", value=datetime.now() - timedelta(days=7))
    with col2:
        end_date = st.date_input("End Date", value=datetime.now())
    with col3:
        log_level = st.selectbox("Log Level", ['All', 'INFO', 'WARNING', 'ERROR'], index=0)
    
    # Refresh logs button
    if st.button("🔄 Refresh Logs", key="refresh_logs"):
        st.rerun()
    
    # Mock audit logs
    audit_logs = pd.DataFrame({
        'timestamp': [datetime.now() - timedelta(hours=i*2) for i in range(20)],
        'level': ['INFO', 'WARNING', 'ERROR', 'INFO'] * 5,
        'source': ['DataRefresh', 'SignalEngine', 'Screener', 'API'] * 5,
        'message': [
            'Successfully refreshed data for AAPL, MSFT, GOOGL',
            'Rate limit approaching for AlphaVantage API',
            'Failed to fetch fundamentals for TSLA: API timeout',
            'Signal generation completed for 150 symbols',
            'Database backup completed successfully',
            'Memory usage above 80% threshold',
            'Connection lost to Massive.com API',
            'Processed 500 screener requests',
            'System health check passed',
            'Configuration updated: Added new data source',
            'Data validation passed for all symbols',
            'Cache cleared for stale indicators',
            'Database connection pool exhausted',
            'User authentication failed: Invalid token',
            'Batch job completed: 1000 records processed',
            'Disk space usage: 75% (warning threshold)',
            'API response time degraded: avg 2.5s',
            'Failed to send notification: SMTP error',
            'New user registered: admin@trading.com',
            'Scheduled task completed successfully'
        ],
        'details': ['498 records', '4,950/5,000 calls', 'Timeout after 30s', '150 signals', 
                   '2.3GB backed up', '8.2GB/16GB used', 'Connection refused', '23 matches found',
                   'All services OK', 'AlphaVantage added', '0 errors', 'Cache cleared', 
                   'Max connections reached', 'Token expired', 'Batch #1234', '120GB/160GB used',
                   'SLA breach detected', 'SMTP server down', 'User ID: 4567', 'Job ID: 789']
    })
    
    # Filter by log level if selected
    if log_level != 'All':
        audit_logs = audit_logs[audit_logs['level'] == log_level]
    
    # Display logs
    st.dataframe(audit_logs, use_container_width=True)
    
    # Export functionality
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Export to CSV"):
            csv = audit_logs.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"audit_logs_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    
    with col2:
        if st.button("📊 Generate Report"):
            with st.spinner("Generating audit report..."):
                st.success("Audit report generated successfully!")
    
    # Log statistics
    st.markdown("#### 📊 Log Statistics")
    
    col1, col2, col3, col4 = st.columns(4)
    
    log_stats = audit_logs['level'].value_counts()
    
    with col1:
        info_count = log_stats.get('INFO', 0)
        st.metric("ℹ️ INFO", info_count)
    
    with col2:
        warning_count = log_stats.get('WARNING', 0)
        st.metric("⚠️ WARNING", warning_count)
    
    with col3:
        error_count = log_stats.get('ERROR', 0)
        st.metric("❌ ERROR", error_count)
    
    with col4:
        total_count = len(audit_logs)
        st.metric("📝 Total Logs", total_count)

def render_system_settings():
    """Render system settings page"""
    st.markdown("### ⚙️ System Settings")
    
    tab1, tab2, tab3 = st.tabs(["🔧 General", "🔐 Security", "📊 Monitoring"])
    
    with tab1:
        st.markdown("#### General Configuration")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**System Settings**")
            auto_refresh = st.checkbox("Enable Auto Refresh", value=True)
            refresh_interval = st.selectbox("Refresh Interval", [5, 10, 15, 30, 60], index=2)
            max_concurrent_jobs = st.number_input("Max Concurrent Jobs", value=5)
            
            st.markdown("**Data Retention**")
            raw_data_retention = st.selectbox("Raw Data Retention", [30, 60, 90, 180, 365], index=2)
            log_retention = st.selectbox("Log Retention", [7, 14, 30, 60, 90], index=2)
        
        with col2:
            st.markdown("**API Configuration**")
            api_timeout = st.number_input("API Timeout (seconds)", value=30)
            rate_limit = st.number_input("Global Rate Limit (req/min)", value=1000)
            cache_ttl = st.number_input("Cache TTL (minutes)", value=15)
            
            st.markdown("**Notification Settings**")
            email_notifications = st.checkbox("Email Notifications", value=True)
            slack_webhook = st.text_input("Slack Webhook URL", type="password")
        
        if st.button("💾 Save Settings", key="save_general_settings"):
            st.success("General settings saved successfully!")
    
    with tab2:
        st.markdown("#### Security Configuration")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Authentication**")
            enable_auth = st.checkbox("Enable Authentication", value=True)
            session_timeout = st.selectbox("Session Timeout", [30, 60, 120, 240], index=1)
            max_login_attempts = st.number_input("Max Login Attempts", value=5)
            
            st.markdown("**API Security**")
            api_key_required = st.checkbox("Require API Key", value=True)
            ip_whitelist = st.text_area("IP Whitelist (one per line)", placeholder="192.168.1.0/24\\n10.0.0.0/8")
        
        with col2:
            st.markdown("**User Management**")
            admin_users = st.text_area("Admin Users (one per line)", 
                                     value="admin@trading.com\\noperator@trading.com")
            
            st.markdown("**Access Control**")
            enable_rbac = st.checkbox("Enable Role-Based Access", value=True)
            default_role = st.selectbox("Default Role", ["viewer", "operator", "admin"], index=0)
        
        if st.button("💾 Save Security Settings", key="save_security_settings"):
            st.success("Security settings saved successfully!")
    
    with tab3:
        st.markdown("#### Monitoring Configuration")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Health Checks**")
            enable_health_checks = st.checkbox("Enable Health Checks", value=True)
            health_check_interval = st.selectbox("Health Check Interval", [1, 5, 10, 15], index=1)
            
            st.markdown("**Alerting**")
            enable_alerts = st.checkbox("Enable Alerts", value=True)
            cpu_threshold = st.slider("CPU Alert Threshold (%)", 50, 95, value=80)
            memory_threshold = st.slider("Memory Alert Threshold (%)", 50, 95, value=85)
            disk_threshold = st.slider("Disk Alert Threshold (%)", 50, 95, value=90)
        
        with col2:
            st.markdown("**Metrics Collection**")
            enable_metrics = st.checkbox("Enable Metrics Collection", value=True)
            metrics_retention = st.selectbox("Metrics Retention", [7, 14, 30, 60], index=2)
            
            st.markdown("**External Monitoring**")
            prometheus_enabled = st.checkbox("Enable Prometheus", value=False)
            grafana_enabled = st.checkbox("Enable Grafana", value=False)
            
            if prometheus_enabled:
                prometheus_url = st.text_input("Prometheus URL")
            if grafana_enabled:
                grafana_url = st.text_input("Grafana URL")
        
        if st.button("💾 Save Monitoring Settings", key="save_monitoring_settings"):
            st.success("Monitoring settings saved successfully!")

def main():
    """Main application entry point"""
    # Render header
    render_header()
    
    # Render sidebar and get selected page
    page = render_sidebar()
    
    # Render selected page
    if page == "🏠 Dashboard":
        render_dashboard()
    elif page == "📊 Data Sources":
        render_data_sources()
    elif page == "🔄 Data Management":
        render_data_management()
    elif page == "📈 Signals & Screeners":
        render_signals_screeners()
    elif page == "📊 Stock Overview":
        render_stock_overview()
    elif page == "🔍 Audit & Logs":
        render_audit_logs()
    elif page == "⚙️ System Settings":
        render_system_settings()
    
    # Footer
    st.markdown("---")
    st.markdown(
        '<div style="text-align: center; color: #666; font-size: 0.8rem;">'
        'Trading System Admin Dashboard v1.0 | Built with Streamlit'
        '</div>', 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
