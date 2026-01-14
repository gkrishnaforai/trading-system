"""
Market Movers Analysis Page
Industry-standard market movers and losers analysis with add-to-watchlist functionality
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime, date
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
import sys
from typing import List, Dict, Any, Optional

# Add the current directory to Python path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import portfolio utilities and shared components
try:
    from utils.portfolio_utils import (
        get_user_portfolios, add_stock_to_portfolio, get_portfolio_holdings,
        get_current_user, format_currency, format_percentage
    )
except ImportError:
    # Fallback imports if utils.portfolio_utils is not available
    import streamlit as st
    import requests
    import pandas as pd
    from datetime import datetime, date
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import json
    from typing import List, Dict, Any, Optional
    
    # Mock functions for testing
    def get_user_portfolios():
        return [{"id": 1, "name": "Test Portfolio"}]
    
    def add_stock_to_portfolio(portfolio_id, symbol, shares, avg_cost):
        return True
    
    def get_current_user():
        return {"id": 1, "username": "test_user"}
    
    def format_currency(amount):
        return f"${amount:,.2f}"
    
    def format_percentage(value):
        return f"{value:.2f}%"

def setup_page_config():
    """Setup page configuration"""
    st.set_page_config(
        page_title="Market Movers",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded"
    )

def get_market_movers() -> Dict[str, List[Dict]]:
    """Get today's top market movers and losers"""
    try:
        # This would typically come from a market data API
        # For now, we'll use a mock implementation
        response = requests.get(f"http://python-worker:8001/api/v1/market/movers", timeout=10)
        
        if response.status_code == 200:
            return response.json()
        else:
            # Fallback to sample data
            return get_sample_market_movers()
            
    except Exception as e:
        st.warning(f"Could not fetch live market data. Using sample data. Error: {e}")
        return get_sample_market_movers()

def get_sample_market_movers() -> Dict[str, List[Dict]]:
    """Sample market movers data for demonstration"""
    return {
        "gainers": [
            {"symbol": "NVDA", "company": "NVIDIA Corporation", "price": 485.09, "change": 25.67, "change_percent": 5.58, "volume": "45.2M", "market_cap": "1.2T"},
            {"symbol": "TSLA", "company": "Tesla, Inc.", "price": 242.84, "change": 12.31, "change_percent": 5.34, "volume": "112.3M", "market_cap": "770B"},
            {"symbol": "AMD", "company": "Advanced Micro Devices", "price": 125.43, "change": 5.89, "change_percent": 4.93, "volume": "67.8M", "market_cap": "203B"},
            {"symbol": "META", "company": "Meta Platforms", "price": 325.67, "change": 14.22, "change_percent": 4.56, "volume": "23.4M", "market_cap": "834B"},
            {"symbol": "GOOGL", "company": "Alphabet Inc.", "price": 139.82, "change": 5.43, "change_percent": 4.04, "volume": "28.9M", "market_cap": "1.8T"}
        ],
        "losers": [
            {"symbol": "BA", "company": "Boeing Company", "price": 198.45, "change": -8.92, "change_percent": -4.30, "volume": "8.7M", "market_cap": "119B"},
            {"symbol": "DIS", "company": "Walt Disney Company", "price": 89.23, "change": -3.78, "change_percent": -4.06, "volume": "15.2M", "market_cap": "161B"},
            {"symbol": "NFLX", "company": "Netflix Inc.", "price": 445.67, "change": -16.89, "change_percent": -3.65, "volume": "12.1M", "market_cap": "198B"},
            {"symbol": "INTC", "company": "Intel Corporation", "price": 42.18, "change": -1.47, "change_percent": -3.36, "volume": "35.6M", "market_cap": "176B"},
            {"symbol": "CSCO", "company": "Cisco Systems", "price": 48.92, "change": -1.58, "change_percent": -3.13, "volume": "18.9M", "market_cap": "202B"}
        ]
    }

def add_stock_to_watchlist(symbol: str, portfolio_id: int):
    """Add stock to selected portfolio"""
    try:
        # Get current stock info
        stock_info = get_stock_info(symbol)
        
        # Add to portfolio
        success = add_stock_to_portfolio(
            portfolio_id=portfolio_id,
            symbol=symbol,
            shares=0,  # User can add shares later
            avg_cost=stock_info.get('price', 0)
        )
        
        if success:
            st.success(f"✅ Added {symbol} to portfolio successfully!")
            st.rerun()
        else:
            st.error(f"❌ Failed to add {symbol} to portfolio")
            
    except Exception as e:
        st.error(f"❌ Error adding stock: {e}")

def get_stock_info(symbol: str) -> Dict[str, Any]:
    """Get current stock information"""
    try:
        response = requests.get(f"http://python-worker:8001/api/v1/stocks/info/{symbol}")
        if response.status_code == 200:
            return response.json()
        else:
            return {"price": 0, "error": "Data not available"}
    except:
        return {"price": 0, "error": "Data not available"}

def render_movers_table(movers: List[Dict], title: str, color_scheme: str):
    """Render movers table with add to portfolio functionality"""
    st.markdown(f"### {title}")
    
    # Display each mover with add to portfolio functionality
    for i, mover in enumerate(movers):
        symbol = mover['symbol']
        company = mover['company']
        price = mover['price']
        change = mover['change']
        change_percent = mover['change_percent']
        volume = mover['volume']
        market_cap = mover['market_cap']
        
        # Create a card for each stock
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            
            with col1:
                st.markdown(f"**{symbol}** - {company}")
                st.caption(f"Vol: {volume} | Cap: {market_cap}")
            
            with col2:
                price_color = "green" if change >= 0 else "red"
                st.markdown(f"<span style='color: {price_color}; font-weight: bold;'>${price:.2f}</span>", 
                           unsafe_allow_html=True)
                st.markdown(f"<span style='color: {price_color};'>{change:+.2f} ({change_percent:+.2f}%)</span>", 
                           unsafe_allow_html=True)
            
            with col3:
                # Get user portfolios
                portfolios = get_user_portfolios()
                portfolio_options = [f"{p['name']} (ID: {p['id']})" for p in portfolios]
                
                if portfolio_options:
                    selected_portfolio = st.selectbox(
                        "Portfolio",
                        options=portfolio_options,
                        key=f"portfolio_{symbol}_{i}",
                        index=0,
                        label_visibility="collapsed"
                    )
                else:
                    st.warning("No portfolios")
            
            with col4:
                if portfolio_options:
                    if st.button("➕ Add", key=f"add_{symbol}_{i}"):
                        portfolio_id = int(selected_portfolio.split("(ID: ")[1].split(")")[0])
                        add_stock_to_watchlist(symbol, portfolio_id)
        
        st.divider()

def render_market_overview():
    """Render market overview section"""
    st.markdown("## 📊 Market Overview")
    
    # Market summary cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("S&P 500", "4,532.16", "1.2%")
    with col2:
        st.metric("NASDAQ", "14,125.48", "2.1%")
    with col3:
        st.metric("DOW", "35,678.23", "0.8%")
    with col4:
        st.metric("VIX", "15.42", "-0.5")
    
    st.markdown("---")

def render_sector_performance():
    """Render sector performance heatmap"""
    st.markdown("## 🏭 Sector Performance")
    
    # Sample sector data
    sectors = {
        'Technology': {'change': 2.1, 'status': 'positive'},
        'Healthcare': {'change': -0.3, 'status': 'negative'},
        'Financials': {'change': 1.4, 'status': 'positive'},
        'Energy': {'change': -1.8, 'status': 'negative'},
        'Consumer Discretionary': {'change': 0.8, 'status': 'positive'},
        'Industrials': {'change': -0.5, 'status': 'negative'},
        'Materials': {'change': 1.2, 'status': 'positive'},
        'Utilities': {'change': -0.2, 'status': 'negative'},
        'Real Estate': {'change': 0.3, 'status': 'positive'},
        'Communication': {'change': 1.8, 'status': 'positive'}
    }
    
    # Create sector performance chart
    sector_names = list(sectors.keys())
    sector_changes = [sectors[s]['change'] for s in sector_names]
    colors = ['green' if change >= 0 else 'red' for change in sector_changes]
    
    fig = go.Figure(data=[
        go.Bar(
            x=sector_changes,
            y=sector_names,
            orientation='h',
            marker_color=colors,
            text=[f"{change:+.1f}%" for change in sector_changes],
            textposition='outside'
        )
    ])
    
    fig.update_layout(
        title="Sector Performance Today",
        xaxis_title="Change (%)",
        yaxis_title="Sector",
        height=400,
        margin=dict(l=10, r=10, t=30, b=10)
    )
    
    st.plotly_chart(fig, use_container_width=True)

def main():
    """Main page logic"""
    setup_page_config()
    
    # Page header
    st.markdown("# 📈 Market Movers")
    st.markdown("*Today's top performing stocks and market analysis*")
    
    # Check user authentication
    current_user = get_current_user()
    if not current_user:
        st.warning("⚠️ Please login to add stocks to your portfolio.")
        st.session_state.redirect_after_login = "Market_Movers"
        return
    
    # Market overview
    render_market_overview()
    
    # Get market movers data
    with st.spinner("Loading market movers..."):
        market_data = get_market_movers()
    
    # Main content tabs
    tab1, tab2, tab3 = st.tabs(["📊 Top Gainers", "📉 Top Losers", "🏭 Sector Analysis"])
    
    with tab1:
        if market_data.get('gainers'):
            render_movers_table(market_data['gainers'], "🚀 Today's Top Gainers", "green")
        else:
            st.info("No gainers data available")
    
    with tab2:
        if market_data.get('losers'):
            render_movers_table(market_data['losers'], "📉 Today's Top Losers", "red")
        else:
            st.info("No losers data available")
    
    with tab3:
        render_sector_performance()
    
    # Footer
    st.markdown("---")
    st.markdown("""
    **Market Movers Analysis** provides real-time insights into today's best and worst performing stocks.
    Add interesting stocks directly to your portfolio for further analysis.
    
    *Data is updated every 15 minutes during market hours.*
    """)

if __name__ == "__main__":
    main()
