"""
Shared utilities for Streamlit pages
Common functions used across multiple pages
"""
import streamlit as st
import os
import logging

from api_client import (
    get_go_api_client,
    APIClient,
    APIError,
    APIConnectionError,
    APIResponseError
)

# Import ticker search component
from components.ticker_search import render_ticker_search

logger = logging.getLogger(__name__)

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://go-api:8000")
PYTHON_API_URL = os.getenv("PYTHON_API_URL", "http://python-worker:8001")
SUBSCRIPTION_LEVELS = ["basic", "pro", "elite"]

# Custom CSS
CUSTOM_CSS = """
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
"""


def setup_page_config(title: str, icon: str = "📈"):
    """Setup page configuration and CSS"""
    st.set_page_config(
        page_title=title,
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded"
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def get_subscription_level():
    """Get subscription level from session state or default"""
    if 'subscription_level' not in st.session_state:
        st.session_state.subscription_level = "basic"
    return st.session_state.subscription_level


def render_sidebar():
    """Render common sidebar with global ticker search and navigation"""
    with st.sidebar:
        st.header("Trading System")
        
        # Global ticker search (magnifying glass UX) - moved to top
        ticker = render_ticker_search()
        
        st.divider()
        
        # Navigation
        st.markdown("### Navigation")
        pages = {
            "🏠 Dashboard": "pages/1_Home.py",
            "📊 Trading Dashboard": "pages/9_Trading_Dashboard.py",
            "📊 Stock Overview": "pages/8_Stock_Overview.py",
            "📈 Stock Analysis": "pages/2_Stock_Analysis.py",
            "📈 Swing Trading": "pages/6_Swing_Trading.py",
            "📋 Watchlist Management": "pages/4_Watchlist.py",
            "💼 Portfolio Management": "pages/3_Portfolio.py",
            "📰 Market News": "pages/8_Market_Features.py",
        }

        for page_name, page_path in pages.items():
            # Use st.button with navigation instead of st.page_link for compatibility
            if st.button(page_name, key=f"nav_{page_path}", use_container_width=True):
                st.switch_page(page_path)
        
        st.divider()
        
        # Subscription level selector
        st.markdown("### Subscription")
        subscription_level = st.selectbox(
            "Subscription Level",
            SUBSCRIPTION_LEVELS,
            index=SUBSCRIPTION_LEVELS.index(get_subscription_level())
        )
        st.session_state.subscription_level = subscription_level
        
        # Display subscription badge
        badge_class = f"subscription-{subscription_level}"
        st.markdown(
            f'<span class="subscription-badge {badge_class}">{subscription_level.upper()}</span>',
            unsafe_allow_html=True
        )
        
        st.divider()
        
        # Cache Management
        st.markdown("### Cache Management")
        
        # Get current symbol from session state or default
        current_symbol = st.session_state.get("selected_ticker", "AAPL")
        
        col1, col2 = st.columns(2)
        with col1:
            clear_symbol = st.button("🗑️ Clear Symbol", key="clear_symbol_cache", use_container_width=True)
        with col2:
            clear_all = st.button("🗑️ Clear All", key="clear_all_cache", use_container_width=True)
        
        if clear_symbol:
            # Clear cache for current symbol
            with st.spinner(f"Clearing cache for {current_symbol}..."):
                try:
                    # Create API client for cache clearing
                    cache_client = APIClient(PYTHON_API_URL, timeout=30)
                    result = cache_client.post("/admin/clear-cache", json_data={"symbol": current_symbol})
                    st.success(f"✅ Cache cleared for {current_symbol}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to clear cache for {current_symbol}: {str(e)}")
        
        if clear_all:
            # Clear all cache
            with st.spinner("Clearing all cache..."):
                try:
                    cache_client = APIClient(PYTHON_API_URL, timeout=30)
                    result = cache_client.post("/admin/clear-cache", json_data={})
                    st.success("✅ All cache cleared")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to clear all cache: {str(e)}")
        
        # Store selected ticker in session state for other pages to use
        if ticker:
            st.session_state.selected_ticker = ticker
        
        return subscription_level

