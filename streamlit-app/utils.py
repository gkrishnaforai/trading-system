"""
Shared utilities for Streamlit pages
Common functions used across multiple pages
"""
import streamlit as st
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
    """Render common sidebar with subscription selector"""
    with st.sidebar:
        st.header("Settings")
        
        # Subscription level selector
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
        
        return subscription_level

