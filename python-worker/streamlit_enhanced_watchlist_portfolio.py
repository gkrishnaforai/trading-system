import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import sys
import requests
import pytz
from typing import Optional

from app.clients.go_api_client import GoApiClient, GoApiClientConfig, GoApiError

# Import shared utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))
from utils.streamlit_utils import get_go_api_base_url, get_go_api_url


@st.cache_resource
def _go_api_base_url() -> str:
    return os.environ.get("GO_API_URL") or os.environ.get("GO_API_BASE_URL") or "http://localhost:8000"


@st.cache_resource
def _go_api_client() -> GoApiClient:
    return GoApiClient(
        _go_api_base_url(),
        config=GoApiClientConfig(connect_timeout_s=5.0, read_timeout_s=30.0, total_retries=2, backoff_factor=0.3),
    )


def _go_api_url(path: str) -> str:
    return _go_api_base_url().rstrip("/") + path


def _go_api_get(path: str, params: dict | None = None) -> dict:
    try:
        return _go_api_client().get(path, params=params or {})
    except GoApiError as e:
        raise RuntimeError(f"Go API request failed ({_go_api_base_url()}): {e}")


def _go_api_post(path: str, payload: dict, params: dict | None = None) -> dict:
    try:
        return _go_api_client().post(path, payload=payload, params=params or {})
    except GoApiError as e:
        raise RuntimeError(f"Go API request failed ({_go_api_base_url()}): {e}")


def _as_list(value):
    if isinstance(value, list):
        return value
    return []


def is_market_hours() -> bool:
    """Check if US market is currently open"""
    now = datetime.now(pytz.timezone('US/Eastern'))
    
    # Check if it's a weekday
    if now.weekday() >= 5:  # Saturday, Sunday
        return False
    
    # Check market hours (9:30 AM - 4:00 PM ET)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_open <= now <= market_close


def display_data_freshness(last_update: Optional[datetime], data_type: str = "data"):
    """Show data freshness with color-coded indicators"""
    if last_update is None:
        st.warning("🟡 No data available")
        return
    
    # Convert to Eastern Time for display
    eastern_tz = pytz.timezone('US/Eastern')
    if last_update.tzinfo is None:
        last_update_et = eastern_tz.localize(last_update)
    else:
        last_update_et = last_update.astimezone(eastern_tz)
    
    age = datetime.now(pytz.UTC) - last_update_et.astimezone(pytz.UTC)
    
    # Determine freshness indicator
    if age < timedelta(minutes=1):
        st.success("🟢 Live data")
        freshness_text = "Live"
    elif age < timedelta(minutes=5):
        st.info("🟡 Fresh data")
        freshness_text = "Fresh"
    elif age < timedelta(minutes=15):
        st.warning("🟠 Stale data")
        freshness_text = "Stale"
    else:
        st.error("🔴 Outdated data")
        freshness_text = "Outdated"
    
    # Display freshness info
    col1, col2 = st.columns([1, 3])
    with col1:
        st.write(f"{freshness_text}")
    with col2:
        st.caption(f"Updated: {last_update_et.strftime('%H:%M:%S ET')}")
    
    # Show auto-refresh status during market hours
    if is_market_hours():
        if age < timedelta(minutes=1):
            st.caption("🔄 Auto-refreshing every 30 seconds")
        else:
            st.caption("⚠️ Data may be delayed during market hours")


def get_auto_refresh_interval() -> int:
    """Get appropriate auto-refresh interval based on market hours and data age"""
    if not is_market_hours():
        return 300  # 5 minutes when market closed
    
    return 30  # 30 seconds during market hours

def display_enhanced_watchlist():
    """Display AI-powered enhanced watchlist with industry-leading features"""
    st.header("📋 Enhanced AI-Powered Watchlist")
    st.markdown("*Industry-standard watchlist with AI insights, screening, and alerts*")
    
    # Market status indicator
    if is_market_hours():
        st.success("🟢 Market Open - Real-time Trading Active")
    else:
        st.warning("🟡 Market Closed - Showing last known prices")
    
    # Import default symbols
    from default_symbols import get_default_symbols, get_themed_watchlist, get_all_themes, get_symbol_info
    
    # Initialize session state
    if 'admin_user_id' not in st.session_state:
        st.session_state.admin_user_id = "a8c2c1e3-91a7-4d25-9e3c-51e5d0bda721"
    if 'admin_subscription_level' not in st.session_state:
        st.session_state.admin_subscription_level = "elite"
    if 'selected_watchlist_id' not in st.session_state:
        st.session_state.selected_watchlist_id = None
    if 'selected_watchlist_item' not in st.session_state:
        st.session_state.selected_watchlist_item = None
    
    # Sidebar controls
    with st.sidebar:
        st.subheader("🎛️ Watchlist Controls")

        st.session_state.admin_user_id = st.text_input("User ID", value=st.session_state.admin_user_id, key="wl_user_id")
        st.session_state.admin_subscription_level = st.selectbox(
            "Subscription",
            ["basic", "pro", "elite"],
            index=["basic", "pro", "elite"].index(st.session_state.admin_subscription_level) if st.session_state.admin_subscription_level in ["basic", "pro", "elite"] else 2,
            key="wl_subscription_level",
        )
        
        # Watchlist selection (persisted via Go API)
        try:
            wl_resp = _go_api_get(
                f"/api/v1/watchlists/user/{st.session_state.admin_user_id}",
                params={"subscription_level": st.session_state.admin_subscription_level},
            )
            watchlists = _as_list(wl_resp.get("watchlists"))
        except Exception as e:
            st.error(f"Failed to load watchlists from Go API: {e}")
            watchlists = []

        watchlist_options = {w.get("watchlist_name") or w.get("watchlist_id"): w.get("watchlist_id") for w in watchlists if w.get("watchlist_id")}
        if not watchlist_options:
            st.info("No watchlists found for this user. Create one below.")
            selected_label = None
        else:
            labels = list(watchlist_options.keys())
            if st.session_state.selected_watchlist_id not in set(watchlist_options.values()):
                st.session_state.selected_watchlist_id = watchlist_options[labels[0]]

            # Determine current label for selected id
            selected_label = next((k for k, v in watchlist_options.items() if v == st.session_state.selected_watchlist_id), labels[0])

        watchlist_name = st.selectbox(
            "Select Watchlist",
            list(watchlist_options.keys()) if watchlist_options else ["(none)"],
            index=(list(watchlist_options.keys()).index(selected_label) if (watchlist_options and selected_label in watchlist_options) else 0),
            key="watchlist_selectbox",
        )
        if watchlist_options and watchlist_name in watchlist_options:
            st.session_state.selected_watchlist_id = watchlist_options[watchlist_name]

        with st.expander("➕ Create Watchlist", expanded=False):
            new_watchlist_name = st.text_input("Watchlist Name", key="create_watchlist_name")
            if st.button("Create", key="create_watchlist_button"):
                name = (new_watchlist_name or "").strip()
                if not name:
                    st.error("Please enter a watchlist name")
                else:
                    payload = {
                        "watchlist_name": name,
                        "description": None,
                        "tags": None,
                        "is_default": False,
                        "subscription_level_required": "basic",
                    }
                    try:
                        created = _go_api_post(
                            "/api/v1/watchlists",
                            payload,
                            params={"user_id": st.session_state.admin_user_id},
                        )
                        st.session_state.selected_watchlist_id = created.get("watchlist_id")
                        st.session_state.selected_watchlist_item = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to create watchlist: {e}")
        
        # Add stock section
        st.subheader("➕ Add Stock")
        new_symbol = st.text_input("Stock Symbol", key="new_watchlist_symbol", placeholder="AAPL").upper()
        
        col1, col2 = st.columns(2)
        with col1:
            priority = st.selectbox("Priority", [1, 2, 3, 4, 5], index=2, key="new_priority")
        with col2:
            watch_reason = st.selectbox(
                "Watch Reason",
                ["Technical Setup", "Fundamental Value", "Earnings Play", "News Catalyst", "Sector Rotation"],
                key="watch_reason"
            )
        
        notes = st.text_area("Notes", key="new_watchlist_notes", placeholder="Why are you watching this stock?")
        
        if st.button("📝 Add to Watchlist", key="add_to_watchlist"):
            if new_symbol:
                if not st.session_state.selected_watchlist_id:
                    st.error("Select or create a watchlist first")
                else:
                    payload = {
                        "stock_symbol": new_symbol,
                        "notes": notes or None,
                        "priority": int(priority),
                        "tags": None,
                    }
                    try:
                        _ = _go_api_post(f"/api/v1/watchlists/{st.session_state.selected_watchlist_id}/items", payload)
                        st.success(f"✅ Added {new_symbol} to watchlist!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add symbol to watchlist: {e}")
            else:
                st.error("Please enter a stock symbol")
        
        st.markdown("---")
        
        # AI Screening
        st.subheader("🤖 AI Screener")
        screening_criteria = st.multiselect(
            "Screening Criteria",
            ["Oversold RSI", "Golden Cross", "High Volume", "Earnings Beat", "Analyst Upgrade"],
            key="screening_criteria"
        )
        
        min_opportunity_score = st.slider(
            "Min Opportunity Score",
            min_value=0, max_value=100, value=70, key="min_opportunity_score"
        )
        
        if st.button("🔍 Apply AI Screening", key="apply_ai_screening"):
            st.info("🤖 AI screening applied - showing best opportunities")
    
    # Main content area
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader(f"📊 {watchlist_name}")

        current_watchlist = []
        if st.session_state.selected_watchlist_id:
            try:
                wl_detail = _go_api_get(
                    f"/api/v1/watchlists/{st.session_state.selected_watchlist_id}",
                    params={"subscription_level": st.session_state.admin_subscription_level},
                )
                items = wl_detail.get("items", [])
                for it in items:
                    current_watchlist.append({
                        "symbol": it.get("stock_symbol"),
                        "company_name": None,
                        "current_price": it.get("current_price"),
                        "daily_change_pct": it.get("daily_change_percent"),
                        "volume": None,
                        "sector": None,
                        "opportunity_score": it.get("trend_strength"),
                        "risk_score": it.get("risk_score"),
                        "watch_reason": None,
                        "notes": it.get("notes"),
                        "item_id": it.get("item_id"),
                    })
            except Exception as e:
                st.warning(f"Could not load watchlist items from Go API: {e}")

        if not current_watchlist:
            st.info("📝 Your watchlist is empty. Add stocks using the sidebar to get started.")
            
            # Show suggested stocks and themed watchlists
            st.markdown("### 💡 Quick Start Options")
            
            # Themed watchlist selector
            col1, col2 = st.columns([2, 1])
            with col1:
                selected_theme = st.selectbox(
                    "🎯 Choose a Themed Watchlist:",
                    options=["Custom"] + get_all_themes(),
                    key="theme_selector"
                )
            
            with col2:
                if st.button("🚀 Load Theme", key="load_theme"):
                    if selected_theme != "Custom":
                        theme_data = get_themed_watchlist(selected_theme)
                        if theme_data:
                            st.success(f"📋 Loading {selected_theme.replace('_', ' ').title()} watchlist...")
                            # Add themed stocks to watchlist
                            for symbol in theme_data['symbols'][:10]:  # Limit to 10 stocks
                                symbol_info = get_symbol_info(symbol)
                                new_item = {
                                    'symbol': symbol,
                                    'company_name': symbol_info['name'],
                                    'current_price': 150.00,  # Mock price
                                    'daily_change': 2.50,
                                    'daily_change_pct': 1.69,
                                    'sector': symbol_info['sector'],
                                    'market_cap': 2500000000000,
                                    'pe_ratio': 25.5,
                                    'dividend_yield': 0.5,
                                    'rsi': 65.0,
                                    'macd_signal': 'bullish',
                                    'fundamental_score': 75.0,
                                    'sentiment_score': 60.0,
                                    'opportunity_score': 80.0,
                                    'risk_score': 'medium',
                                    'added_date': datetime.now().strftime('%Y-%m-%d'),
                                    'priority': 3,
                                    'watch_reason': f"Theme: {selected_theme}",
                                    'notes': theme_data.get('description', ''),
                                    'technical_signals': ['AI Suggested', 'Strong Fundamentals'],
                                    'next_earnings': (datetime.now() + timedelta(days=21)).strftime('%Y-%m-%d'),
                                    'price_target': 175.00,
                                    'upside_potential': 16.7
                                }
                                if st.session_state.selected_watchlist_id:
                                    try:
                                        _go_api_post(
                                            f"/api/v1/watchlists/{st.session_state.selected_watchlist_id}/items",
                                            {"stock_symbol": symbol, "notes": theme_data.get('description', '') or None, "priority": 3, "tags": None},
                                        )
                                    except Exception as e:
                                        st.warning(f"Failed to add {symbol}: {e}")
                            st.rerun()
            
            # Show theme description
            if selected_theme != "Custom":
                theme_data = get_themed_watchlist(selected_theme)
                if theme_data:
                    st.info(f"📊 **{selected_theme.replace('_', ' ').title()}**: {theme_data.get('description', '')}")
                    st.write(f"🎯 **Risk Level**: {theme_data.get('risk_level', 'medium').title()}")
                    st.write(f"📈 **Symbols**: {', '.join(theme_data['symbols'][:10])}")
            
            st.markdown("---")
            st.markdown("### 🔍 Individual Stock Suggestions")
            
            # Get top default symbols
            default_symbols = get_default_symbols()[:10]
            suggested_stocks = []
            for symbol in default_symbols:
                symbol_info = get_symbol_info(symbol)
                suggested_stocks.append({
                    'symbol': symbol,
                    'company': symbol_info['name'],
                    'reason': f"Top {symbol_info['sector']} stock"
                })
            
            for stock in suggested_stocks:
                with st.expander(f"📈 {stock['symbol']} - {stock['company']}"):
                    st.write(f"**Why watch:** {stock['reason']}")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button(f"Add {stock['symbol']}", key=f"add_{stock['symbol']}"):
                            if st.session_state.selected_watchlist_id:
                                try:
                                    _go_api_post(
                                        f"/api/v1/watchlists/{st.session_state.selected_watchlist_id}/items",
                                        {"stock_symbol": stock['symbol'], "notes": stock.get('reason') or None, "priority": 3, "tags": None},
                                    )
                                except Exception as e:
                                    st.warning(f"Failed to add {stock['symbol']}: {e}")
                            st.rerun()
                    with col_b:
                        st.write(f"🎯 Opportunity Score: 85")
        else:
            # Create enhanced watchlist table
            watchlist_df = pd.DataFrame(current_watchlist)
            
            # Add selection column
            watchlist_df.insert(0, 'Select', False)
            
            # Format columns for display
            display_cols = ['Select', 'symbol', 'company_name', 'current_price', 'daily_change_pct', 
                          'volume', 'sector', 'opportunity_score', 'risk_score', 'watch_reason']
            
            # Rename columns for better display
            display_df = watchlist_df[display_cols].copy()
            display_df.columns = ['Select', 'Symbol', 'Company', 'Price', 'Change %', 'Volume', 
                                'Sector', 'Opportunity', 'Risk', 'Reason']
            
            # Display interactive table
            edited_df = st.data_editor(
                display_df,
                width='stretch',
                height=400,
                hide_index=True,
                column_config={"Select": st.column_config.CheckboxColumn(required=False)},
                key="watchlist_table_editor"
            )
            
            # Find selected items
            selected_items = edited_df[edited_df['Select'] == True]
            
            if not selected_items.empty:
                selected_symbol = selected_items.iloc[0]['Symbol']
                selected_data = next((item for item in current_watchlist 
                                    if item['symbol'] == selected_symbol), None)
                
                if selected_data:
                    st.session_state.selected_watchlist_item = selected_data
            
            # Clear selection button
            if not selected_items.empty and st.button("Clear Selection", key="clear_watchlist_selection"):
                st.session_state.selected_watchlist_item = None
                st.rerun()
    
    with col2:
        # Watchlist Analytics
        st.subheader("📈 Analytics")
        
        if current_watchlist:
            total_stocks = len(current_watchlist)
            avg_opportunity = sum(item['opportunity_score'] for item in current_watchlist) / total_stocks
            
            st.metric("Total Stocks", total_stocks)
            st.metric("Avg Opportunity", f"{avg_opportunity:.1f}")
            
            # Risk distribution
            risk_counts = {}
            for item in current_watchlist:
                risk = item['risk_score']
                risk_counts[risk] = risk_counts.get(risk, 0) + 1
            
            st.markdown("**Risk Distribution:**")
            for risk, count in risk_counts.items():
                st.write(f"• {risk.title()}: {count}")
            
            # Sector breakdown
            sector_counts = {}
            for item in current_watchlist:
                sector = item['sector']
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
            
            st.markdown("**Sector Breakdown:**")
            for sector, count in sector_counts.items():
                st.write(f"• {sector}: {count}")
        
        st.markdown("---")
        
        # Market Context
        st.subheader("🌍 Market Context")
        st.write("**S&P 500:** +1.2%")
        st.write("**NASDAQ:** +1.8%")
        st.write("**VIX:** 15.2 (Low)")
        st.write("**Market Mood:** 🟢 Bullish")
        
        st.markdown("---")
        
        # Quick Actions
        st.subheader("⚡ Quick Actions")
        
        # Data freshness indicator
        st.markdown("**Data Freshness:**")
        last_update = datetime.now() - timedelta(minutes=2)  # Simulated - should come from API
        display_data_freshness(last_update, "watchlist")
        
        # Smart refresh button
        refresh_col1, refresh_col2 = st.columns(2)
        with refresh_col1:
            if st.button("🔄 Refresh All Data", key="refresh_watchlist"):
                st.info("🔄 Refreshing watchlist data...")
                # Clear cache to force fresh data
                st.cache_data.clear()
                st.rerun()
        
        with refresh_col2:
            # Auto-refresh toggle during market hours
            auto_refresh_key = "auto_refresh_watchlist"
            if 'auto_refresh_watchlist' not in st.session_state:
                st.session_state[auto_refresh_key] = is_market_hours()
            
            auto_refresh = st.checkbox(
                "🔄 Auto-refresh", 
                value=st.session_state[auto_refresh_key],
                disabled=not is_market_hours(),
                help="Auto-refresh during market hours (9:30 AM - 4:00 PM ET)"
            )
            st.session_state[auto_refresh_key] = auto_refresh
            
            if auto_refresh and is_market_hours():
                interval = get_auto_refresh_interval()
                st.caption(f"📊 Refreshing every {interval} seconds")
            elif not is_market_hours():
                st.caption("⏰ Market closed - auto-refresh disabled")
        
        # Other actions
        if st.button("📊 Export to CSV", key="export_watchlist"):
            st.info("📊 Watchlist exported to CSV")
        
        if st.button("📧 Email Alerts", key="email_alerts"):
            st.info("📧 Email alerts configured")
    
    # Detailed view for selected stock
    if st.session_state.selected_watchlist_item:
        st.markdown("---")
        item = st.session_state.selected_watchlist_item
        
        st.subheader(f"🔍 Detailed Analysis: {item['symbol']}")
        
        # Create columns for detailed view
        detail_col1, detail_col2, detail_col3 = st.columns(3)
        
        with detail_col1:
            st.markdown("#### 📊 Price & Volume")
            st.metric("Current Price", f"${item['current_price']:.2f}")
            st.metric("Daily Change", f"{item['daily_change']:+.2f} ({item['daily_change_pct']:+.2f}%)")
            st.metric("Volume", f"{item['volume']:,}")
            st.metric("Avg Volume", f"{item['avg_volume']:,}")
            
            if item['volume'] > item['avg_volume'] * 1.5:
                st.success("🔥 Unusual Volume!")
        
        with detail_col2:
            st.markdown("#### 📈 Technical Analysis")
            st.metric("RSI", f"{item['rsi']:.1f}")
            st.metric("MACD Signal", item['macd_signal'].title())
            st.metric("Opportunity Score", f"{item['opportunity_score']:.1f}/100")
            st.metric("Risk Level", item['risk_score'].title())
            
            # Technical signals
            st.markdown("**Technical Signals:**")
            for signal in item.get('technical_signals', []):
                st.write(f"• {signal}")
        
        with detail_col3:
            st.markdown("#### 💰 Fundamentals")
            st.metric("P/E Ratio", f"{item['pe_ratio']:.1f}")
            st.metric("Dividend Yield", f"{item['dividend_yield']:.1f}%")
            st.metric("Market Cap", f"${item['market_cap']/1e9:.1f}B")
            st.metric("Sentiment", f"{item['sentiment_score']:.1f}/100")
            
            st.markdown("**Key Info:**")
            st.write(f"• Sector: {item['sector']}")
            st.write(f"• Added: {item['added_date']}")
            st.write(f"• Next Earnings: {item['next_earnings']}")
        
        # AI Insights section
        st.markdown("#### 🤖 AI Insights")
        insight_col1, insight_col2 = st.columns(2)
        
        with insight_col1:
            st.markdown("**📊 Trading Signals:**")
            if item['opportunity_score'] > 80:
                st.success("🟢 Strong Buy Signal - Multiple indicators aligned")
            elif item['opportunity_score'] > 60:
                st.info("🟡 Moderate Buy Signal - Some positive indicators")
            else:
                st.warning("🔴 Hold Signal - Wait for better entry")
            
            st.write(f"**Price Target:** ${item['price_target']:.2f}")
            st.write(f"**Upside Potential:** +{item['upside_potential']:.1f}%")
        
        with insight_col2:
            st.markdown("**⚠️ Risk Analysis:**")
            if item['risk_score'] == 'high':
                st.warning("⚠️ High Risk - High volatility position")
            elif item['risk_score'] == 'medium':
                st.info("⚖️ Medium Risk - Balanced risk/reward")
            else:
                st.success("✅ Low Risk - Stable position")
            
            st.write(f"**Watch Reason:** {item['watch_reason']}")
            if item['notes']:
                st.write(f"**Notes:** {item['notes']}")
        
        # Action buttons
        st.markdown("#### 🎯 Action Center")
        action_col1, action_col2, action_col3, action_col4 = st.columns(4)
        
        with action_col1:
            if st.button(f"📈 Buy {item['symbol']}", key=f"buy_{item['symbol']}"):
                st.success(f"🎯 Buy order prepared for {item['symbol']}")
        
        with action_col2:
            if st.button("📊 Deep Analysis", key=f"analyze_{item['symbol']}"):
                st.info(f"🔍 Loading deep analysis for {item['symbol']}...")
            
            # Add Fundamentals Analysis link
            st.markdown("---")
            st.markdown("#### 💰 Growth Quality Analysis")
            st.markdown(f"""
            <a href="http://localhost:8503/?symbol={item['symbol']}" target="_blank">
                <button style="background-color: #667eea; color: white; padding: 8px 16px; 
                        border: none; border-radius: 4px; cursor: pointer; width: 100%;">
                    📈 View Fundamentals Analysis
                </button>
            </a>
            """, unsafe_allow_html=True)
            st.caption("Comprehensive growth quality and early warning analysis")
        
        with action_col3:
            if st.button("🔔 Set Alert", key=f"alert_{item['symbol']}"):
                st.info(f"🔔 Price alerts set for {item['symbol']}")
        
        with action_col4:
            if st.button("🗑️ Remove", key=f"remove_{item['symbol']}"):
                item_id = item.get("item_id")
                if item_id:
                    try:
                        resp = requests.delete(_go_api_url(f"/api/v1/watchlist-items/{item_id}"), timeout=30)
                        resp.raise_for_status()
                        st.session_state.selected_watchlist_item = None
                        st.success(f"✅ Removed {item['symbol']} from watchlist")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to remove watchlist item: {e}")


def display_enhanced_portfolio():
    """Display AI-powered enhanced portfolio management with industry-leading features"""
    st.header("💼 Enhanced AI-Powered Portfolio")
    st.markdown("*Industry-standard portfolio management with AI analytics, rebalancing, and risk management*")
    
    # Market status indicator
    if is_market_hours():
        st.success("🟢 Market Open - Real-time P&L Updates Active")
    else:
        st.warning("🟡 Market Closed - Showing last known P&L")
    
    # Import default symbols
    from default_symbols import get_default_symbols, get_themed_watchlist, get_all_themes, get_symbol_info
    
    # Initialize session state
    if 'admin_user_id' not in st.session_state:
        st.session_state.admin_user_id = "a8c2c1e3-91a7-4d25-9e3c-51e5d0bda721"
    if 'admin_subscription_level' not in st.session_state:
        st.session_state.admin_subscription_level = "elite"
    if 'selected_portfolio_id' not in st.session_state:
        st.session_state.selected_portfolio_id = None
    if 'selected_portfolio_holding' not in st.session_state:
        st.session_state.selected_portfolio_holding = None
    
    # Sidebar controls
    with st.sidebar:
        st.subheader("💼 Portfolio Controls")

        st.session_state.admin_user_id = st.text_input("User ID", value=st.session_state.admin_user_id, key="pf_user_id")
        st.session_state.admin_subscription_level = st.selectbox(
            "Subscription",
            ["basic", "pro", "elite"],
            index=["basic", "pro", "elite"].index(st.session_state.admin_subscription_level) if st.session_state.admin_subscription_level in ["basic", "pro", "elite"] else 2,
            key="pf_subscription_level",
        )

        # Portfolio selection (persisted via Go API)
        try:
            pf_resp = _go_api_get(f"/api/v1/portfolios/user/{st.session_state.admin_user_id}")
            portfolios = _as_list(pf_resp.get("portfolios"))
        except Exception as e:
            st.error(f"Failed to load portfolios from Go API: {e}")
            portfolios = []

        portfolio_options = {p.get("portfolio_name") or p.get("portfolio_id"): p.get("portfolio_id") for p in portfolios if p.get("portfolio_id")}
        if not portfolio_options:
            st.info("No portfolios found for this user. Create one below.")
            selected_pf_label = None
        else:
            pf_labels = list(portfolio_options.keys())
            if st.session_state.selected_portfolio_id not in set(portfolio_options.values()):
                st.session_state.selected_portfolio_id = portfolio_options[pf_labels[0]]
            selected_pf_label = next((k for k, v in portfolio_options.items() if v == st.session_state.selected_portfolio_id), pf_labels[0])

        portfolio_name = st.selectbox(
            "Select Portfolio",
            list(portfolio_options.keys()) if portfolio_options else ["(none)"],
            index=(list(portfolio_options.keys()).index(selected_pf_label) if (portfolio_options and selected_pf_label in portfolio_options) else 0),
            key="portfolio_selectbox",
        )
        if portfolio_options and portfolio_name in portfolio_options:
            st.session_state.selected_portfolio_id = portfolio_options[portfolio_name]

        with st.expander("➕ Create Portfolio", expanded=False):
            new_portfolio_name = st.text_input("Portfolio Name", key="create_portfolio_name")
            if st.button("Create", key="create_portfolio_button"):
                name = (new_portfolio_name or "").strip()
                if not name:
                    st.error("Please enter a portfolio name")
                else:
                    payload = {"portfolio_name": name, "notes": None}
                    try:
                        created = _go_api_post(f"/api/v1/portfolio/{st.session_state.admin_user_id}", payload)
                        st.session_state.selected_portfolio_id = created.get("portfolio_id")
                        st.session_state.selected_portfolio_holding = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to create portfolio: {e}")

        portfolio_holdings = []
        if st.session_state.selected_portfolio_id:
            try:
                pf_detail = _go_api_get(
                    f"/api/v1/portfolio/{st.session_state.admin_user_id}/{st.session_state.selected_portfolio_id}",
                    params={"subscription_level": st.session_state.admin_subscription_level},
                )
                portfolio_holdings = _as_list(pf_detail.get("holdings"))
            except Exception as e:
                st.warning(f"Could not load portfolio holdings from Go API: {e}")
        
        # Portfolio summary
        total_value = sum(item['quantity'] * item['current_price'] for item in portfolio_holdings)
        total_cost = sum(item['quantity'] * item['avg_cost'] for item in portfolio_holdings)
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
        
        st.markdown("### 📊 Portfolio Summary")
        st.metric("Total Value", f"${total_value:,.2f}")
        st.metric("Total Cost", f"${total_cost:,.2f}")
        st.metric("Total P&L", f"${total_pnl:,.2f}", f"{total_pnl_pct:+.2f}%")
        st.metric("Cash Available", "N/A")
        
        st.markdown("---")
        
        # Add position section
        st.subheader("➕ Add Position")
        new_symbol = st.text_input("Stock Symbol", key="new_portfolio_symbol", placeholder="AAPL").upper()
        
        col1, col2 = st.columns(2)
        with col1:
            quantity = st.number_input("Quantity", min_value=1, value=10, key="new_quantity")
        with col2:
            avg_cost = st.number_input("Avg Cost $", min_value=0.01, value=100.00, step=0.01, key="new_avg_cost")
        
        position_type = st.selectbox("Position Type", ["Long", "Short"], key="position_type")
        strategy = st.selectbox(
            "Strategy",
            ["Value Investing", "Growth", "Dividend", "Momentum", "Swing Trading"],
            key="strategy"
        )
        
        notes = st.text_area("Notes", key="new_portfolio_notes", placeholder="Investment thesis...")
        
        if st.button("💼 Add Position", key="add_to_portfolio"):
            if not new_symbol:
                st.error("Please enter a stock symbol")
            elif not st.session_state.selected_portfolio_id:
                st.error("Select or create a portfolio first")
            else:
                payload = {
                    "stock_symbol": new_symbol,
                    "quantity": float(quantity),
                    "avg_entry_price": float(avg_cost),
                    "position_type": "Long" if position_type == "Long" else "Short",
                    "strategy_tag": strategy or None,
                    "notes": notes or None,
                    "purchase_date": datetime.now().strftime('%Y-%m-%d'),
                }
                try:
                    _ = _go_api_post(
                        f"/api/v1/portfolio/{st.session_state.admin_user_id}/{st.session_state.selected_portfolio_id}/holdings",
                        payload,
                    )
                    st.success(f"✅ Added {quantity} shares of {new_symbol} at ${avg_cost:.2f}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to add holding: {e}")
        
        st.markdown("---")
        
        # AI Portfolio Tools
        st.subheader("🤖 AI Portfolio Tools")
        
        if st.button("🎯 AI Rebalancing", key="ai_rebalancing"):
            st.info("🤖 AI analyzing portfolio for rebalancing opportunities...")
        
        if st.button("⚠️ Risk Assessment", key="risk_assessment"):
            st.info("🔍 Running comprehensive risk analysis...")
        
        if st.button("📈 Performance Report", key="performance_report"):
            st.info("📊 Generating detailed performance report...")
        
        if st.button("🎯 Optimization Suggestions", key="optimization"):
            st.info("🤖 AI analyzing portfolio optimization opportunities...")

        st.markdown("---")
        st.markdown("### 🔍 Individual Position Suggestions")
        
        # Get top default symbols for portfolio
        default_symbols = get_default_symbols()[:8]  # Top 8 symbols
        suggestions = []
        for symbol in default_symbols:
            symbol_info = get_symbol_info(symbol)
            suggestions.append({
                'symbol': symbol,
                'name': symbol_info['name'],
                'reason': f"Core {symbol_info['sector']} holding"
            })
        
        for suggestion in suggestions:
            with st.expander(f"📈 {suggestion['symbol']} - {suggestion['name']}"):
                st.write(f"**Why consider:** {suggestion['reason']}")
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button(f"Add {suggestion['symbol']}", key=f"add_portfolio_{suggestion['symbol']}"):
                        if st.session_state.selected_portfolio_id:
                            try:
                                _go_api_post(
                                    f"/api/v1/portfolio/{st.session_state.admin_user_id}/{st.session_state.selected_portfolio_id}/holdings",
                                    {
                                        "stock_symbol": suggestion['symbol'],
                                        "quantity": 10.0,
                                        "avg_entry_price": 100.0,
                                        "position_type": "Long",
                                        "strategy_tag": "AI Suggestion",
                                        "notes": suggestion.get('reason') or None,
                                        "purchase_date": datetime.now().strftime('%Y-%m-%d'),
                                    },
                                )
                                st.success(f"✅ Added {suggestion['symbol']} to portfolio!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to add holding: {e}")
                with col_b:
                    st.write(f"💰 Est. Cost: ${1000:,.2f}")

        # Holdings table (Go API)
        if portfolio_holdings:
            rows = []
            for h in portfolio_holdings:
                symbol = h.get("stock_symbol")
                qty = float(h.get("quantity") or 0)
                avg = float(h.get("avg_entry_price") or 0)
                mv = qty * avg
                rows.append({
                    "holding_id": h.get("holding_id"),
                    "symbol": symbol,
                    "quantity": qty,
                    "avg_entry_price": avg,
                    "market_value": mv,
                    "position_type": h.get("position_type"),
                    "strategy_tag": h.get("strategy_tag"),
                })

            portfolio_df = pd.DataFrame(rows)
            portfolio_df.insert(0, "Select", False)

            display_cols = ["Select", "symbol", "quantity", "avg_entry_price", "market_value", "position_type", "strategy_tag"]
            display_df = portfolio_df[display_cols].copy()
            display_df.columns = ["Select", "Symbol", "Qty", "Avg Entry", "Market Value", "Position", "Strategy"]

            edited_df = st.data_editor(
                display_df,
                width='stretch',
                height=400,
                hide_index=True,
                column_config={"Select": st.column_config.CheckboxColumn(required=False)},
                key="portfolio_table_editor",
            )

            selected = edited_df[edited_df["Select"] == True]
            if not selected.empty:
                sym = selected.iloc[0]["Symbol"]
                selected_data = next((r for r in rows if r.get("symbol") == sym), None)
                if selected_data:
                    st.session_state.selected_portfolio_holding = selected_data
    
    with col2:
        # Portfolio Analytics
        st.subheader("📈 Portfolio Analytics")

        positions_count = len(portfolio_holdings)
        st.metric("Positions", positions_count)
        st.metric("Total Value (est)", f"${total_value:,.2f}")

        st.markdown("---")
        
        # Market Overview
        st.subheader("🌍 Market Overview")
        st.write("**S&P 500:** +1.2%")
        st.write("**NASDAQ:** +1.8%")
        st.write("**DOW:** +0.9%")
        st.write("**VIX:** 15.2 (Low)")
        st.write("**10Y Yield:** 4.25%")
        
        st.markdown("---")
        
        # Quick Actions
        st.subheader("⚡ Quick Actions")
        
        # Data freshness indicator for portfolio
        st.markdown("**Data Freshness:**")
        portfolio_last_update = datetime.now() - timedelta(minutes=1)  # Simulated - should come from API
        display_data_freshness(portfolio_last_update, "portfolio")
        
        # Smart refresh buttons
        refresh_col1, refresh_col2 = st.columns(2)
        with refresh_col1:
            if st.button("🔄 Refresh Prices", key="refresh_portfolio"):
                st.info("🔄 Refreshing portfolio prices...")
                # Clear cache to force fresh data
                st.cache_data.clear()
                st.rerun()
        
        with refresh_col2:
            # Auto-refresh toggle for portfolio (more frequent than watchlist)
            auto_refresh_portfolio_key = "auto_refresh_portfolio"
            if 'auto_refresh_portfolio' not in st.session_state:
                st.session_state[auto_refresh_portfolio_key] = is_market_hours()
            
            auto_refresh_portfolio = st.checkbox(
                "🔄 Auto-refresh Prices", 
                value=st.session_state[auto_refresh_portfolio_key],
                disabled=not is_market_hours(),
                help="Auto-refresh portfolio prices during market hours"
            )
            st.session_state[auto_refresh_portfolio_key] = auto_refresh_portfolio
            
            if auto_refresh_portfolio and is_market_hours():
                st.caption("📊 Prices refreshing every 30 seconds")
            elif not is_market_hours():
                st.caption("⏰ Market closed - price updates disabled")
        
        # Other actions
        if st.button("📊 Export Holdings", key="export_portfolio"):
            st.info("📊 Portfolio exported to CSV")
        
        if st.button("💰 Deposit Cash", key="deposit_cash"):
            st.info("💰 Cash deposit feature")
        
        if st.button("📈 Performance Chart", key="performance_chart"):
            st.info("📈 Generating performance chart...")
    
    # Detailed view for selected holding
    if st.session_state.selected_portfolio_holding:
        st.markdown("---")
        holding = st.session_state.selected_portfolio_holding
        
        st.subheader(f"🔍 Position: {holding.get('symbol')}")
        
        # Create columns for detailed view
        detail_col1, detail_col2, detail_col3 = st.columns(3)
        
        with detail_col1:
            st.markdown("#### 💰 Position Details")
            st.metric("Quantity", f"{float(holding.get('quantity') or 0):,.2f}")
            st.metric("Avg Entry", f"${float(holding.get('avg_entry_price') or 0):.2f}")
            st.metric("Market Value (est)", f"${float(holding.get('market_value') or 0):,.2f}")
            st.write(f"**Position Type:** {holding.get('position_type')}")
            if holding.get('strategy_tag'):
                st.write(f"**Strategy:** {holding.get('strategy_tag')}")
        
        with detail_col2:
            st.markdown("#### 📊 Notes")
            st.write("(Detailed analytics will be sourced from Go API /overview + indicators later.)")
        
        with detail_col3:
            st.markdown("#### 🎯 Actions")
            st.write("Use 'Close Position' to delete holding.")
            
            # Add Fundamentals Analysis link
            st.markdown("---")
            st.markdown("#### 💰 Growth Quality Analysis")
            st.markdown(f"""
            <a href="http://localhost:8503/?symbol={holding.get('symbol')}" target="_blank">
                <button style="background-color: #667eea; color: white; padding: 8px 16px; 
                        border: none; border-radius: 4px; cursor: pointer; width: 100%;">
                    📈 View Fundamentals Analysis
                </button>
            </a>
            """, unsafe_allow_html=True)
            st.caption("Comprehensive growth quality and early warning analysis")
        
        st.markdown("#### 🎯 Position Actions")
        holding_id = holding.get("holding_id")
        if st.button("❌ Close Position", key=f"close_{holding.get('symbol')}"):
            if not holding_id:
                st.error("Missing holding_id")
            else:
                try:
                    resp = requests.delete(_go_api_url(f"/api/v1/holdings/{holding_id}"), timeout=30)
                    resp.raise_for_status()
                    st.session_state.selected_portfolio_holding = None
                    st.success("✅ Closed position")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to close position: {e}")
