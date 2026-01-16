"""
Enhanced Portfolio Analysis Page with Database Persistence and Audit Trails
Industry-standard portfolio management with user authentication, multiple portfolios, and scheduling
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, date, time
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
    from utils.portfolio_utils import PortfolioManager, PortfolioAnalyzer, PortfolioVisualizer
except ImportError:
    # Fallback for Docker environment
    PortfolioManager = None
    PortfolioAnalyzer = None
    PortfolioVisualizer = None

from utils import setup_page_config, render_sidebar
from api_client import APIClient, APIError
from api_config import api_config

# Import shared analysis display component
from components.analysis_display import display_signal_analysis, display_no_data_message

# Initialize API client
python_api_url = api_config.python_worker_url
python_client = APIClient(python_api_url, timeout=30)
portfolio_api_url = f"{python_api_url}/api/v2/portfolio"

# ========================================
# Helper Functions for DRY Code
# ========================================

def create_portfolio_selector(portfolios: List[Dict[str, Any]], key: str = "portfolio") -> Dict[str, Any]:
    """Create standardized portfolio selector dropdown"""
    portfolio_options = {f"{p['name']} ({p['portfolio_type'].title()})": p for p in portfolios}
    selected_name = st.selectbox(
        "Select Portfolio",
        options=list(portfolio_options.keys()),
        key=f"{key}_selector",
        help="Choose a portfolio to manage"
    )
    return portfolio_options[selected_name]

def format_currency(value: Any, default: str = "$0.00") -> str:
    """Safely format currency values"""
    try:
        if value is None or value == "":
            return default
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return str(value) if value else default

def format_percentage(value: Any, default: str = "0.00%") -> str:
    """Safely format percentage values"""
    try:
        if value is None or value == "":
            return default
        return f"{float(value):+.2f}%"
    except (ValueError, TypeError):
        return str(value) if value else default

def format_shares(value: Any, default: str = "0") -> str:
    """Safely format share values"""
    try:
        if value is None or value == "":
            return default
        return f"{float(value):,.2f}"
    except (ValueError, TypeError):
        return str(value) if value else default

def create_portfolio_metrics(portfolio: Dict[str, Any]) -> None:
    """Create standardized portfolio metrics display"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Portfolio Type", portfolio['portfolio_type'].title())
    
    with col2:
        initial_capital = portfolio.get('initial_capital', 0)
        try:
            initial_capital = float(initial_capital)
            st.metric("Initial Capital", f"${initial_capital:,.2f}")
        except (ValueError, TypeError):
            st.metric("Initial Capital", str(initial_capital))
    
    with col3:
        st.metric("Holdings", portfolio.get('holdings_count', 0))
    
    with col4:
        status = "🟢 Active" if portfolio.get('is_active', True) else "🔴 Inactive"
        st.metric("Status", status)

def create_holdings_table(holdings: List[Dict[str, Any]], show_actions: bool = True) -> pd.DataFrame:
    """Create standardized holdings table with formatting"""
    holdings_data = []
    
    for holding in holdings:
        # Get signal with color formatting
        signal = get_stock_signal(holding['symbol'])
        signal_colors = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}
        color = signal_colors.get(signal, '⚪')
        formatted_signal = f"{color} {signal}"
        
        # Safe numeric formatting
        avg_cost = holding.get('average_cost', 0)
        current_price = holding.get('current_price')
        market_value = holding.get('market_value')
        pnl_pct = holding.get('unrealized_pnl_pct')
        
        holdings_data.append({
            'Symbol': holding['symbol'],
            'Shares': format_shares(holding['shares_held']),
            'Avg Cost': format_currency(avg_cost),
            'Current Price': format_currency(current_price),
            'Market Value': format_currency(market_value),
            'P&L': format_percentage(pnl_pct),
            'Signal': formatted_signal
        })
    
    return pd.DataFrame(holdings_data)

def create_portfolio_action_buttons(portfolio: Dict[str, Any]) -> None:
    """Create standardized portfolio action buttons"""
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("✏️ Edit Portfolio", key=f"edit_{portfolio['id']}"):
            st.session_state.edit_portfolio = portfolio['id']
    
    with col2:
        if st.button("🗑️ Delete Portfolio", key=f"delete_{portfolio['id']}"):
            if portfolio.get('holdings_count', 0) == 0:
                delete_portfolio(portfolio['id'])
                st.success("Portfolio deleted successfully!")
                st.rerun()
            else:
                st.error("Cannot delete portfolio with holdings. Remove all holdings first.")
    
    with col3:
        if st.button("📊 View Analysis", key=f"analyze_{portfolio['id']}"):
            st.session_state.selected_portfolio = portfolio['id']
            st.session_state.show_analysis = True

# ========================================
# Authentication Functions
# ========================================

def login_user(username: str, password: str) -> bool:
    """Login user and store token in session state"""
    try:
        response = requests.post(f"{portfolio_api_url}/users/login", 
                               json={"username": username, "password": password})
        
        if response.status_code == 200:
            data = response.json()
            st.session_state.auth_token = data["access_token"]
            st.session_state.current_user = data["user"]
            return True
        else:
            st.error(f"Login failed: {response.json().get('detail', 'Unknown error')}")
            return False
    except Exception as e:
        st.error(f"Login error: {str(e)}")
        return False

def logout_user():
    """Logout user and clear session state"""
    if 'auth_token' in st.session_state:
        del st.session_state.auth_token
    if 'current_user' in st.session_state:
        del st.session_state.current_user
    if 'selected_portfolio' in st.session_state:
        del st.session_state.selected_portfolio
    st.rerun()

def get_auth_headers() -> Dict[str, str]:
    """Get authorization headers for API requests"""
    if 'auth_token' in st.session_state:
        return {"Authorization": f"Bearer {st.session_state.auth_token}"}
    return {}

def is_authenticated() -> bool:
    """Check if user is authenticated"""
    return 'auth_token' in st.session_state and 'current_user' in st.session_state

# ========================================
# Portfolio Management Functions
# ========================================

def get_user_portfolios() -> List[Dict[str, Any]]:
    """Get all portfolios for current user"""
    try:
        response = requests.get(f"{portfolio_api_url}/portfolios", 
                              headers=get_auth_headers(),
                              timeout=30)  # 30 second timeout
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error loading portfolios: {response.json().get('detail', 'Unknown error')}")
            return []
    except requests.exceptions.Timeout:
        st.error("⏰ Loading portfolios timed out. Please try again.")
        return []
    except Exception as e:
        st.error(f"Error loading portfolios: {str(e)}")
        return []

def create_portfolio(name: str, description: str = "", portfolio_type: str = "custom", 
                    initial_capital: float = 10000.0) -> Optional[Dict[str, Any]]:
    """Create a new portfolio"""
    try:
        response = requests.post(f"{portfolio_api_url}/portfolios",
                               json={
                                   "name": name,
                                   "description": description,
                                   "portfolio_type": portfolio_type,
                                   "initial_capital": initial_capital
                               },
                               headers=get_auth_headers(),
                               timeout=30)  # 30 second timeout
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error creating portfolio: {response.json().get('detail', 'Unknown error')}")
            return None
    except requests.exceptions.Timeout:
        st.error("⏰ Creating portfolio timed out. Please try again.")
        return None
    except Exception as e:
        st.error(f"Error creating portfolio: {str(e)}")
        return None

def get_portfolio_holdings(portfolio_id: str) -> List[Dict[str, Any]]:
    """Get holdings for a portfolio with timeout handling"""
    try:
        response = requests.get(f"{portfolio_api_url}/portfolios/{portfolio_id}/holdings",
                              headers=get_auth_headers(),
                              timeout=30)  # 30 second timeout
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error loading holdings: {response.json().get('detail', 'Unknown error')}")
            return []
    except requests.exceptions.Timeout:
        st.error("⏰ Loading holdings timed out. Please try again.")
        return []
    except Exception as e:
        st.error(f"Error loading holdings: {str(e)}")
        return []

def add_portfolio_holding(portfolio_id: str, symbol: str, asset_type: str = "stock", 
                         shares_held: float = 0, average_cost: float = 0) -> Optional[Dict[str, Any]]:
    """Add a holding to portfolio with timeout handling"""
    try:
        url = f"{portfolio_api_url}/portfolios/{portfolio_id}/holdings"
        
        response = requests.post(url,
                               json={
                                   "symbol": symbol.upper(),
                                   "asset_type": asset_type,
                                   "shares_held": shares_held,
                                   "average_cost": average_cost
                               },
                               headers=get_auth_headers(),
                               timeout=30)  # 30 second timeout
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error adding holding: {response.json().get('detail', 'Unknown error')}")
            return None
    except requests.exceptions.Timeout:
        st.error("⏰ Adding holding timed out. Please try again.")
        return None
    except Exception as e:
        st.error(f"Error adding holding: {str(e)}")
        return None

def analyze_portfolio(portfolio_id: str, target_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """Run analysis on portfolio with timeout handling"""
    try:
        payload = {}
        if target_date:
            payload["target_date"] = target_date.isoformat()
        
        response = requests.post(f"{portfolio_api_url}/portfolios/{portfolio_id}/analyze",
                               json=payload,
                               headers=get_auth_headers(),
                               timeout=60)  # 60 second timeout for analysis
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error analyzing portfolio: {response.json().get('error', 'Unknown error')}")
            return None
    except requests.exceptions.Timeout:
        st.error("⏰ Portfolio analysis timed out. Please try again.")
        return None
    except Exception as e:
        st.error(f"Error analyzing portfolio: {str(e)}")
        return None

def get_symbol_signal_history(symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get signal history for a symbol with timeout handling"""
    try:
        response = requests.get(f"{portfolio_api_url}/symbols/{symbol}/signals?limit={limit}",
                              headers=get_auth_headers(),
                              timeout=30)  # 30 second timeout
        
        if response.status_code == 200:
            return response.json()
        else:
            return []
    except requests.exceptions.Timeout:
        st.warning(f"⏰ Signal history for {symbol} timed out.")
        return []
    except Exception as e:
        st.warning(f"Error getting signal history for {symbol}: {str(e)}")
        return []

def get_portfolio_schedules(portfolio_id: str) -> List[Dict[str, Any]]:
    """Get scheduled analyses for portfolio with timeout handling"""
    try:
        response = requests.get(f"{portfolio_api_url}/portfolios/{portfolio_id}/schedules",
                              headers=get_auth_headers(),
                              timeout=30)  # 30 second timeout
        
        if response.status_code == 200:
            return response.json()
        else:
            return []
    except requests.exceptions.Timeout:
        st.warning("⏰ Loading schedules timed out.")
        return []
    except Exception as e:
        st.warning(f"Error loading schedules: {str(e)}")
        return []

def create_portfolio_schedule(portfolio_id: str, schedule_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Create a scheduled analysis with timeout handling"""
    try:
        response = requests.post(f"{portfolio_api_url}/portfolios/{portfolio_id}/schedules",
                               json=schedule_data,
                               headers=get_auth_headers(),
                               timeout=30)  # 30 second timeout
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error creating schedule: {response.json().get('detail', 'Unknown error')}")
            return None
    except requests.exceptions.Timeout:
        st.error("⏰ Creating schedule timed out. Please try again.")
        return None
    except Exception as e:
        st.error(f"Error creating schedule: {str(e)}")
        return None

def refresh_symbol_analysis(symbol: str, asset_type: str = "stock") -> bool:
    """Refresh analysis for a symbol with timeout handling"""
    try:
        response = requests.post(f"{portfolio_api_url}/symbols/{symbol}/analyze",
                               json={"asset_type": asset_type},
                               headers=get_auth_headers(),
                               timeout=60)  # 60 second timeout for analysis
        
        if response.status_code == 200:
            st.success(f"✅ Analysis refreshed for {symbol}")
            return True
        else:
            st.error(f"Error refreshing analysis: {response.json().get('detail', 'Unknown error')}")
            return False
    except requests.exceptions.Timeout:
        st.error(f"⏰ Analysis refresh for {symbol} timed out. Please try again.")
        return False
    except Exception as e:
        st.error(f"Error refreshing analysis: {str(e)}")
        return False

# ========================================
# UI Components
# ========================================

def show_login_page():
    """Show login page"""
    st.markdown("""
    <div style="text-align: center; padding: 4rem; color: #666;">
        <h1>🔐 Portfolio Management System</h1>
        <p>Please login to access your portfolios</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("login_form"):
            st.markdown("### Login")
            
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            
            if st.form_submit_button("Login", type="primary", use_container_width=True):
                if username and password:
                    if login_user(username, password):
                        st.success("✅ Login successful!")
                        st.rerun()
                else:
                    st.error("Please enter both username and password")
        
        st.markdown("---")
        st.markdown("#### 📝 Default Admin Account")
        st.code("""
Username: admin
Password: admin123
        """)

def show_portfolio_management_tab(portfolios):
    """Portfolio Management tab with CRUD operations"""
    st.markdown("### 📋 Portfolio Management")
    
    # Portfolio selection and actions
    col1, col2 = st.columns([3, 1])
    
    with col1:
        selected_portfolio = create_portfolio_selector(portfolios, "management")
    
    with col2:
        if st.button("➕ Create New", type="primary", use_container_width=True, key="create_portfolio_mgmt"):
            st.session_state.show_create_portfolio = True
    
    # Show create portfolio form if requested
    if st.session_state.get('show_create_portfolio', False):
        st.markdown("#### ➕ Create New Portfolio")
        show_create_portfolio_form("management")
        if st.button("❌ Cancel", key="cancel_create_mgmt"):
            st.session_state.show_create_portfolio = False
            st.rerun()
        return
    
    # Portfolio details and actions
    if selected_portfolio:
        st.markdown("---")
        
        # Use helper function for portfolio metrics
        create_portfolio_metrics(selected_portfolio)
        
        # Use helper function for action buttons
        create_portfolio_action_buttons(selected_portfolio)
        
        # Portfolio holdings
        st.markdown("#### 📈 Portfolio Holdings")
        holdings = get_portfolio_holdings(selected_portfolio['id'])
        
        if holdings:
            # Use helper function for holdings table
            df_holdings = create_holdings_table(holdings)
            
            # Display the dataframe without styling the Signal column
            st.dataframe(df_holdings, use_container_width=True, hide_index=True)
            
            # Action buttons for each holding
            st.markdown("#### 🎯 Stock Actions")
            for holding in holdings:
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                
                with col1:
                    st.write(f"**{holding['symbol']}**")
                
                with col2:
                    if st.button("✏️ Edit", key=f"mgmt_edit_{holding['symbol']}"):
                        st.session_state.show_edit_stock = True
                        st.session_state.edit_symbol = holding['symbol']
                        st.session_state.edit_holding = holding
                        st.rerun()
                
                with col3:
                    if st.button("🗑️ Delete", key=f"mgmt_delete_{holding['symbol']}"):
                        if st.session_state.get(f'confirm_delete_{holding["symbol"]}', False):
                            success = delete_portfolio_holding(selected_portfolio['id'], holding['symbol'])
                            if success:
                                st.success(f"✅ {holding['symbol']} deleted successfully!")
                                st.rerun()
                            else:
                                st.error(f"❌ Failed to delete {holding['symbol']}")
                        else:
                            st.session_state[f'confirm_delete_{holding["symbol"]}'] = True
                            st.warning(f"⚠️ Click again to confirm deleting {holding['symbol']}")
                            st.rerun()
                
                with col4:
                    signal = get_stock_signal(holding['symbol'])
                    signal_colors = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}
                    color = signal_colors.get(signal, '⚪')
                    if st.button(f"{color} {signal}", key=f"mgmt_signal_{holding['symbol']}"):
                        # Clear any previous analysis state
                        if 'show_symbol_analysis' in st.session_state:
                            st.session_state.show_symbol_analysis = False
                        if 'selected_symbol_for_analysis' in st.session_state:
                            del st.session_state.selected_symbol_for_analysis
                        
                        # Set new symbol for analysis
                        st.session_state.selected_symbol_for_analysis = holding['symbol']
                        st.session_state.show_symbol_analysis = True
                        st.success(f"🔄 Loading analysis for {holding['symbol']}...")
                        st.rerun()
            
            # Show edit stock form if requested
            if st.session_state.get('show_edit_stock', False) and st.session_state.get('edit_holding'):
                show_edit_stock_form(selected_portfolio['id'], st.session_state.edit_holding)
            
            # Add stock button
            st.markdown("---")
            if st.button("➕ Add Stock to Portfolio", type="primary", key="add_stock_mgmt"):
                st.session_state.show_add_stock = True
            
            # Add stock form
            if st.session_state.get('show_add_stock', False):
                show_add_stock_form(selected_portfolio['id'])
        else:
            st.info("📋 No holdings in this portfolio. Add stocks to get started!")
            if st.button("➕ Add Your First Stock", type="primary", key="add_first_stock"):
                st.session_state.show_add_stock = True
            
            # Add stock form
            if st.session_state.get('show_add_stock', False):
                show_add_stock_form(selected_portfolio['id'])

def update_portfolio_holding(portfolio_id: str, symbol: str, shares_held: float, average_cost: float, asset_type: str = "stock") -> Optional[Dict[str, Any]]:
    """Update a holding in portfolio"""
    try:
        url = f"{portfolio_api_url}/portfolios/{portfolio_id}/holdings/{symbol}"
        
        response = requests.put(url,
                              json={
                                  "shares_held": shares_held,
                                  "average_cost": average_cost,
                                  "asset_type": asset_type
                              },
                              headers=get_auth_headers(),
                              timeout=30)
        
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Error updating holding: {response.json().get('detail', 'Unknown error')}")
            return None
    except requests.exceptions.Timeout:
        st.error("⏰ Updating holding timed out. Please try again.")
        return None
    except Exception as e:
        st.error(f"Error updating holding: {str(e)}")
        return None

def delete_portfolio_holding(portfolio_id: str, symbol: str) -> bool:
    """Delete a holding from portfolio"""
    try:
        url = f"{portfolio_api_url}/portfolios/{portfolio_id}/holdings/{symbol}"
        
        response = requests.delete(url,
                                 headers=get_auth_headers(),
                                 timeout=30)
        
        if response.status_code == 200:
            return True
        else:
            st.error(f"Error deleting holding: {response.json().get('detail', 'Unknown error')}")
            return False
    except requests.exceptions.Timeout:
        st.error("⏰ Deleting holding timed out. Please try again.")
        return False
    except Exception as e:
        st.error(f"Error deleting holding: {str(e)}")
        return False

def show_edit_stock_form(portfolio_id: str, holding: Dict[str, Any]):
    """Show edit stock form"""
    with st.form("edit_stock_form"):
        st.markdown(f"#### ✏️ Edit {holding['symbol']}")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.text_input("Symbol", value=holding['symbol'], disabled=True)
        
        with col2:
            asset_type = st.selectbox("Type*", ["stock", "regular_etf", "3x_etf"], 
                                     index=["stock", "regular_etf", "3x_etf"].index(holding.get('asset_type', 'stock')))
        
        with col3:
            shares = st.number_input("Shares*", min_value=0.0, value=float(holding['shares_held']), step=10.0)
        
        with col4:
            avg_cost = st.number_input("Avg Cost ($)*", min_value=0.0, value=float(holding['average_cost']), step=0.01)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("💾 Update Stock", type="primary"):
                updated_holding = update_portfolio_holding(portfolio_id, holding['symbol'], shares, avg_cost, asset_type)
                if updated_holding:
                    st.success(f"✅ {holding['symbol']} updated successfully!")
                    st.session_state.show_edit_stock = False
                    st.session_state.edit_symbol = None
                    st.rerun()
        
        with col2:
            if st.form_submit_button("❌ Cancel"):
                st.session_state.show_edit_stock = False
                st.session_state.edit_symbol = None
                st.rerun()

def get_stock_signal(symbol: str) -> str:
    """Get stock signal (mock implementation - replace with real API call)"""
    # This is a mock implementation - replace with actual signal API call
    import random
    signals = ['BUY', 'SELL', 'HOLD']
    return random.choice(signals)

def delete_portfolio(portfolio_id: str) -> bool:
    """Delete a portfolio"""
    try:
        response = requests.delete(f"{portfolio_api_url}/portfolios/{portfolio_id}",
                                headers=get_auth_headers())
        return response.status_code == 200
    except:
        return False

def show_add_stock_form(portfolio_id: str):
    """Show add stock form"""
    with st.form("add_stock_form"):
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            symbol = st.text_input("Symbol*", placeholder="e.g., AAPL").upper()
        
        with col2:
            asset_type = st.selectbox("Type*", ["stock", "regular_etf", "3x_etf"])
        
        with col3:
            shares = st.number_input("Shares", min_value=0.0, value=100.0, step=10.0)
        
        with col4:
            avg_cost = st.number_input("Avg Cost ($)", min_value=0.0, value=0.0, step=0.01)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("➕ Add Stock", type="primary"):
                if symbol:
                    holding = add_portfolio_holding(portfolio_id, symbol, asset_type, shares, avg_cost)
                    if holding:
                        st.success(f"✅ {symbol} added to portfolio!")
                        st.session_state.show_add_stock = False
                        st.rerun()
                else:
                    st.error("Symbol is required")
        
        with col2:
            if st.form_submit_button("❌ Cancel"):
                st.session_state.show_add_stock = False
                st.rerun()

def show_portfolio_overview_tab(portfolios):
    """Portfolio Overview tab"""
    show_portfolio_overview()

def show_stock_analysis_tab(portfolios):
    """Stock Analysis tab with clickable signals"""
    st.markdown("### 📈 Stock Analysis")
    
    # Use helper function for portfolio selection
    selected_portfolio = create_portfolio_selector(portfolios, "analysis")
    
    # Get holdings
    holdings = get_portfolio_holdings(selected_portfolio['id'])
    
    if holdings:
        st.markdown("#### 📊 Portfolio Stocks with Signals")
        
        for holding in holdings:
            signal = get_stock_signal(holding['symbol'])
            
            # Signal color
            signal_colors = {
                'BUY': '🟢',
                'SELL': '🔴', 
                'HOLD': '🟡'
            }
            color = signal_colors.get(signal, '⚪')
            
            # Create clickable signal
            col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
            
            with col1:
                st.write(f"**{holding['symbol']}**")
            
            with col2:
                st.write(f"Shares: {format_shares(holding['shares_held'])}")
            
            with col3:
                st.write(f"Cost: {format_currency(holding.get('average_cost', 0))}")
            
            with col4:
                if st.button(f"{color} {signal}", key=f"analysis_signal_{holding['symbol']}"):
                    # Clear any previous analysis state
                    if 'show_symbol_analysis' in st.session_state:
                        st.session_state.show_symbol_analysis = False
                    if 'selected_symbol_for_analysis' in st.session_state:
                        del st.session_state.selected_symbol_for_analysis
                    
                    # Set new symbol for analysis
                    st.session_state.selected_symbol_for_analysis = holding['symbol']
                    st.session_state.show_symbol_analysis = True
                    st.success(f"🔄 Loading analysis for {holding['symbol']}...")
                    st.rerun()
            
            with col5:
                current_price = holding.get('current_price')
                st.write(f"Price: {format_currency(current_price)}")
    else:
        st.info("📋 No holdings in this portfolio. Add stocks to see analysis.")

def show_settings_tab():
    """Settings tab"""
    st.markdown("### ⚙️ Settings")
    st.info("Settings functionality coming soon...")

def show_portfolio_overview():
    """Show institutional-grade portfolio overview page"""
    user = st.session_state.current_user
    
    # Institutional header with professional styling
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); 
                padding: 2.5rem; border-radius: 15px; color: white; margin-bottom: 2rem; 
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h1 style="margin: 0; font-size: 2.5rem; font-weight: 700;">🏛️ Portfolio Management</h1>
                <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">Institutional-grade portfolio analysis and management</p>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 1.2rem; font-weight: 600;">{user['full_name'] or user['username']}</div>
                <div style="opacity: 0.8;">{user['role'].title()} Account</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Get user portfolios
    portfolios = get_user_portfolios()
    
    if not portfolios:
        # Show create portfolio form for first-time users
        st.markdown("""
        <div style="background: #f8fafc; padding: 3rem; border-radius: 15px; text-align: center; border: 2px dashed #cbd5e1;">
            <div style="font-size: 4rem; margin-bottom: 1rem;">📋</div>
            <h2 style="color: #475569; margin-bottom: 1rem;">No Portfolios Yet</h2>
            <p style="color: #64748b; margin-bottom: 2rem;">Create your first portfolio to start institutional-grade analysis</p>
        </div>
        """, unsafe_allow_html=True)
        
        show_create_portfolio_form("first_portfolio")
    else:
        # Use helper function for portfolio selection
        selected_portfolio = create_portfolio_selector(portfolios, "overview")
        st.session_state.selected_portfolio = selected_portfolio['id']
        
        # Institutional action buttons
        st.markdown("### 🎯 Portfolio Actions")
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
        
        with col1:
            if st.button("📊 Institutional Analysis", type="primary", use_container_width=True, key="overview_analysis"):
                with st.spinner("Running institutional-grade analysis..."):
                    result = analyze_portfolio(selected_portfolio['id'])
                    if result and result.get('success'):
                        st.success(f"✅ Analysis complete! Generated {result['signals_generated']} institutional signals")
                        st.session_state.last_analysis_result = result
                    else:
                        st.error("❌ Analysis failed")
        
        with col2:
            if st.button("🔄 Refresh Data", use_container_width=True, key="overview_refresh"):
                load_portfolio_data(selected_portfolio['id'])
        
        with col3:
            if st.button("📈 Risk Metrics", use_container_width=True, key="overview_risk"):
                st.session_state.show_risk_metrics = True
        
        with col4:
            if st.button("➕ Add Symbol", use_container_width=True, key="overview_add"):
                st.session_state.show_add_symbol = True
        
        with col5:
            if st.button("🔄 Load All Data", use_container_width=True, key="overview_load_all"):
                load_all_portfolio_data(selected_portfolio['id'])
        
        # Show portfolio details with institutional formatting
        show_portfolio_details(selected_portfolio)
        
        # Show institutional risk metrics if requested
        if st.session_state.get('show_risk_metrics', False):
            show_institutional_risk_metrics(selected_portfolio)
        
        # Show last analysis results with institutional formatting
        if 'last_analysis_result' in st.session_state:
            show_institutional_analysis_results(st.session_state.last_analysis_result)

def show_create_portfolio_form(location: str = "main"):
    """Show create portfolio form"""
    form_key = f"create_portfolio_form_{location}"
    with st.form(form_key):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Portfolio Name*", placeholder="e.g., Growth Portfolio")
            portfolio_type = st.selectbox("Portfolio Type", [
                "custom", "growth", "income", "balanced", "retirement"
            ])
        
        with col2:
            initial_capital = st.number_input("Initial Capital ($)", min_value=0.0, value=10000.0, step=1000.0)
            currency = st.selectbox("Currency", ["USD", "EUR", "GBP"])
        
        description = st.text_area("Description (Optional)", placeholder="Describe your portfolio strategy...")
        
        if st.form_submit_button("➕ Create Portfolio", type="primary", use_container_width=True):
            if name:
                portfolio = create_portfolio(name, description, portfolio_type, initial_capital)
                if portfolio:
                    st.success(f"✅ Portfolio '{name}' created successfully!")
                    st.rerun()
            else:
                st.error("Portfolio name is required")

def show_institutional_risk_metrics(portfolio: Dict[str, Any]):
    """Show institutional-grade risk metrics"""
    st.markdown("### 📊 Institutional Risk Metrics")
    
    # Get portfolio holdings for risk analysis
    holdings = get_portfolio_holdings(portfolio['id'])
    
    if not holdings:
        st.warning("No holdings data available for risk analysis")
        return
    
    # Calculate risk metrics
    total_value = sum(float(h.get('market_value', 0)) for h in holdings if h.get('market_value'))
    
    # Risk metrics calculation
    risk_metrics = calculate_institutional_risk_metrics(holdings)
    
    # Display risk dashboard
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div style="background: #f0f9ff; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #0ea5e9;">
            <h4 style="margin: 0; color: #0c4a6e;">📊 Portfolio Beta</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #0284c7;">{risk_metrics['portfolio_beta']:.2f}</div>
            <div style="font-size: 0.875rem; color: #64748b;">Market sensitivity</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background: #fef3c7; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #f59e0b;">
            <h4 style="margin: 0; color: #92400e;">⚠️ Value at Risk</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #d97706;">{risk_metrics['var_95']:.2f}%</div>
            <div style="font-size: 0.875rem; color: #64748b;">95% Confidence</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div style="background: #f0fdf4; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #22c55e;">
            <h4 style="margin: 0; color: #166534;">🎯 Sharpe Ratio</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #16a34a;">{risk_metrics['sharpe_ratio']:.2f}</div>
            <div style="font-size: 0.875rem; color: #64748b;">Risk-adjusted return</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div style="background: #fef2f2; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #ef4444;">
            <h4 style="margin: 0; color: #991b1b;">📉 Max Drawdown</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #dc2626;">{risk_metrics['max_drawdown']:.2f}%</div>
            <div style="font-size: 0.875rem; color: #64748b;">Peak to trough</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Risk assessment
    st.markdown("### 🎯 Risk Assessment")
    
    risk_level = assess_portfolio_risk(risk_metrics)
    
    st.markdown(f"""
    <div style="background: {risk_level['bg_color']}; padding: 1.5rem; border-radius: 10px; border-left: 4px solid {risk_level['border_color']};">
        <h4 style="margin: 0; color: {risk_level['text_color']};">{risk_level['emoji']} Risk Level: {risk_level['level']}</h4>
        <p style="margin: 0.5rem 0 0 0; color: {risk_level['text_color']};">{risk_level['description']}</p>
        <div style="margin-top: 1rem;">
            <strong>Key Risk Factors:</strong>
            <ul style="margin: 0.5rem 0; padding-left: 1.5rem; color: {risk_level['text_color']};">
                {"".join([f"<li>{factor}</li>" for factor in risk_level['factors']])}
            </ul>
        </div>
    </div>
    """, unsafe_allow_html=True)

def calculate_institutional_risk_metrics(holdings: List[Dict]) -> Dict[str, float]:
    """Calculate institutional-grade risk metrics"""
    # Simplified calculations - in production, these would use historical data
    total_value = sum(float(h.get('market_value', 0)) for h in holdings if h.get('market_value'))
    
    # Portfolio beta (simplified)
    portfolio_beta = 1.0  # Would calculate from individual stock betas
    
    # VaR (simplified - would use historical returns)
    var_95 = 2.5  # 95% VaR percentage
    
    # Sharpe ratio (simplified)
    sharpe_ratio = 1.2  # Risk-adjusted return metric
    
    # Max drawdown (simplified)
    max_drawdown = 8.5  # Maximum peak-to-trough decline
    
    return {
        'portfolio_beta': portfolio_beta,
        'var_95': var_95,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown
    }

def assess_portfolio_risk(risk_metrics: Dict[str, float]) -> Dict[str, Any]:
    """Assess overall portfolio risk level"""
    risk_score = 0
    
    # Calculate risk score based on metrics
    if risk_metrics['portfolio_beta'] > 1.2:
        risk_score += 2
    elif risk_metrics['portfolio_beta'] < 0.8:
        risk_score += 1
    
    if risk_metrics['var_95'] > 3.0:
        risk_score += 2
    elif risk_metrics['var_95'] > 2.0:
        risk_score += 1
    
    if risk_metrics['max_drawdown'] > 10.0:
        risk_score += 2
    elif risk_metrics['max_drawdown'] > 5.0:
        risk_score += 1
    
    if risk_metrics['sharpe_ratio'] < 0.5:
        risk_score += 2
    elif risk_metrics['sharpe_ratio'] < 1.0:
        risk_score += 1
    
    # Determine risk level
    if risk_score >= 6:
        return {
            'level': 'HIGH',
            'emoji': '🔴',
            'bg_color': '#fef2f2',
            'border_color': '#ef4444',
            'text_color': '#991b1b',
            'description': 'Portfolio exhibits high risk characteristics. Consider reducing exposure or implementing hedging strategies.',
            'factors': ['High market sensitivity', 'Elevated volatility risk', 'Significant drawdown potential', 'Low risk-adjusted returns']
        }
    elif risk_score >= 3:
        return {
            'level': 'MODERATE',
            'emoji': '🟡',
            'bg_color': '#fef3c7',
            'border_color': '#f59e0b',
            'text_color': '#92400e',
            'description': 'Portfolio has moderate risk levels. Monitor market conditions and maintain balanced diversification.',
            'factors': ['Moderate market sensitivity', 'Acceptable volatility levels', 'Reasonable drawdown risk', 'Adequate risk-adjusted returns']
        }
    else:
        return {
            'level': 'LOW',
            'emoji': '🟢',
            'bg_color': '#f0fdf4',
            'border_color': '#22c55e',
            'text_color': '#166534',
            'description': 'Portfolio demonstrates low risk characteristics with good diversification and risk management.',
            'factors': ['Low market sensitivity', 'Controlled volatility', 'Limited drawdown risk', 'Strong risk-adjusted returns']
        }

def show_institutional_analysis_results(analysis_result: Dict[str, Any]):
    """Show institutional-grade analysis results"""
    st.markdown("### 📊 Institutional Analysis Results")
    
    # Analysis summary
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); 
                padding: 2rem; border-radius: 15px; color: white; margin-bottom: 2rem;">
        <h2 style="margin: 0; font-size: 2rem;">🎯 Analysis Summary</h2>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1.5rem;">
            <div style="background: rgba(255,255,255,0.1); padding: 1rem; border-radius: 10px;">
                <div style="font-size: 0.875rem; opacity: 0.8;">Signals Generated</div>
                <div style="font-size: 1.5rem; font-weight: 700;">{analysis_result.get('signals_generated', 0)}</div>
            </div>
            <div style="background: rgba(255,255,255,0.1); padding: 1rem; border-radius: 10px;">
                <div style="font-size: 0.875rem; opacity: 0.8;">Analysis Time</div>
                <div style="font-size: 1.5rem; font-weight: 700;">{analysis_result.get('analysis_time', 'N/A')}</div>
            </div>
            <div style="background: rgba(255,255,255,0.1); padding: 1rem; border-radius: 10px;">
                <div style="font-size: 0.875rem; opacity: 0.8;">Confidence</div>
                <div style="font-size: 1.5rem; font-weight: 700;">{analysis_result.get('confidence', 'N/A')}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Signal breakdown
    if 'signals' in analysis_result:
        st.markdown("### 🚦 Signal Breakdown")
        
        signals = analysis_result['signals']
        signal_counts = {}
        
        for signal in signals:
            signal_type = signal.get('signal', 'UNKNOWN')
            signal_counts[signal_type] = signal_counts.get(signal_type, 0) + 1
        
        # Create signal distribution chart
        if signal_counts:
            fig = go.Figure(data=[
                go.Bar(
                    x=list(signal_counts.keys()),
                    y=list(signal_counts.values()),
                    marker_color=['#00C851' if k == 'BUY' else '#FF4444' if k == 'SELL' else '#FF8800' for k in signal_counts.keys()]
                )
            ])
            
            fig.update_layout(
                title="Signal Distribution",
                xaxis_title="Signal Type",
                yaxis_title="Count",
                plot_bgcolor='white',
                paper_bgcolor='white'
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        # Detailed signals table
        st.markdown("#### 📋 Detailed Signals")
        
        signal_data = []
        for signal in signals:
            signal_data.append({
                'Symbol': signal.get('symbol', 'N/A'),
                'Signal': signal.get('signal', 'N/A'),
                'Confidence': f"{signal.get('confidence', 0):.1%}",
                'Reasoning': signal.get('reasoning', ['No reasoning'])[0] if signal.get('reasoning') else 'No reasoning',
                'Timestamp': signal.get('timestamp', 'N/A')
            })
        
        if signal_data:
            df_signals = pd.DataFrame(signal_data)
            st.dataframe(df_signals, use_container_width=True, hide_index=True)

def show_portfolio_details(portfolio: Dict[str, Any]):
    """Show institutional-grade portfolio information"""
    st.markdown(f"### 📊 {portfolio['name']}")
    
    # Portfolio metrics with institutional styling
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div style="background: #f8fafc; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #0ea5e9;">
            <h4 style="margin: 0; color: #0c4a6e;">💰 Initial Capital</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #0284c7;">${:.2f}</div>
        </div>
        """.format(float(portfolio.get('initial_capital', 0))), unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background: #f8fafc; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #22c55e;">
            <h4 style="margin: 0; color: #166534;">📈 Portfolio Type</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #16a34a;">{}</div>
        </div>
        """.format(portfolio.get('portfolio_type', 'custom').replace('_', ' ').title()), unsafe_allow_html=True)
    
    with col3:
        created_at = portfolio.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        st.markdown("""
        <div style="background: #f8fafc; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #f59e0b;">
            <h4 style="margin: 0; color: #92400e;">📅 Created</h4>
            <div style="font-size: 1.5rem; font-weight: 700; color: #d97706;">{}</div>
        </div>
        """.format(created_at.strftime('%Y-%m-%d') if hasattr(created_at, 'strftime') else str(created_at)), unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div style="background: #f8fafc; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #8b5cf6;">
            <h4 style="margin: 0; color: #6d28d9;">👤 Portfolio ID</h4>
            <div style="font-size: 1.2rem; font-weight: 600; color: #7c3aed;">{}</div>
        </div>
        """.format(portfolio.get('id', 'N/A')), unsafe_allow_html=True)
    
    # Portfolio description
    if portfolio.get('description'):
        st.markdown("### 📝 Portfolio Strategy")
        st.info(portfolio.get('description', 'No strategy description available'))
    
    # Holdings section with institutional formatting
    with st.spinner("Loading portfolio holdings..."):
        holdings = get_portfolio_holdings(portfolio['id'])
    
    # Initialize holdings_data to avoid UnboundLocalError
    holdings_data = []
    
    if holdings:
        st.markdown("### 📋 Portfolio Holdings")
        
        # Holdings summary
        total_value = sum(float(h.get('market_value', 0)) for h in holdings if h.get('market_value'))
        total_cost = sum(float(h['average_cost']) * float(h['shares_held']) for h in holdings if h.get('average_cost') and h.get('shares_held'))
        total_return = total_value - total_cost
        total_return_pct = (total_return / total_cost * 100) if total_cost > 0 else 0
        
        # Portfolio performance metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown("""
            <div style="background: #f0fdf4; padding: 1rem; border-radius: 10px; text-align: center;">
                <div style="font-size: 0.875rem; color: #166534;">Total Value</div>
                <div style="font-size: 1.25rem; font-weight: 700; color: #16a34a;">${:,.2f}</div>
            </div>
            """.format(float(total_value) if total_value else 0), unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div style="background: #fef2f2; padding: 1rem; border-radius: 10px; text-align: center;">
                <div style="font-size: 0.875rem; color: #991b1b;">Total Cost</div>
                <div style="font-size: 1.25rem; font-weight: 700; color: #dc2626;">${:,.2f}</div>
            </div>
            """.format(float(total_cost) if total_cost else 0), unsafe_allow_html=True)
        
        with col3:
            color = "#16a34a" if total_return >= 0 else "#dc2626"
            total_return_float = float(total_return) if total_return else 0
            st.markdown(f"""
            <div style="background: {'#f0fdf4' if total_return >= 0 else '#fef2f2'}; padding: 1rem; border-radius: 10px; text-align: center;">
                <div style="font-size: 0.875rem; color: {color};">Total Return</div>
                <div style="font-size: 1.25rem; font-weight: 700; color: {color};">${total_return_float:,.2f}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            color = "#16a34a" if total_return_pct >= 0 else "#dc2626"
            st.markdown(f"""
            <div style="background: {'#f0fdf4' if total_return_pct >= 0 else '#fef2f2'}; padding: 1rem; border-radius: 10px; text-align: center;">
                <div style="font-size: 0.875rem; color: {color};">Return %</div>
                <div style="font-size: 1.25rem; font-weight: 700; color: {color};">{total_return_pct:+.2f}%</div>
            </div>
            """, unsafe_allow_html=True)
        
        # Holdings table with institutional formatting
        st.markdown("#### 📊 Detailed Holdings")
        
        # Process holdings in batches to avoid timeout
        batch_size = 10
        
        for i in range(0, len(holdings), batch_size):
            batch = holdings[i:i+batch_size]
            
            # Show progress for large portfolios
            if len(holdings) > 20:
                progress = (i + len(batch)) / len(holdings)
                st.progress(progress, text=f"Processing holdings {i+len(batch)}/{len(holdings)}...")
            
            for holding in batch:
                market_value = float(holding.get('market_value', 0)) if holding.get('market_value') else 0
                average_cost = float(holding['average_cost']) if isinstance(holding['average_cost'], str) else holding['average_cost']
                shares_held = float(holding['shares_held']) if isinstance(holding['shares_held'], str) else holding['shares_held']
                cost_basis = average_cost * shares_held
                unrealized_pnl = market_value - cost_basis
                unrealized_pct = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0
                
                holdings_data.append({
                    'Symbol': holding.get('symbol', 'N/A'),
                    'Shares': format_shares(shares_held),
                    'Avg Cost': format_currency(average_cost),
                    'Current Price': format_currency(holding.get('current_price', 0)),
                    'Market Value': format_currency(market_value),
                    'Cost Basis': format_currency(cost_basis),
                    'P&L %': format_percentage(unrealized_pct),
                    'Weight': f"{(float(market_value)/float(total_value)*100):.2f}%" if total_value and market_value else "0.00%"
                })
        
        if holdings_data:
            df_holdings = pd.DataFrame(holdings_data)
            
            # Style the dataframe with institutional formatting
            def highlight_pnl(val):
                color = 'inherit'
                if isinstance(val, str) and val.startswith('+'):
                    color = '#16a34a'
                elif isinstance(val, str) and val.startswith('-'):
                    color = '#dc2626'
                return f'color: {color}'
            
            # Display the holdings table without View Analysis column
            display_columns = ['Symbol', 'Shares', 'Avg Cost', 'Current Price', 'Market Value', 'Cost Basis', 'P&L %', 'Weight']
            df_display = df_holdings[display_columns]
            
            # Apply styling to P&L % column
            styled_df = df_display.style.applymap(highlight_pnl, subset=['P&L %'])
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            
            # Add View Analysis buttons in a clean grid layout
            st.markdown("#### 📊 Stock Analysis")
            
            # Calculate optimal grid layout (4 columns max for desktop)
            num_holdings = len(holdings_data)
            cols_per_row = min(4, max(2, num_holdings))
            cols = st.columns(cols_per_row)
            
            for i, holding_data in enumerate(holdings_data):
                col_idx = i % cols_per_row
                symbol = holding_data['Symbol']
                
                with cols[col_idx]:
                    if st.button(f"📊 {symbol}", key=f"overview_analysis_btn_{symbol}", 
                               help=f"View detailed analysis for {symbol}",
                               use_container_width=True):
                        # Clear any previous analysis state
                        if 'show_symbol_analysis' in st.session_state:
                            st.session_state.show_symbol_analysis = False
                        if 'selected_symbol_for_analysis' in st.session_state:
                            del st.session_state.selected_symbol_for_analysis
                        
                        # Set new symbol for analysis
                        st.session_state.selected_symbol_for_analysis = symbol
                        st.session_state.show_symbol_analysis = True
                        st.success(f"🔄 Loading analysis for {symbol}...")
                        st.rerun()
            
            # Portfolio allocation chart
            st.markdown("#### 📊 Portfolio Allocation")
            
            # Create allocation pie chart
            fig = go.Figure(data=[go.Pie(
                labels=[h['symbol'] for h in holdings],
                values=[float(h.get('market_value', 0)) for h in holdings],
                hole=0.3,
                textinfo='label+percent',
                textposition='outside'
            )])
            
            fig.update_layout(
                title="Portfolio Allocation by Market Value",
                plot_bgcolor='white',
                paper_bgcolor='white',
                showlegend=True,
                legend=dict(
                    orientation="v",
                    yanchor="middle",
                    y=0.5,
                    xanchor="left",
                    font=dict(size=10)
                )
            )
            
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No holdings data available for this portfolio")
        
        # Clear progress bar
        if len(holdings) > 20:
            st.empty()
        
        if holdings_data:
            # Display as a professional table
            df_holdings = pd.DataFrame(holdings_data)
            
            # Configure column display
            column_config = {
                "Symbol": st.column_config.TextColumn("Symbol", width=80),
                "Shares": st.column_config.TextColumn("Shares", width=100),
                "Avg Cost": st.column_config.TextColumn("Avg Cost", width=100),
                "Current Price": st.column_config.TextColumn("Current Price", width=100),
                "Signal": st.column_config.TextColumn("Signal", width=80),
                "Target Price": st.column_config.TextColumn("Target Price", width=100)
            }
            
            # Display the dataframe
            st.dataframe(
                df_holdings,
                column_config=column_config,
                hide_index=True,
                use_container_width=True
            )
            
            # Add View Analysis buttons below the table
            st.markdown("#### 📊 Stock Analysis (Technical & Fundamentals)")
            cols = st.columns(min(len(holdings_data), 4))  # Max 4 columns wide
            
            for i, holding_data in enumerate(holdings_data):
                col_idx = i % len(cols)
                with cols[col_idx]:
                    if st.button(f"📊 {holding_data['Symbol']}", key=f"details_analyze_{holding_data['Symbol']}", help=f"View detailed analysis for {holding_data['Symbol']}"):
                        # Clear any previous analysis state
                        if 'show_symbol_analysis' in st.session_state:
                            st.session_state.show_symbol_analysis = False
                        if 'selected_symbol_for_analysis' in st.session_state:
                            del st.session_state.selected_symbol_for_analysis
                        
                        # Set new symbol for analysis
                        st.session_state.selected_symbol_for_analysis = holding_data['Symbol']
                        st.session_state.show_symbol_analysis = True
                        st.success(f"🔄 Loading analysis for {holding_data['Symbol']}...")
                        st.rerun()
            
            st.markdown("---")
            
            # Portfolio summary
            total_pnl = total_value - total_cost
            total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
            
            st.markdown("#### 💰 Portfolio Summary")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Value", format_currency(total_value, "$0.00"))
            
            with col2:
                st.metric("Total Cost", format_currency(total_cost, "$0.00"))
            
            with col3:
                st.metric("Total P&L", format_currency(total_pnl, "$0.00"))
            
            with col4:
                st.metric("Return %", f"{float(total_pnl_pct):.2f}%" if total_pnl_pct is not None else "0.00%")
        
        # Add symbol form
        if st.session_state.get('show_add_symbol', False):
            st.markdown("#### ➕ Add Symbol to Portfolio")
            
            with st.form("add_symbol_form"):
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    symbol = st.text_input("Symbol*", placeholder="e.g., AAPL").upper()
                
                with col2:
                    asset_type = st.selectbox("Type*", ["stock", "regular_etf", "3x_etf"])
                
                with col3:
                    shares = st.number_input("Shares", min_value=0.0, value=100.0, step=10.0)
                
                with col4:
                    avg_cost = st.number_input("Avg Cost ($)", min_value=0.0, value=0.0, step=0.01)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("➕ Add Symbol", type="primary"):
                        if symbol:
                            holding = add_portfolio_holding(portfolio['id'], symbol, asset_type, shares, avg_cost)
                            if holding:
                                st.success(f"✅ {symbol} added to portfolio!")
                                st.session_state.show_add_symbol = False
                                st.rerun()
                        else:
                            st.error("Symbol is required")
                
                with col2:
                    if st.form_submit_button("❌ Cancel"):
                        st.session_state.show_add_symbol = False
                        st.rerun()
    
    # Show message if no holdings
    if not holdings:
        st.info("📋 No holdings in this portfolio. Add symbols to get started!")

def show_analysis_results(result: Dict[str, Any]):
    """Show portfolio analysis results"""
    st.markdown("### 📊 Analysis Results")
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📈 Symbols Analyzed", result['symbols_analyzed'])
    
    with col2:
        st.metric("🎯 Signals Generated", result['signals_generated'])
    
    with col3:
        st.metric("✅ Success Rate", f"{result['success_rate']:.1f}%")
    
    with col4:
        st.metric("📅 Analysis Date", result['analysis_date'])
    
    # Signal results
    if result.get('results'):
        st.markdown("#### 🎯 Generated Signals")
        
        signals_data = []
        for signal_result in result['results']:
            signals_data.append({
                'Symbol': signal_result['symbol'],
                'Signal': signal_result['signal'],
                'Confidence': f"{signal_result['confidence']:.1f}%",
                'Price': f"${signal_result['price']:.2f}"
            })
        
        df_signals = pd.DataFrame(signals_data)
        
        # Color code signals
        def color_signal(val):
            if val == 'BUY':
                return 'background-color: #E8F5E8; color: #00C851'
            elif val == 'SELL':
                return 'background-color: #FFEBEE; color: #FF4444'
            else:
                return 'background-color: #FFF3E0; color: #FF8800'
        
        styled_df = df_signals.style.applymap(color_signal, subset=['Signal'])
        st.dataframe(styled_df, use_container_width=True)
        
        # Signal distribution chart
        signal_counts = {'BUY': 0, 'SELL': 0, 'HOLD': 0}
        for signal_result in result['results']:
            signal_type = signal_result['signal']
            if signal_type in signal_counts:
                signal_counts[signal_type] += 1
        
        if sum(signal_counts.values()) > 0:
            fig = PortfolioVisualizer.create_signal_distribution_chart(signal_counts)
            st.plotly_chart(fig, use_container_width=True)

def load_all_symbol_data(symbol: str):
    """Load all data types for a single symbol (similar to Trading Dashboard)"""
    # All data types to load (same as Trading Dashboard)
    all_data_types = [
        "price_historical",
        "price_current", 
        "price_intraday_15m",
        "fundamentals",
        "indicators",
        "news",
        "earnings",
        "industry_peers",
    ]
    
    with st.spinner(f"Loading all data for {symbol} ({', '.join(all_data_types)})..."):
        try:
            response = python_client.post("api/v1/refresh", json_data={
                "symbols": [symbol],
                "data_types": all_data_types,
                "force": True,  # Always force refresh for Load All Data
            }, timeout=180)  # 3 minute timeout for single symbol data load
            
            if response and response.get("success"):
                st.success(f"✅ Load All triggered successfully for {symbol}!")
                st.info(f"Loaded data types: {', '.join(all_data_types)}")
                
                # Clear cached analysis to force refresh with new data
                cache_key = f"analysis_{symbol}"
                if cache_key in st.session_state:
                    del st.session_state[cache_key]
                
                # Auto-refresh analysis after loading data
                st.rerun()
                
                # Show response details in expander
                with st.expander("📊 Load Details", expanded=False):
                    st.json(response)
            else:
                st.error(f"❌ Failed to load data: {response.get('error', 'Unknown error')}")
                
        except Exception as e:
            st.error(f"❌ Error loading data for {symbol}: {str(e)}")

def load_all_portfolio_data(portfolio_id: str):
    """Load all data types for all symbols in portfolio (similar to Trading Dashboard)"""
    holdings = get_portfolio_holdings(portfolio_id)
    
    if not holdings:
        st.warning("⚠️ No symbols found in portfolio to load data for")
        return
    
    symbols = [holding['symbol'] for holding in holdings]
    
    # All data types to load (same as Trading Dashboard)
    all_data_types = [
        "price_historical",
        "price_current", 
        "price_intraday_15m",
        "fundamentals",
        "indicators",
        "news",
        "earnings",
        "industry_peers",
    ]
    
    with st.spinner(f"Loading all data for {len(symbols)} symbols ({', '.join(all_data_types)})..."):
        try:
            response = python_client.post("api/v1/refresh", json_data={
                "symbols": symbols,
                "data_types": all_data_types,
                "force": True,  # Always force refresh for Load All Data
            }, timeout=300)  # 5 minute timeout for portfolio-wide data load
            
            if response and response.get("success"):
                st.success(f"✅ Load All triggered successfully for {len(symbols)} symbols!")
                st.info(f"Loaded data types: {', '.join(all_data_types)}")
                
                # Show response details in expander
                with st.expander("📊 Load Details", expanded=False):
                    st.json(response)
            else:
                st.error(f"❌ Failed to load data: {response.get('error', 'Unknown error')}")
                
        except Exception as e:
            st.error(f"❌ Error loading portfolio data: {str(e)}")

def load_portfolio_data(portfolio_id: str):
    """Load data for all symbols in portfolio"""
    holdings = get_portfolio_holdings(portfolio_id)
    
    if holdings:
        symbols = [holding['symbol'] for holding in holdings]
        
        with st.spinner(f"Loading data for {len(symbols)} symbols..."):
            try:
                response = python_client.post("api/v1/refresh", json_data={
                    "symbols": symbols,
                    "data_types": ["price_historical", "indicators"],
                    "force": True
                })
                
                if response and response.get("success"):
                    st.success(f"✅ Data loaded successfully for {len(symbols)} symbols!")
                else:
                    st.error(f"❌ Failed to load data: {response.get('error', 'Unknown error')}")
            except Exception as e:
                st.error(f"❌ Error loading data: {str(e)}")
    else:
        st.warning("⚠️ No symbols found in portfolio")

def show_scheduling_section(portfolio_id: str):
    """Show scheduling section for portfolio"""
    st.markdown("### ⏰ Scheduled Analysis")
    
    schedules = get_portfolio_schedules(portfolio_id)
    
    if schedules:
        st.markdown("#### 📅 Active Schedules")
        
        for schedule in schedules:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown(f"**{schedule['schedule_type'].title()}**")
                st.caption(f"at {schedule['schedule_time']}")
            
            with col2:
                if schedule['next_run']:
                    st.markdown(f"**Next Run:**")
                    st.caption(schedule['next_run'].strftime('%Y-%m-%d %H:%M'))
            
            with col3:
                status = "🟢 Active" if schedule['is_active'] else "🔴 Inactive"
                st.markdown(f"**Status:** {status}")
            
            with col4:
                if st.button("🗑️", key=f"delete_schedule_{schedule['id']}", help="Delete Schedule"):
                    # TODO: Implement delete schedule
                    st.warning("Delete schedule feature coming soon!")
    else:
        st.info("⏰ No scheduled analyses set up")
    
    # Add new schedule
    with st.expander("➕ Schedule Analysis", expanded=False):
        with st.form("schedule_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                schedule_type = st.selectbox("Schedule Type", ["daily", "weekly", "monthly"])
                schedule_time = st.time_input("Time", value=time(9, 0))  # 9:00 AM default
            
            with col2:
                schedule_day = None
                if schedule_type == "weekly":
                    schedule_day = st.selectbox("Day of Week", [
                        (1, "Monday"), (2, "Tuesday"), (3, "Wednesday"),
                        (4, "Thursday"), (5, "Friday"), (6, "Saturday"), (7, "Sunday")
                    ], format_func=lambda x: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][x-1])
                elif schedule_type == "monthly":
                    schedule_day = st.selectbox("Day of Month", list(range(1, 32)))
            
            if st.form_submit_button("⏰ Create Schedule", type="primary"):
                schedule = create_portfolio_schedule(portfolio_id, schedule_type, schedule_time, schedule_day)
                if schedule:
                    st.success("✅ Schedule created successfully!")
                    st.rerun()

# ========================================
# ========================================
# Symbol Analysis Functions
# ========================================

def get_symbol_analysis(symbol: str, asset_type: str = "stock"):
    """Get detailed analysis for a specific symbol"""
    try:
        payload = {
            "symbol": symbol,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "asset_type": asset_type
        }
        
        response = python_client.post("api/v1/universal/signal/universal", json_data=payload)
        
        if response and response.get("success"):
            return response["data"]
        else:
            return {"error": response.get("error", "Unknown error")}
            
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}

def refresh_symbol_analysis(symbol: str, asset_type: str = "stock"):
    """Refresh analysis for a specific symbol"""
    with st.spinner(f"Refreshing analysis for {symbol}..."):
        analysis_data = get_symbol_analysis(symbol, asset_type)
        
        if analysis_data and not analysis_data.get('error'):
            st.success(f"✅ Analysis refreshed for {symbol}!")
            st.session_state[f"analysis_{symbol}"] = analysis_data
        else:
            st.error(f"❌ Error refreshing {symbol}: {analysis_data.get('error', 'Unknown error')}")

def show_symbol_analysis(symbol: str):
    """Show detailed analysis for a symbol using shared component"""
    st.markdown(f"### 📊 Detailed Analysis - {symbol}")
    
    # Action buttons for symbol analysis
    st.markdown("#### 🎯 Analysis Actions")
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        if st.button("🔄 Load All Data", type="primary", use_container_width=True, help=f"Load fresh data for {symbol}"):
            load_all_symbol_data(symbol)
    
    with col2:
        if st.button("📊 Refresh Analysis", use_container_width=True, help=f"Refresh analysis for {symbol}"):
            refresh_symbol_analysis(symbol)
    
    with col3:
        if st.button("← Back to Portfolio", use_container_width=True):
            st.session_state.show_symbol_analysis = False
            st.rerun()
    
    st.markdown("---")
    
    # ALWAYS get fresh analysis for the selected symbol (no caching)
    with st.spinner(f"Loading fresh analysis for {symbol}..."):
        asset_type = "stock"  # Default, could be enhanced to get from holdings
        analysis_data = get_symbol_analysis(symbol, asset_type)
    
    # Cache the analysis for potential reuse within this session
    cache_key = f"analysis_{symbol}"
    if analysis_data and not analysis_data.get('error'):
        st.session_state[cache_key] = analysis_data
    
    # Display analysis using shared component
    if analysis_data and not analysis_data.get('error'):
        display_signal_analysis(symbol, analysis_data, show_header=True, show_debug=True)
    else:
        display_no_data_message(symbol, analysis_data.get('error') if analysis_data else None)
    
    # Add Fundamentals Analysis section
    st.markdown("---")
    st.markdown("### 💰 Fundamentals Analysis")
    
    # Add tabs for different analysis types
    tab1, tab2 = st.tabs(["📊 Technical Analysis", "💰 Fundamentals Analysis"])
    
    with tab1:
        # Current technical analysis (already displayed above)
        if analysis_data and not analysis_data.get('error'):
            st.info("Technical analysis shown above")
        else:
            display_no_data_message(symbol, analysis_data.get('error') if analysis_data else None)
    
    with tab2:
        # Fundamentals analysis
        try:
            with st.spinner(f"Loading fundamentals analysis for {symbol}..."):
                response = requests.get(f"{python_api_url}/api/v1/growth-quality/growth-health/{symbol}")
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Validate that we have real data (not placeholder)
                    if data.get('symbol') and data.get('structural_risk'):
                        _render_fundamentals_analysis(data)
                        
                        # Add comprehensive analysis section
                        st.markdown("---")
                        _render_comprehensive_fundamentals_analysis(symbol)
                        
                    else:
                        st.error("❌ Incomplete fundamentals data received")
                        st.info("💡 Try loading fresh data using the 'Load All Data' button")
                        
                        # Show retry button
                        if st.button("🔄 Retry Fundamentals Analysis", key=f"retry_fundamentals_{symbol}"):
                            st.rerun()
                            
                elif response.status_code == 404:
                    st.error(f"❌ No fundamentals data available for {symbol}")
                    st.info("💡 Please load fundamentals data first using the 'Load All Data' button")
                    
                    # Show retry button
                    if st.button("🔄 Load Data & Retry", key=f"load_retry_fundamentals_{symbol}"):
                        # Trigger data load
                        load_all_symbol_data(symbol)
                        st.rerun()
                        
                else:
                    error_detail = "Unknown error"
                    try:
                        error_json = response.json()
                        error_detail = error_json.get('detail', str(error_json))
                    except:
                        error_detail = response.text
                    
                    st.error(f"❌ Failed to load fundamentals analysis: {response.status_code}")
                    st.error(f"🔍 Details: {error_detail}")
                    
                    # Show retry button
                    if st.button("🔄 Retry Analysis", key=f"retry_error_fundamentals_{symbol}"):
                        st.rerun()
                    
        except requests.exceptions.RequestException as e:
            st.error(f"❌ Connection error: Unable to reach analysis service")
            st.error(f"🔍 Details: {str(e)}")
            st.info("💡 Please check if the Python Worker service is running")
            
            # Show retry button
            if st.button("🔄 Retry Connection", key=f"retry_connection_{symbol}"):
                st.rerun()
                
        except Exception as e:
            st.error(f"❌ Unexpected error in fundamentals analysis")
            st.error(f"🔍 Details: {str(e)}")
            st.info("💡 Please try refreshing the page or contact support")
            
            # Show retry button
            if st.button("🔄 Refresh Page", key=f"refresh_page_{symbol}"):
                st.rerun()


def _render_comprehensive_fundamentals_analysis(symbol: str):
    """Render comprehensive fundamentals analysis with professional visualizations"""
    try:
        # Fetch early warning analysis
        response = requests.get(f"{python_api_url}/api/v1/growth-quality/early-warning/{symbol}")
        
        if response.status_code == 200:
            analysis_data = response.json()
            _render_fundamentals_risk_overview(analysis_data, symbol)
            _render_fundamentals_detailed_flags(analysis_data)
            _render_fundamentals_metrics_dashboard(analysis_data)
        elif response.status_code == 404:
            st.warning(f"⚠️ No fundamentals data available for {symbol}")
        else:
            st.error(f"❌ Failed to load comprehensive analysis for {symbol} (HTTP {response.status_code})")
            
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Network error loading analysis for {symbol}: {str(e)}")
    except Exception as e:
        st.error(f"❌ Error loading comprehensive analysis for {symbol}: {str(e)}")

def _render_fundamentals_risk_overview(analysis_data: Dict[str, Any], symbol: str):
    """Render risk overview with professional styling"""
    overall_risk = analysis_data.get('overall_risk', 'GREEN')
    
    risk_colors = {
        'GREEN': '#38ef7d',
        'YELLOW': '#f5576c', 
        'RED': '#eb3349'
    }
    
    risk_icons = {
        'GREEN': '✅',
        'YELLOW': '⚠️',
        'RED': '🚨'
    }
    
    risk_descriptions = {
        'GREEN': 'Low Risk - Healthy growth fundamentals',
        'YELLOW': 'Medium Risk - Early warning signs detected',
        'RED': 'High Risk - Structural breakdown detected'
    }
    
    # Main risk card
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {risk_colors.get(overall_risk, '#38ef7d')} 0%, #667eea 100%); 
                padding: 20px; border-radius: 15px; color: white; margin: 20px 0;">
        <h3>{risk_icons.get(overall_risk, '')} {symbol} Overall Risk: {overall_risk}</h3>
        <p>{risk_descriptions.get(overall_risk, '')}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Domain risks
    domain_risks = analysis_data.get('domain_risks', {})
    if domain_risks:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📊 Revenue Quality")
            revenue_risk = domain_risks.get('revenue_risk', 'NO_RISK')
            _render_domain_risk_gauge(revenue_risk, "Revenue Quality")
            
            st.markdown("### 💰 Capital Efficiency")
            capital_risk = domain_risks.get('capital_risk', 'NO_RISK')
            _render_domain_risk_gauge(capital_risk, "Capital Efficiency")
        
        with col2:
            st.markdown("### 📈 Margin Stress")
            margin_risk = domain_risks.get('margin_risk', 'NO_RISK')
            _render_domain_risk_gauge(margin_risk, "Margin Stress")
            
            st.markdown("### 🎯 Management Signals")
            mgmt_risk = domain_risks.get('management_risk', 'NO_RISK')
            _render_domain_risk_gauge(mgmt_risk, "Management Signals")

def _render_domain_risk_gauge(risk_level: str, title: str):
    """Render individual domain risk gauge"""
    risk_values = {'NO_RISK': 0, 'EARLY_STRESS': 50, 'STRUCTURAL_BREAKDOWN': 100}
    risk_colors = {'NO_RISK': '#38ef7d', 'EARLY_STRESS': '#f5576c', 'STRUCTURAL_BREAKDOWN': '#eb3349'}
    
    fig = go.Figure(go.Indicator(
        mode = "gauge+number+delta",
        value = risk_values.get(risk_level, 0),
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': title},
        delta = {'reference': 0},
        gauge = {
            'axis': {'range': [None, 100]},
            'bar': {'color': risk_colors.get(risk_level, '#38ef7d')},
            'steps': [
                {'range': [0, 33], 'color': "lightgray"},
                {'range': [33, 66], 'color': "gray"},
                {'range': [66, 100], 'color': "darkgray"}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 80
            }
        }
    ))
    
    fig.update_layout(height=250, margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)

def _render_fundamentals_detailed_flags(analysis_data: Dict[str, Any]):
    """Render detailed flag analysis"""
    st.markdown("### 🔍 Detailed Risk Flags Analysis")
    
    # Warnings and insights
    warnings = analysis_data.get('warnings', [])
    insights = analysis_data.get('insights', [])
    
    if warnings:
        st.markdown("#### ⚠️ Risk Warnings")
        for warning in warnings:
            st.error(f"• {warning}")
    
    if insights:
        st.markdown("#### ✅ Positive Insights")
        for insight in insights:
            st.success(f"• {insight}")
    
    # Metrics analysis
    metrics = analysis_data.get('metrics', {})
    if metrics:
        st.markdown("#### 📊 Key Metrics Analysis")
        
        col1, col2 = st.columns(2)
        
        with col1:
            for metric_name, value in list(metrics.items())[:len(metrics)//2]:
                st.metric(metric_name.replace('_', ' ').title(), str(value))
        
        with col2:
            for metric_name, value in list(metrics.items())[len(metrics)//2:]:
                st.metric(metric_name.replace('_', ' ').title(), str(value))

def _render_fundamentals_metrics_dashboard(analysis_data: Dict[str, Any]):
    """Render comprehensive metrics dashboard"""
    st.markdown("### 📈 Fundamentals Metrics Dashboard")
    
    # Create metrics overview
    metrics = analysis_data.get('metrics', {})
    if not metrics:
        st.info("No detailed metrics available")
        return
    
    # Key financial metrics
    col1, col2, col3, col4 = st.columns(4)
    
    key_metrics = {
        'receivables_vs_revenue_growth': 'Receivables vs Revenue',
        'margin_trend': 'Margin Trend',
        'roe_trend': 'ROE Trend',
        'roic_trend': 'ROIC Trend',
        'growth_vs_capital': 'Growth vs Capital',
        'debt_level': 'Debt Level'
    }
    
    for i, (metric_key, display_name) in enumerate(list(key_metrics.items())[:4]):
        col = [col1, col2, col3, col4][i]
        with col:
            value = metrics.get(metric_key, 'N/A')
            st.metric(display_name, str(value))
    
    # Analysis date
    analysis_date = analysis_data.get('analysis_date', 'Unknown')
    st.caption(f"Analysis as of: {analysis_date}")


def _render_fundamentals_analysis(data: Dict[str, Any]):
    """Render institutional-grade fundamentals analysis with corrected logic"""
    symbol = data.get('symbol', 'Unknown')
    
    # Structural Risk Assessment
    structural_risk = data.get('structural_risk', 'LOW')
    structural_icons = {
        'LOW': '🟢',
        'MEDIUM': '🟡',
        'HIGH': '🔴'
    }
    
    structural_descriptions = {
        'LOW': 'Low Structural Risk - Balance sheet strong, revenue quality clean',
        'MEDIUM': 'Medium Structural Risk - Some concerns but no critical issues',
        'HIGH': 'High Structural Risk - Structural issues or red flags detected'
    }
    
    # Growth Phase Assessment
    growth_phase = data.get('growth_phase', 'MATURE_COMPOUNDER')
    growth_icons = {
        'HEALTHY_COMPOUNDER': '🟢',
        'MATURE_COMPOUNDER': '🟡',
        'GROWTH_DEGRADATION': '🟠',
        'GROWTH_BREAKDOWN': '🔴'
    }
    
    growth_descriptions = {
        'HEALTHY_COMPOUNDER': 'Accelerating Compounder - Revenue + margins + ROIC expanding',
        'MATURE_COMPOUNDER': 'Mature Compounder - Growth persists but efficiency and margins are no longer expanding',
        'GROWTH_DEGRADATION': 'Growth Degrading - Growth trajectory showing material slowdown',
        'GROWTH_BREAKDOWN': 'Growth Breakdown - Structural business issues detected'
    }
    
    # Investment Posture
    investment_posture = data.get('investment_posture', 'HOLD_SELECTIVE_ADD')
    posture_icons = {
        'BUY': '🟢',
        'HOLD_SELECTIVE_ADD': '🟡',
        'TRIM_REDUCE': '🟠',
        'EXIT_AVOID': '🔴'
    }
    
    posture_descriptions = {
        'BUY': 'BUY - Aggressive accumulation recommended',
        'HOLD_SELECTIVE_ADD': 'HOLD / SELECTIVE ADD - Suitable for core holding; add selectively during market pullbacks',
        'TRIM_REDUCE': 'TRIM / REDUCE - Reduce position size',
        'EXIT_AVOID': 'EXIT / AVOID - Capital preservation priority'
    }
    
    # Forward Returns
    forward_returns = data.get('forward_return_expectation', '6-10% annualized (cash flows + buybacks)')
    
    # Main Assessment Card
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 25px; border-radius: 15px; color: white; margin: 20px 0;">
        <h2>{structural_icons.get(structural_risk, '🟢')} {symbol} Fundamentals Assessment</h2>
        <p style="font-size: 18px; margin: 15px 0;"><strong>{structural_descriptions.get(structural_risk, '')}</strong></p>
    </div>
    """, unsafe_allow_html=True)
    
    # Growth Phase and Investment Posture
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"""
        <div style="background: {growth_phase == 'HEALTHY_COMPOUNDER' and '#d4edda' or growth_phase == 'MATURE_COMPOUNDER' and '#fff3cd' or growth_phase == 'GROWTH_DEGRADATION' and '#f8d7da' or '#f5c6cb'}; 
                    padding: 20px; border-radius: 10px; margin: 10px 0;">
            <h3>{growth_icons.get(growth_phase, '🟡')} Growth Phase</h3>
            <p><strong>{growth_descriptions.get(growth_phase, '')}</strong></p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div style="background: {investment_posture == 'BUY' and '#d4edda' or investment_posture == 'HOLD_SELECTIVE_ADD' and '#fff3cd' or investment_posture == 'TRIM_REDUCE' and '#f8d7da' or '#f5c6cb'}; 
                    padding: 20px; border-radius: 10px; margin: 10px 0;">
            <h3>{posture_icons.get(investment_posture, '🟡')} Investment Posture</h3>
            <p><strong>{posture_descriptions.get(investment_posture, '')}</strong></p>
        </div>
        """, unsafe_allow_html=True)
    
    # Forward Return Expectation
    st.markdown(f"""
    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 15px 0; border-left: 5px solid #007bff;">
        <h3>📈 Forward Return Outlook</h3>
        <p style="font-size: 16px;"><strong>{forward_returns}</strong></p>
    </div>
    """, unsafe_allow_html=True)
    
    # Key Insights
    reasoning = data.get('reasoning', [])
    if reasoning:
        st.markdown("### 🎯 Key Assessment Points")
        for point in reasoning:
            st.success(f"• {point}")
    
    # Risk Factors with Critical Impact Analysis
    risk_factors = data.get('risk_factors', [])
    if risk_factors:
        st.markdown("### ⚠️ Critical Risk Factors")
        for factor in risk_factors:
            # Determine risk impact level
            if any(phrase in factor.lower() for phrase in ['margin declining', 'growth vs capital mismatch', 'structural breakdown']):
                st.error(f"🚨 **CRITICAL**: {factor} - Prevents BUY recommendation")
            elif any(phrase in factor.lower() for phrase in ['monitor', 'concerns', 'pressure']):
                st.warning(f"⚠️ **WARNING**: {factor} - May limit returns")
            else:
                st.info(f"ℹ️ **NOTE**: {factor}")
    
    # Risk-to-Decision Summary
    st.markdown("### 📋 Risk-to-Decision Analysis")
    
    # Show why investment posture was chosen
    if investment_posture == 'BUY':
        st.success("✅ **BUY Justification**: All critical risk factors cleared - Growth phase accelerating with strong fundamentals")
    elif investment_posture == 'HOLD_SELECTIVE_ADD':
        if growth_phase == 'MATURE_COMPOUNDER':
            st.info("🟡 **HOLD Justification**: Mature compounder with stable but non-accelerating growth - Suitable for core holding")
        else:
            st.warning("🟡 **HOLD Justification**: Some risk factors present - Monitor closely")
    elif investment_posture == 'TRIM_REDUCE':
        st.warning("🟠 **TRIM Justification**: Growth degradation or medium structural risk detected - Reduce exposure")
    elif investment_posture == 'EXIT_AVOID':
        st.error("🔴 **EXIT Justification**: Structural breakdown or growth breakdown detected - Capital preservation priority")
    
    # Risk Gate Status
    st.markdown("### 🚪 Risk Gate Status")
    
    # Get domain risks from analysis data
    domain_risks = data.get('domain_risks', {})
    
    # Ensure domain_risks is a dictionary
    if not isinstance(domain_risks, dict):
        st.error("❌ Invalid domain risks data format")
        domain_risks = {}
    
    gates = {
        "Revenue Quality": domain_risks.get('revenue_risk', 'NO_RISK') == 'NO_RISK',
        "Margin Stability": domain_risks.get('margin_risk', 'NO_RISK') == 'NO_RISK', 
        "Capital Efficiency": domain_risks.get('capital_risk', 'NO_RISK') == 'NO_RISK',
        "Structural Risk": structural_risk == 'LOW'
    }
    
    for gate_name, passed in gates.items():
        if passed:
            st.success(f"✅ {gate_name}: PASSED")
        else:
            st.error(f"❌ {gate_name}: FAILED - Blocks BUY signal")
    
    # Golden Rule Status
    st.markdown("### 🏛️ Golden Rule Check")
    if investment_posture == 'BUY' and growth_phase == 'HEALTHY_COMPOUNDER':
        st.success("✅ **PASSED**: BUY allowed only when Growth Phase = Accelerating")
    elif investment_posture != 'BUY' and growth_phase != 'HEALTHY_COMPOUNDER':
        st.info("ℹ️ **CORRECTLY APPLIED**: Non-BUY posture for non-accelerating growth")
    else:
        st.warning("⚠️ **REVIEW**: Check if posture matches growth phase")
    
    # Opportunities
    opportunities = data.get('opportunities', [])
    if opportunities:
        st.markdown("### 💡 Opportunities")
        for opportunity in opportunities:
            st.info(f"• {opportunity}")
    
    # Confidence Score
    confidence = data.get('confidence', 0.85)
    st.markdown(f"""
    <div style="background: #e9ecef; padding: 15px; border-radius: 8px; margin: 15px 0;">
        <p><strong>Analysis Confidence:</strong> {confidence:.1%}</p>
        <div style="background: #ddd; height: 10px; border-radius: 5px;">
            <div style="background: #28a745; width: {confidence*100}%; height: 10px; border-radius: 5px;"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Critical Rule Display (Golden Rule)
    if investment_posture == 'BUY' and growth_phase != 'HEALTHY_COMPOUNDER':
        st.error("🚨 **CRITICAL WARNING**: This analysis shows a BUY recommendation but growth phase is not accelerating. This violates the golden rule: NEVER allow BUY when Growth Phase ≠ Accelerating. Please review the analysis logic.")
    elif investment_posture == 'BUY' and growth_phase == 'HEALTHY_COMPOUNDER':
        st.success("✅ **Valid BUY Signal**: Growth phase is accelerating, supporting the BUY recommendation.")
    elif investment_posture == 'HOLD_SELECTIVE_ADD' and growth_phase == 'MATURE_COMPOUNDER':
        st.info("✅ **Valid HOLD Signal**: Mature compounder with low structural risk - appropriate for core holding.")
    
    # Analysis Date
    analysis_date = data.get('analysis_date', datetime.now().strftime('%Y-%m-%d'))
    st.caption(f"Analysis as of: {analysis_date}")


# Main Page Logic
# ========================================

def main():
    """Main page logic"""
    setup_page_config("Portfolio Analysis", "📊")
    
    # Custom CSS for institutional appearance
    st.markdown("""
    <style>
    .portfolio-header {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
        padding: 2.5rem; 
        border-radius: 15px; 
        color: white; 
        margin-bottom: 2rem; 
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        text-align: center;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
    }
    
    .institutional-metric {
        background: white;
        padding: 1.5rem; 
        border-radius: 10px; 
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        border-left: 4px solid #1e40af;
        margin-bottom: 1rem;
        transition: all 0.3s ease;
    }
    
    .institutional-metric:hover {
        box-shadow: 0 8px 12px rgba(0, 0, 0, 0.15);
        transform: translateY(-2px);
    }
    
    .risk-high {
        background: linear-gradient(135deg, #fef2f2 0%, #f87171 100%);
        border-left: 4px solid #ef4444;
    }
    
    .risk-moderate {
        background: linear-gradient(135deg, #fef3c7 0%, #fbbf24 100%);
        border-left: 4px solid #f59e0b;
    }
    
    .risk-low {
        background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
        border-left: 4px solid #22c55e;
    }
    
    .signal-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.875rem;
        font-weight: 600;
        text-align: center;
        transition: all 0.2s ease;
    }
    
    .buy-signal { 
        background: #E8F5E8; 
        color: #00C851; 
        border: 1px solid #00C851;
    }
    
    .sell-signal { 
        background: #FFEBEE; 
        color: #FF4444; 
        border: 1px solid #FF4444;
    }
    
    .hold-signal { 
        background: #FFF3E0; 
        color: #FF8800; 
        border: 1px solid #FF8800;
    }
    
    .add-signal { 
        background: #E8F5E8; 
        color: #00C851; 
        border: 1px solid #00C851;
    }
    
    .reduce-signal { 
        background: #FFF3E0; 
        color: #FF8800; 
        border: 1px solid #FF8800;
    }
    
    .institutional-table {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        overflow: hidden;
    }
    
    .institutional-table th {
        background: #f8fafc;
        font-weight: 600;
        color: #1e293b8;
        border-bottom: 2px solid #e2e8f0;
        padding: 1rem;
    }
    
    .institutional-table td {
        border-bottom: 1px solid #f1f5f9;
        padding: 0.75rem 1rem;
        color: #475569;
    }
    
    .institutional-table tr:hover {
        background: #f8fafc;
    }
    
    .portfolio-summary {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); 
        padding: 2rem; 
        border-radius: 15px; 
        margin-bottom: 2rem; 
        border: 1px solid #cbd5e1;
    }
    
    .signal-summary {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); 
        color: white; 
        padding: 2rem; 
        border-radius: 15px; 
        margin-bottom: 2rem; 
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    
    .analysis-summary {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); 
        color: white; 
        padding: 2rem; 
        border-radius: 15px; 
        margin-bottom: 2rem; 
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    
    .institutional-button {
        background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
        color: white; 
        border: none; 
        border-radius: 8px; 
        padding: 0.75rem 1.5rem; 
        font-weight: 600; 
        transition: all 0.3s ease; 
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .institutional-button:hover {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        transform: translateY(-2px);
    }
    
    .institutional-button:active {
        background: linear-gradient(135deg, #1e40af 0%, #1e40af 100%);
        transform: translateY(0px);
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    </style>
    """, unsafe_allow_html=True)
    
    # Check authentication
    if not is_authenticated():
        show_login_page()
    else:
        # Sidebar with user info only
        with st.sidebar:
            user = st.session_state.current_user
            
            st.markdown(f"### 👤 {user['full_name'] or user['username']}")
            st.caption(f"Role: {user['role'].title()}")
            
            st.divider()
            
            if st.button("🔄 Refresh Data", use_container_width=True):
                if 'selected_portfolio' in st.session_state:
                    load_portfolio_data(st.session_state.selected_portfolio)
            
            if st.button("🚪 Logout", use_container_width=True):
                logout_user()
        
        # Main content with tabs
        portfolios = get_user_portfolios()
        
        if not portfolios:
            # Show create portfolio form for first-time users
            show_portfolio_overview()
            
            st.markdown("""
            <div style="background: #f8fafc; padding: 3rem; border-radius: 15px; text-align: center; border: 2px dashed #cbd5e1;">
                <div style="font-size: 4rem; margin-bottom: 1rem;">📋</div>
                <h2 style="color: #475569; margin-bottom: 1rem;">No Portfolios Yet</h2>
                <p style="color: #64748b; margin-bottom: 2rem;">Create your first portfolio to start institutional-grade analysis</p>
            </div>
            """, unsafe_allow_html=True)
            
            show_create_portfolio_form("first_portfolio")
        else:
            # Tabbed interface for portfolio management
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📊 Portfolio Overview", 
                "📋 Portfolio Management", 
                "📈 Stock Analysis", 
                "🏢 Stock Symbols",
                "⚙️ Settings"
            ])
            
            # Check if symbol analysis is requested and show it instead of tabs
            if st.session_state.get('show_symbol_analysis', False):
                symbol = st.session_state.get('selected_symbol_for_analysis')
                if symbol:
                    # Clear any cached analysis for this symbol to ensure fresh data
                    cache_key = f"analysis_{symbol}"
                    if cache_key in st.session_state:
                        del st.session_state[cache_key]
                    
                    # Always show fresh analysis for the selected symbol
                    show_symbol_analysis(symbol)
                else:
                    st.error("No symbol selected for analysis")
                    st.session_state.show_symbol_analysis = False
                    st.rerun()
            else:
                with tab1:
                    show_portfolio_overview_tab(portfolios)
                
                with tab2:
                    show_portfolio_management_tab(portfolios)
                
                with tab3:
                    show_stock_analysis_tab(portfolios)
                
                with tab4:
                    show_stock_symbols_tab()
                
                with tab5:
                    show_settings_tab()

def show_stock_symbols_tab():
    """Stock Symbols Management Tab - Add and view stock symbols"""
    st.markdown("## 🏢 Stock Symbols Management")
    st.markdown("Manage stock symbols in the system - add new symbols and view existing ones")
    
    # Initialize session state for form
    if 'add_symbol_form_visible' not in st.session_state:
        st.session_state.add_symbol_form_visible = False
    
    # Add new symbol section
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown("### ➕ Add New Symbol")
        st.markdown("Add a new stock symbol to the system for portfolio management")
        st.caption("💡 Company information is automatically fetched from Yahoo Finance")
    
    with col2:
        if st.button("📝 Add Symbol", type="primary", use_container_width=True):
            st.session_state.add_symbol_form_visible = not st.session_state.add_symbol_form_visible
            st.rerun()
    
    # Show add symbol form
    if st.session_state.add_symbol_form_visible:
        show_add_symbol_form()
    
    # List all symbols section
    st.markdown("### 📋 All Stock Symbols")
    st.markdown("View and manage all stock symbols available in the system")
    
    # Fetch all symbols
    symbols_data = get_all_stock_symbols()
    
    if symbols_data:
        # Show success message with count
        st.success(f"✅ Found {len(symbols_data)} stock symbols in the system")
        
        # Search and filter
        col_search, col_filter = st.columns([2, 1])
        
        with col_search:
            search_term = st.text_input("🔍 Search symbols", placeholder="Search by symbol or company name...")
        
        with col_filter:
            filter_status = st.selectbox("📊 Status", ["All", "Active", "Inactive"], index=0)
        
        # Filter symbols
        filtered_symbols = filter_symbols(symbols_data, search_term, filter_status)
        
        if filtered_symbols:
            # Display symbols in a nice table
            display_symbols_table(filtered_symbols)
        else:
            st.info("🔍 No symbols found matching your criteria")
    else:
        st.warning("⚠️ No stock symbols found in the system")
        st.info("💡 Add your first stock symbol using the form above")

def show_add_symbol_form():
    """Show form to add a new stock symbol"""
    with st.expander("📝 Add New Stock Symbol", expanded=True):
        st.markdown("**🚀 Auto-populated from Yahoo Finance** - Enter symbol and optionally company details")
        
        with st.form("add_symbol_form"):
            symbol = st.text_input(
                "📈 Stock Symbol *", 
                placeholder="e.g., AAPL, GOOGL, MSFT",
                help="Enter the stock ticker symbol (e.g., AAPL, GOOGL, MSFT)"
            ).upper()
            
            st.markdown("---")
            st.markdown("**📝 Optional Company Information**")
            st.caption("Yahoo Finance API may be rate-limited. You can manually enter company details below.")
            
            col1, col2 = st.columns(2)
            
            with col1:
                company_name = st.text_input(
                    "🏢 Company Name", 
                    placeholder="e.g., Apple Inc.",
                    help="Company name (optional - will be fetched from Yahoo Finance if not provided)"
                )
                
                sector = st.text_input(
                    "🏭 Sector", 
                    placeholder="e.g., Technology",
                    help="Industry sector (optional)"
                )
            
            with col2:
                industry = st.text_input(
                    "⚙️ Industry", 
                    placeholder="e.g., Consumer Electronics",
                    help="Industry (optional)"
                )
                
                country = st.text_input(
                    "🌍 Country", 
                    placeholder="e.g., United States",
                    help="Country (optional)"
                )
            
            description = st.text_area(
                "📝 Description", 
                placeholder="Brief company description...",
                help="Enter a brief description of the company (optional)",
                height=80
            )
            
            st.info("💡 **Tip**: If Yahoo Finance API is rate-limited, you can manually enter company details above")
            
            # Submit buttons
            col_submit, col_cancel = st.columns([1, 1])
            
            with col_submit:
                submitted = st.form_submit_button("➕ Add Symbol", type="primary", use_container_width=True)
            
            with col_cancel:
                if st.form_submit_button("❌ Cancel", use_container_width=True):
                    st.session_state.add_symbol_form_visible = False
                    st.rerun()
            
            if submitted:
                if symbol:
                    success = add_stock_symbol(
                        symbol=symbol,
                        company_name=company_name,
                        sector=sector,
                        industry=industry,
                        description=description
                    )
                    
                    if success:
                        st.session_state.add_symbol_form_visible = False
                        st.rerun()
                else:
                    st.error("❌ Stock Symbol is required")

def get_all_stock_symbols():
    """Fetch all stock symbols from the database"""
    try:
        response = python_client.get("api/v1/stocks/available")
        
        if response and isinstance(response, list):
            return response
        else:
            st.error("❌ Failed to fetch stock symbols")
            return []
            
    except Exception as e:
        st.error(f"❌ Error fetching stock symbols: {str(e)}")
        return []

def filter_symbols(symbols_data, search_term, filter_status):
    """Filter symbols based on search term and status"""
    filtered = symbols_data.copy()
    
    # Filter by search term
    if search_term:
        search_term = search_term.lower()
        filtered = [
            symbol for symbol in filtered 
            if search_term in symbol.get('symbol', '').lower() 
            or (symbol.get('company_name') and search_term in symbol.get('company_name').lower())
        ]
    
    # Filter by status
    if filter_status != "All":
        is_active = filter_status == "Active"
        filtered = [
            symbol for symbol in filtered 
            if symbol.get('is_active', True) == is_active
        ]
    
    return filtered

def display_symbols_table(symbols_data):
    """Display symbols in a formatted table"""
    # Create display data
    display_data = []
    for symbol in symbols_data:
        display_data.append({
            'Symbol': symbol.get('symbol', 'N/A'),
            'Company Name': symbol.get('company_name') or 'N/A',
            'Sector': symbol.get('sector') or 'N/A',
            'Industry': symbol.get('industry') or 'N/A',
            'Country': symbol.get('country') or 'N/A',
            'Exchange': symbol.get('exchange') or 'N/A',
            'Status': '🟢 Active' if symbol.get('is_active', True) else '🔴 Inactive'
        })
    
    # Convert to DataFrame for better display
    if display_data:
        import pandas as pd
        df = pd.DataFrame(display_data)
        
        # Display with formatting
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Symbol": st.column_config.TextColumn("📈 Symbol", width="small"),
                "Company Name": st.column_config.TextColumn("🏢 Company Name", width="large"),
                "Sector": st.column_config.TextColumn("🏭 Sector", width="medium"),
                "Industry": st.column_config.TextColumn("⚙️ Industry", width="medium"),
                "Country": st.column_config.TextColumn("🌍 Country", width="small"),
                "Exchange": st.column_config.TextColumn("📊 Exchange", width="small"),
                "Status": st.column_config.TextColumn("📊 Status", width="small")
            }
        )
        
        # Show summary stats
        st.markdown("### 📊 Summary Statistics")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            total_symbols = len(symbols_data)
            st.metric("📈 Total Symbols", total_symbols)
        
        with col2:
            active_symbols = len([s for s in symbols_data if s.get('is_active', True)])
            st.metric("🟢 Active Symbols", active_symbols)
        
        with col3:
            inactive_symbols = len([s for s in symbols_data if not s.get('is_active', True)])
            st.metric("🔴 Inactive Symbols", inactive_symbols)

def add_stock_symbol(symbol, company_name=None, sector=None, industry=None, description=None, is_active=True):
    """Add a new stock symbol to the database"""
    try:
        # Prepare payload with manual company information if provided
        payload = {
            "symbol": symbol.upper()
        }
        
        # Add optional fields if provided
        if company_name:
            payload["company_name"] = company_name
        if sector:
            payload["sector"] = sector
        if industry:
            payload["industry"] = industry
        if description:
            payload["description"] = description
        
        response = python_client.post("api/v1/stocks/add", json_data=payload)
        
        if response and isinstance(response, dict):
            st.success(f"✅ Successfully added {symbol} to the system!")
            
            # Show what information was used
            if company_name or sector or industry:
                st.info(f"📝 Used manual company information")
                if response.get('company_name'):
                    st.info(f"🏢 Company: {response.get('company_name')}")
                if response.get('sector'):
                    st.info(f"🏭 Sector: {response.get('sector')}")
                if response.get('industry'):
                    st.info(f"⚙️ Industry: {response.get('industry')}")
            else:
                # Show the auto-populated company info
                if response.get('company_name'):
                    st.info(f"📝 Company info auto-populated: {response.get('company_name')}")
            
            return True
        else:
            error_msg = "Unknown error"
            if isinstance(response, dict) and response.get('detail'):
                error_msg = response.get('detail')
            st.error(f"❌ Failed to add symbol: {error_msg}")
            return False
            
    except Exception as e:
        st.error(f"❌ Error adding symbol: {str(e)}")
        return False

if __name__ == "__main__":
    main()
