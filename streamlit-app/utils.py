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
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
PYTHON_API_URL = os.getenv("PYTHON_API_URL", "http://localhost:8001")
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

        subscription = subscription_level

    # TipRanks-style horizontal nav — cross-links the cockpit pages
    # at the top of every screen (renders in the main area, not the
    # sidebar block above).
    render_top_nav()
    return subscription


# The 10 cockpit pages — must stay registered in app.py's "🎯 Cockpit"
# section for page_link to resolve. Short labels so the strip fits.
COCKPIT_NAV = [
    ("pages/0_Alerts_Briefing.py", "Briefing", "🔔"),
    ("pages/00_Daily_Board.py", "Board", "📋"),
    ("pages/3_Portfolio_Manager.py", "Portfolio", "💼"),
    ("pages/28_Portfolio_Strategy.py", "Strategy", "🧭"),
    ("pages/1_Swing_Screener.py", "Swing", "🔍"),
    ("pages/29_Hidden_Gems.py", "Gems", "💎"),
    ("pages/30_Conviction.py", "Conviction", "🏆"),
    ("pages/32_Daily_Sheet.py", "Sheet", "📄"),
    ("pages/33_Readiness.py", "Ready", "✅"),
    ("pages/25_GARP_Screen.py", "GARP", "⚖️"),
    ("pages/9_Options.py", "Options", "🎲"),
    ("pages/24_Agent_Workbench.py", "Agents", "🤖"),
    ("pages/27_Learning_Lab.py", "Lab", "🧠"),
]


def sym_md(sym: str) -> str:
    """Inline markdown link → the Stock Health page (31_Stock.py →
    the /Stock route — filename-derived, not title). Embed inside
    st.markdown / st.caption strings: f"…{sym_md(s)}…" """
    s = (sym or "").upper().strip()
    return f"[{s}](Stock?sym={s})" if s else ""


def sym_link(sym: str) -> None:
    """Clickable symbol → the Stock Health detail page (?sym=...).
    Plain markdown link — theme-colored, visible in any theme.
    (st.page_link inherits the dark top-nav chip CSS → unreadable.)"""
    s = sym_md(sym)
    if s:
        st.markdown(s)


def sym_df_url(sym: str) -> str:
    """URL for a symbol — used to build a link column in a df."""
    s = (sym or "").upper().strip()
    return f"Stock?sym={s}"


def health_col(df, sym_col: str = "symbol"):
    """Add a 🩺 link column to a dataframe that has a symbol column —
    pair with `HEALTH_CFG` in the dataframe's column_config."""
    if sym_col in df.columns:
        df = df.copy()
        df["🩺"] = df[sym_col].map(sym_df_url)
    return df


HEALTH_CFG = None  # filled lazily — needs streamlit context


def health_cfg():
    """column_config entry: renders the 🩺 column cells as links."""
    return st.column_config.LinkColumn("🩺", display_text="open")


def render_top_nav():
    """Horizontal cross-nav strip — links every cockpit page to every
    other, like a real site's header. Compact pill styling; active
    page is highlighted via .cockpit-active."""
    st.markdown(
        """<style>
        div[data-testid="stHorizontalBlock"]:has(div[data-testid="stPageLink"]) {
            gap:.4rem;padding:.45rem .6rem;background:#0e1117;
            border-radius:10px;border:1px solid #262730;
            margin:-.6rem 0 .4rem}
        section[data-testid="stMain"] div[data-testid="stPageLink"] a {
            padding:.28rem .55rem !important;border-radius:999px;
            border:1px solid #2b2d3a;background:#16181f}
        section[data-testid="stMain"] div[data-testid="stPageLink"] a p {
            font-size:.8rem !important;margin:0}
        </style>""",
        unsafe_allow_html=True)
    cols = st.columns(len(COCKPIT_NAV))
    for col, (path, label, icon) in zip(cols, COCKPIT_NAV):
        with col:
            try:
                st.page_link(path, label=f"{icon} {label}")
            except Exception:
                pass

