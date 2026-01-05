"""
Streamlit earnings calendar application with monthly, weekly, daily views and portfolio integration.
"""

import streamlit as st
import sys
import os
import pandas as pd
from datetime import datetime, date, timedelta
from typing import List, Dict, Any
import requests

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.observability.logging import get_logger
from app.clients.go_api_client import GoApiClient, GoApiClientConfig, GoApiError

logger = get_logger("streamlit_earnings_calendar")

st.set_page_config(page_title="Earnings Calendar", layout="wide")

@st.cache_resource
def get_go_api_base_url() -> str:
    return os.environ.get("GO_API_URL") or os.environ.get("GO_API_BASE_URL") or "http://localhost:8000"


@st.cache_resource
def get_go_api_client() -> GoApiClient:
    return GoApiClient(
        get_go_api_base_url(),
        config=GoApiClientConfig(connect_timeout_s=5.0, read_timeout_s=30.0, total_retries=2, backoff_factor=0.3),
    )


def _go_api_url(path: str) -> str:
    return get_go_api_base_url().rstrip("/") + path


def _go_api_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return get_go_api_client().get(path, params=params)
    except GoApiError as e:
        raise RuntimeError(f"Go API request failed ({get_go_api_base_url()}): {e}")


def _go_api_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return get_go_api_client().post(path, payload=payload)
    except GoApiError as e:
        raise RuntimeError(f"Go API request failed ({get_go_api_base_url()}): {e}")

# Helper functions
def format_earnings_date(date_str):
    """Format earnings date for display."""
    if isinstance(date_str, str):
        return date_str
    return str(date_str)

def format_market_cap(market_cap):
    """Format market cap for display."""
    if not market_cap:
        return "N/A"
    if market_cap > 1e12:
        return f"${market_cap/1e12:.1f}T"
    elif market_cap > 1e9:
        return f"${market_cap/1e9:.1f}B"
    elif market_cap > 1e6:
        return f"${market_cap/1e6:.1f}M"
    else:
        return f"${market_cap:,.0f}"

# Sidebar controls
st.sidebar.header("Earnings Calendar Controls")

# View selection
view_type = st.sidebar.selectbox(
    "View Type",
    ["Monthly", "Weekly", "Daily", "Portfolio"],
    help="Select calendar view type"
)

# Date range controls
today = date.today()
if view_type == "Monthly":
    selected_month = st.sidebar.date_input(
        "Select Month",
        value=today.replace(day=1),
        help="Choose month to view"
    )
    start_date = selected_month
    # Calculate end of month
    if selected_month.month == 12:
        end_date = date(selected_month.year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(selected_month.year, selected_month.month + 1, 1) - timedelta(days=1)
    
elif view_type == "Weekly":
    selected_week = st.sidebar.date_input(
        "Select Week Start",
        value=today - timedelta(days=today.weekday()),
        help="Choose week start (Monday)"
    )
    start_date = selected_week
    end_date = selected_week + timedelta(days=6)
    
elif view_type == "Daily":
    selected_date = st.sidebar.date_input(
        "Select Date",
        value=today,
        help="Choose specific date"
    )
    start_date = end_date = selected_date
    
else:  # Portfolio
    days_ahead = st.sidebar.slider(
        "Days Ahead",
        min_value=7,
        max_value=90,
        value=30,
        help="Look ahead for portfolio earnings"
    )
    start_date = today
    end_date = today + timedelta(days=days_ahead)

# Sector filter (optional)
sectors = ["All", "Technology", "Financial Services", "Healthcare", "Consumer Discretionary", "Energy", "Utilities", "Real Estate", "Materials", "Industrial", "Communication Services"]
selected_sector = st.sidebar.selectbox("Filter by Sector", sectors)

# Data refresh button
if st.sidebar.button("Refresh Data"):
    with st.spinner("Refreshing earnings data..."):
        user_id = st.sidebar.text_input("User ID", value="a8c2c1e3-91a7-4d25-9e3c-51e5d0bda721", key="earnings_user_id")
        subscription_level = st.sidebar.selectbox("Subscription", ["basic", "pro", "elite"], index=2, key="earnings_sub")

        scope = st.sidebar.selectbox(
            "Symbol Scope",
            ["manual", "watchlist", "portfolio", "watchlist+portfolio"],
            index=0,
            key="earnings_scope",
        )

        watchlist_id = st.sidebar.text_input("Watchlist ID", value="", key="earnings_watchlist_id")
        portfolio_id = st.sidebar.text_input("Portfolio ID", value="", key="earnings_portfolio_id")

        symbols: List[str] = []
        if scope == "manual":
            manual = st.sidebar.text_area(
                "Symbols (one per line)",
                value="AAPL\nMSFT\nNVDA",
                key="earnings_manual_symbols",
            )
            symbols = [s.strip().upper() for s in manual.split("\n") if s.strip()]
        else:
            params = {
                "user_id": user_id,
                "subscription_level": subscription_level,
            }
            if "watchlist" in scope:
                params["watchlist_id"] = watchlist_id
            if "portfolio" in scope:
                params["portfolio_id"] = portfolio_id

            scope_resp = _go_api_get("/api/v1/symbol-scope/resolve", params=params)
            symbols = [s.strip().upper() for s in scope_resp.get("symbols", []) if s]

        payload = {
            "symbols": symbols or None,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        }
        result = _go_api_post("/api/v1/admin/earnings-calendar/refresh", payload)
        
        if result["status"] == "success":
            st.sidebar.success(f"Refreshed {result['count']} earnings entries")
        else:
            st.sidebar.error(f"Refresh failed: {result.get('error', 'Unknown error')}")

# Main content
st.title("📅 Earnings Calendar")

# Fetch and display data
if view_type == "Portfolio":
    # Portfolio earnings check
    portfolio_symbols = st.text_area(
        "Enter Portfolio Symbols (one per line)",
        value="AAPL\nMSFT\nGOOGL\nTSLA\nNVDA",
        help="Enter your portfolio symbols to check for upcoming earnings"
    ).split('\n')
    
    portfolio_symbols = [s.strip().upper() for s in portfolio_symbols if s.strip()]
    
    if portfolio_symbols:
        portfolio_result = earnings_service.check_portfolio_earnings(portfolio_symbols, days_ahead)
        
        if portfolio_result["has_earnings"]:
            st.warning(f"⚠️ {portfolio_result['count']} portfolio companies have upcoming earnings!")
            
            # Display upcoming earnings
            for earnings in portfolio_result["earnings"]:
                with st.expander(f"{earnings['symbol']} - {earnings['earnings_date']} ({earnings.get('time', 'N/A')})"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Company:** {earnings.get('company_name', earnings['symbol'])}")
                        st.write(f"**Date:** {earnings['earnings_date']}")
                        st.write(f"**Time:** {earnings.get('time', 'N/A')}")
                        st.write(f"**Quarter:** {earnings.get('quarter')} Q{earnings.get('year')}")
                    with col2:
                        st.write(f"**EPS Estimate:** ${earnings.get('eps_estimate', 'N/A')}")
                        st.write(f"**Revenue Estimate:** ${earnings.get('revenue_estimate', 'N/A'):,}" if earnings.get('revenue_estimate') else "N/A")
                        st.write(f"**Market Cap:** {format_market_cap(earnings.get('market_cap'))}")
                        st.write(f"**Sector:** {earnings.get('sector', 'N/A')}")
        else:
            st.success("✅ No portfolio earnings in the selected period")
    
else:
    # Calendar views
    resp = _go_api_get(
        "/api/v1/admin/earnings-calendar",
        params={
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        },
    )
    earnings_data = resp.get("rows", [])
    
    # Filter by sector if selected
    if selected_sector != "All":
        earnings_data = [e for e in earnings_data if e.get('sector') == selected_sector]
    
    # Display summary
    st.subheader(f"Earnings Summary ({start_date} to {end_date})")
    # Summary can be derived locally from returned rows to avoid adding more endpoints.
    summary = {
        "total_companies": len(earnings_data),
        "unique_symbols": len({e.get("symbol") for e in earnings_data if e.get("symbol")}),
        "by_sector": {},
        "by_date": {},
        "market_cap_distribution": {},
    }
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Companies", summary["total_companies"])
    with col2:
        st.metric("Unique Symbols", summary["unique_symbols"])
    with col3:
        st.metric("Sectors Represented", len(summary["by_sector"]))
    with col4:
        if summary["market_cap_distribution"]:
            large_cap = summary["market_cap_distribution"]["large_cap"]
            st.metric("Large Cap (> $10B)", large_cap)
    
    # Display earnings by date
    if earnings_data:
        st.subheader("Earnings by Date")
        
        # Group by date
        df = pd.DataFrame(earnings_data)
        df['earnings_date'] = pd.to_datetime(df['earnings_date'])
        
        for earnings_date, group in df.groupby(df['earnings_date'].dt.date):
            with st.expander(f"{earnings_date} ({len(group)} companies)"):
                # Display as table
                display_df = group[[
                    'symbol', 'company_name', 'time', 'eps_estimate', 'revenue_estimate',
                    'market_cap', 'sector'
                ]].copy()
                
                display_df['market_cap'] = display_df['market_cap'].apply(format_market_cap)
                display_df['revenue_estimate'] = display_df['revenue_estimate'].apply(
                    lambda x: f"${x:,.0f}" if x else "N/A"
                )
                display_df['eps_estimate'] = display_df['eps_estimate'].apply(
                    lambda x: f"${x:.2f}" if x else "N/A"
                )
                
                display_df.columns = [
                    'Symbol', 'Company', 'Time', 'EPS Est.', 'Revenue Est.', 'Market Cap', 'Sector'
                ]
                
                st.dataframe(display_df, use_container_width=True)
    else:
        st.info("No earnings found in the selected period")

# Sector breakdown
if view_type != "Portfolio" and earnings_data:
    st.subheader("Sector Breakdown")
    if summary["by_sector"]:
        sector_df = pd.DataFrame(list(summary["by_sector"].items()), columns=['Sector', 'Count'])
        st.bar_chart(sector_df.set_index('Sector'))

# Export functionality
if earnings_data:
    st.subheader("Export Data")
    col1, col2 = st.columns(2)
    
    with col1:
        csv = pd.DataFrame(earnings_data).to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"earnings_calendar_{start_date}_{end_date}.csv",
            mime="text/csv"
        )
    
    with col2:
        # Create calendar format for export
        calendar_text = "Earnings Calendar\n" + "="*50 + "\n\n"
        for earnings in earnings_data:
            calendar_text += f"{earnings['earnings_date']} - {earnings['symbol']} ({earnings.get('time', 'N/A')})\n"
            calendar_text += f"  {earnings.get('company_name', earnings['symbol'])}\n"
            if earnings.get('eps_estimate'):
                calendar_text += f"  EPS Estimate: ${earnings['eps_estimate']:.2f}\n"
            if earnings.get('revenue_estimate'):
                calendar_text += f"  Revenue Estimate: ${earnings['revenue_estimate']:,.0f}\n"
            calendar_text += "\n"
        
        st.download_button(
            label="Download Text Calendar",
            data=calendar_text,
            file_name=f"earnings_calendar_{start_date}_{end_date}.txt",
            mime="text/plain"
        )

# Footer
st.markdown("---")
st.caption("Data refreshed from Yahoo Finance. Enable LLM sentiment analysis for enhanced insights.")
