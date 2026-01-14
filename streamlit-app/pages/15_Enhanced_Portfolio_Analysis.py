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

# Import shared analysis display component
from components.analysis_display import display_signal_analysis, display_no_data_message

# Initialize API client
python_api_url = os.getenv("PYTHON_API_URL", "http://python-worker:8001")
python_client = APIClient(python_api_url, timeout=30)
portfolio_api_url = os.getenv("PORTFOLIO_API_URL", "http://python-worker:8001/api/v2/portfolio")

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
        response = requests.post(f"{portfolio_api_url}/portfolios/{portfolio_id}/holdings",
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
                <p style="margin: 0.5rem 0 0 0; font-size: 1.1rem; opacity: 0.9;">
                    Welcome back, {user['full_name'] or user['username']} | 
                    <span style="background: rgba(255,255,255,0.2); padding: 0.25rem 0.75rem; border-radius: 20px; font-size: 0.875rem;">
                        {user['role'].title()}
                    </span>
                </p>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 0.875rem; opacity: 0.8;">Last Updated</div>
                <div style="font-size: 1.1rem; font-weight: 600;">{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Get user portfolios
    portfolios = get_user_portfolios()
    
    if not portfolios:
        # Institutional empty state
        st.markdown("""
        <div style="background: #f8fafc; padding: 3rem; border-radius: 15px; text-align: center; border: 2px dashed #cbd5e1;">
            <div style="font-size: 4rem; margin-bottom: 1rem;">📋</div>
            <h2 style="color: #475569; margin-bottom: 1rem;">No Portfolios Yet</h2>
            <p style="color: #64748b; margin-bottom: 2rem;">Create your first portfolio to start institutional-grade analysis</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Show create portfolio form
        with st.expander("➕ Create Your First Portfolio", expanded=True):
            show_create_portfolio_form()
    else:
        # Portfolio selector with enhanced styling
        portfolio_options = {f"{p['name']} ({p['portfolio_type'].title()})": p for p in portfolios}
        
        if 'selected_portfolio' not in st.session_state:
            st.session_state.selected_portfolio = portfolios[0]['id']
        
        # Enhanced portfolio selector
        st.markdown("### 📋 Portfolio Selection")
        selected_name = st.selectbox(
            "Select Portfolio",
            options=list(portfolio_options.keys()),
            index=list(portfolio_options.keys()).index(
                next(k for k, v in portfolio_options.items() if v['id'] == st.session_state.selected_portfolio)
            ) if st.session_state.selected_portfolio in [v['id'] for v in portfolio_options.values()] else 0,
            help="Choose a portfolio to analyze and manage"
        )
        
        selected_portfolio = portfolio_options[selected_name]
        st.session_state.selected_portfolio = selected_portfolio['id']
        
        # Institutional action buttons
        st.markdown("### 🎯 Portfolio Actions")
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
        
        with col1:
            if st.button("📊 Institutional Analysis", type="primary", use_container_width=True):
                with st.spinner("Running institutional-grade analysis..."):
                    result = analyze_portfolio(selected_portfolio['id'])
                    if result and result.get('success'):
                        st.success(f"✅ Analysis complete! Generated {result['signals_generated']} institutional signals")
                        st.session_state.last_analysis_result = result
                    else:
                        st.error("❌ Analysis failed")
        
        with col2:
            if st.button("🔄 Refresh Data", use_container_width=True):
                load_portfolio_data(selected_portfolio['id'])
        
        with col3:
            if st.button("📈 Risk Metrics", use_container_width=True):
                st.session_state.show_risk_metrics = True
        
        with col4:
            if st.button("➕ Add Symbol", use_container_width=True):
                st.session_state.show_add_symbol = True
        
        with col5:
            if st.button("🔄 Load All Data", use_container_width=True):
                load_all_portfolio_data(selected_portfolio['id'])
        
        # Show portfolio details with institutional formatting
        show_portfolio_details(selected_portfolio)
        
        # Show institutional risk metrics if requested
        if st.session_state.get('show_risk_metrics', False):
            show_institutional_risk_metrics(selected_portfolio)
        
        # Show last analysis results with institutional formatting
        if 'last_analysis_result' in st.session_state:
            show_institutional_analysis_results(st.session_state.last_analysis_result)

def show_create_portfolio_form():
    """Show create portfolio form"""
    with st.form("create_portfolio_form"):
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
            """.format(total_value), unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div style="background: #fef2f2; padding: 1rem; border-radius: 10px; text-align: center;">
                <div style="font-size: 0.875rem; color: #991b1b;">Total Cost</div>
                <div style="font-size: 1.25rem; font-weight: 700; color: #dc2626;">${:,.2f}</div>
            </div>
            """.format(total_cost), unsafe_allow_html=True)
        
        with col3:
            color = "#16a34a" if total_return >= 0 else "#dc2626"
            st.markdown(f"""
            <div style="background: {'#f0fdf4' if total_return >= 0 else '#fef2f2'}; padding: 1rem; border-radius: 10px; text-align: center;">
                <div style="font-size: 0.875rem; color: {color};">Total Return</div>
                <div style="font-size: 1.25rem; font-weight: 700; color: {color};">${total_return:,.2f}</div>
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
        holdings_data = []
        
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
                    'Shares': f"{shares_held:,.2f}",
                    'Avg Cost': f"${average_cost:.2f}",
                    'Current Price': f"${holding.get('current_price', 0):.2f}",
                    'Market Value': f"${market_value:,.2f}",
                    'Cost Basis': f"${cost_basis:,.2f}",
                    'P&L %': f"{unrealized_pct:+.2f}%",
                    'Weight': f"{(market_value/total_value*100):.2f}%" if total_value > 0 else "0.00%"
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
                    if st.button(f"📊 {symbol}", key=f"analysis_btn_{symbol}", 
                               help=f"View detailed analysis for {symbol}",
                               use_container_width=True):
                        st.session_state.selected_symbol_for_analysis = symbol
                        st.session_state.show_symbol_analysis = True
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
                    if st.button(f"📊 {holding_data['Symbol']}", key=f"analyze_{holding_data['Symbol']}", help=f"View detailed analysis for {holding_data['Symbol']}"):
                        st.session_state.selected_symbol_for_analysis = holding_data['Symbol']
                        st.session_state.show_symbol_analysis = True
                        st.rerun()
            
            st.markdown("---")
            
            # Portfolio summary
            total_pnl = total_value - total_cost
            total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
            
            st.markdown("#### 💰 Portfolio Summary")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Value", f"${total_value:,.2f}")
            
            with col2:
                st.metric("Total Cost", f"${total_cost:,.2f}")
            
            with col3:
                st.metric("Total P&L", f"${total_pnl:,.2f}")
            
            with col4:
                st.metric("Return %", f"{total_pnl_pct:.2f}%")
        
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
            response = python_client.post("refresh", json_data={
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
            response = python_client.post("refresh", json_data={
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
                response = python_client.post("refresh", json_data={
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
    
    # Check if we have cached analysis
    cache_key = f"analysis_{symbol}"
    if cache_key in st.session_state:
        analysis_data = st.session_state[cache_key]
    else:
        # Get fresh analysis
        asset_type = "stock"  # Default, could be enhanced to get from holdings
        analysis_data = get_symbol_analysis(symbol, asset_type)
        
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
                response = requests.get(f"http://python-worker:8001/api/v1/growth-quality/growth-health/{symbol}")
                
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
        response = requests.get(f"http://python-worker:8001/api/v1/growth-quality/early-warning/{symbol}")
        
        if response.status_code == 200:
            analysis_data = response.json()
            _render_fundamentals_risk_overview(analysis_data, symbol)
            _render_fundamentals_detailed_flags(analysis_data)
            _render_fundamentals_metrics_dashboard(analysis_data)
        else:
            st.error(f"❌ Failed to load comprehensive analysis for {symbol}")
            
    except Exception as e:
        st.error(f"❌ Error loading comprehensive analysis: {e}")

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
    """Render institutional-grade fundamentals analysis"""
    symbol = data.get('symbol', 'Unknown')
    
    # Structural Risk Assessment
    structural_risk = data.get('structural_risk', 'LOW')
    structural_icons = {
        'LOW': '🟢',
        'MEDIUM': '🟡',
        'HIGH': '🔴'
    }
    
    # Growth Phase Assessment
    growth_phase = data.get('growth_phase', 'MATURE_COMPOUNDER')
    growth_display = {
        'HEALTHY_COMPOUNDER': '🟢 Healthy Compounder',
        'MATURE_COMPOUNDER': '🟡 Mature Compounder',
        'GROWTH_DEGRADATION': '🟠 Growth Degradation',
        'GROWTH_BREAKDOWN': '🔴 Growth Breakdown'
    }
    
    # Investment Posture
    investment_posture = data.get('investment_posture', 'HOLD_SELECTIVE_ADD')
    posture_display = {
        'BUY': '🟢 BUY',
        'HOLD_SELECTIVE_ADD': '🟡 HOLD / SELECTIVE ADD',
        'TRIM_REDUCE': '🟠 TRIM / REDUCE',
        'EXIT_AVOID': '🔴 EXIT / AVOID'
    }
    
    # Main Assessment Card using Streamlit native components
    st.markdown("---")
    st.markdown(f"### 📊 {symbol} Fundamentals Assessment")
    
    # Structural Risk and Growth Phase
    col1, col2 = st.columns(2)
    
    with col1:
        risk_color = {
            'LOW': '🟢',
            'MEDIUM': '🟡', 
            'HIGH': '🔴'
        }
        st.markdown(f"#### Structural Risk: {risk_color.get(structural_risk, '')} {structural_risk}")
        st.caption("Balance sheet health assessment")
    
    with col2:
        st.markdown(f"#### Growth Phase: {growth_display.get(growth_phase, growth_phase)}")
        st.caption("Business lifecycle stage")
    
    # Investment Posture
    st.markdown("---")
    
    # Use metric for investment posture
    posture_emoji = {
        'BUY': '🟢',
        'HOLD_SELECTIVE_ADD': '🟡',
        'TRIM_REDUCE': '🟠',
        'EXIT_AVOID': '🔴'
    }
    
    posture_text = posture_display.get(investment_posture, investment_posture)
    st.metric(
        label="Investment Posture",
        value=f"{posture_emoji.get(investment_posture, '')} {posture_text}",
        delta=None
    )
    st.caption("Clear investment guidance")
    
    # Detailed Analysis
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 🎯 Investment Reasoning")
        for reason in data.get('reasoning', []):
            st.markdown(f"• {reason}")
        
        st.markdown("#### 💰 Forward Returns")
        st.info(data.get('forward_return_expectation', 'Not available'))
    
    with col2:
        st.markdown("#### ⚠️ Risk Factors")
        for risk in data.get('risk_factors', []):
            st.markdown(f"• {risk}")
        
        st.markdown("#### 🚀 Opportunities")
        for opportunity in data.get('opportunities', []):
            st.markdown(f"• {opportunity}")
    
    # Investment Guidance
    confidence = data.get('confidence', 0) * 100
    
    # Show confidence as a metric
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Analysis Confidence", f"{confidence:.0f}%")
    
    with col2:
        if investment_posture == 'BUY':
            st.success("**🟢 Action: BUY**")
            st.caption("Aggressive accumulation recommended")
        elif investment_posture == 'HOLD_SELECTIVE_ADD':
            st.warning("**🟡 Action: HOLD**")
            st.caption("Add only on meaningful corrections")
        elif investment_posture == 'TRIM_REDUCE':
            st.error("**🟠 Action: TRIM**")
            st.caption("Reduce position size")
        else:
            st.error("**🔴 Action: EXIT**")
            st.caption("Avoid or sell position")


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
        # Sidebar with user info and actions
        with st.sidebar:
            user = st.session_state.current_user
            
            st.markdown(f"### 👤 {user['full_name'] or user['username']}")
            st.caption(f"Role: {user['role'].title()}")
            
            st.divider()
            
            # Quick actions
            if st.button("➕ New Portfolio", use_container_width=True):
                st.session_state.show_create_portfolio = True
            
            if st.button("🔄 Refresh Data", use_container_width=True):
                if 'selected_portfolio' in st.session_state:
                    load_portfolio_data(st.session_state.selected_portfolio)
            
            if st.button("🚪 Logout", use_container_width=True):
                logout_user()
            
            st.divider()
            
            # Show create portfolio form if requested
            if st.session_state.get('show_create_portfolio', False):
                st.markdown("#### ➕ Create New Portfolio")
                show_create_portfolio_form()
        
        # Main content
        if st.session_state.get('show_create_portfolio', False):
            st.markdown("### ➕ Create New Portfolio")
            show_create_portfolio_form()
        elif st.session_state.get('show_symbol_analysis', False):
            # Show individual symbol analysis
            symbol = st.session_state.get('selected_symbol_for_analysis')
            if symbol:
                show_symbol_analysis(symbol)
            else:
                st.error("No symbol selected for analysis")
                st.session_state.show_symbol_analysis = False
                st.rerun()
        else:
            show_portfolio_overview()
            
            # Show scheduling section for selected portfolio
            if 'selected_portfolio' in st.session_state:
                st.divider()
                show_scheduling_section(st.session_state.selected_portfolio)

if __name__ == "__main__":
    main()
