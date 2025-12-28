"""
Home/Dashboard Page
Main landing page with overview and quick access
"""
import streamlit as st
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar

setup_page_config("Trading System - Home", "🏠")

st.title("🏠 Trading System Dashboard")
st.markdown("**Welcome to the AI Trading System**")

# Sidebar
subscription_level = render_sidebar()

# Main content
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Total Portfolios", "0", "0")
    st.caption("Active portfolios")

with col2:
    st.metric("Watchlists", "0", "0")
    st.caption("Active watchlists")

with col3:
    st.metric("Open Positions", "0", "0")
    st.caption("Current positions")

st.divider()

st.header("Quick Actions")
col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("📊 Stock Analysis", use_container_width=True):
        st.switch_page("pages/2_📊_Stock_Analysis.py")

with col2:
    if st.button("💼 Portfolio", use_container_width=True):
        st.switch_page("pages/3_💼_Portfolio.py")

with col3:
    if st.button("📋 Watchlist", use_container_width=True):
        st.switch_page("pages/4_📋_Watchlist.py")

with col4:
    # Testbed is automatically available in sidebar - no need for button navigation
    st.markdown("**🧪 Testbed**")
    st.caption("Available in sidebar")

st.divider()

st.header("Feature Overview")
st.markdown("""
### Available Features

- **📊 Stock Analysis**: Comprehensive stock analysis with indicators, signals, and reports
- **💼 Portfolio Management**: Create and manage portfolios with holdings
- **📋 Watchlist Management**: Create watchlists and track stocks
- **📈 Swing Trading**: Swing trading signals and risk management (Elite)
- **📝 Blog Generation**: AI-generated blog posts (Elite)
- **🌐 Market Features**: Market movers, sectors, comparisons
- **🧪 Testbed**: Comprehensive testing interface

### Subscription Tiers

- **Basic**: Stock overview, simple signals, read-only portfolio
- **Pro**: Advanced analysis, actionable levels, alerts, multiple portfolios
- **Elite**: Swing trading, blog generation, API access, automation
""")

