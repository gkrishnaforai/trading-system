import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import os
from utils import setup_page_config, render_sidebar
from api_client import APIClient, APIError

# Initialize API client
python_api_url = os.getenv("PYTHON_API_URL", "http://python-worker:8001")
python_client = APIClient(python_api_url, timeout=30)

# Function definitions (moved to top to fix NameError)
def get_symbol_signal(symbol, asset_type):
    """Get signal for a specific symbol"""
    from utils.portfolio_utils import PortfolioAnalyzer
    
    analyzer = PortfolioAnalyzer()
    return analyzer.analyze_symbol(symbol, asset_type)

def show_detailed_analysis(symbol: str):
    """Show detailed analysis for a specific symbol using shared component"""
    
    # Import the shared analysis display component
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from components.analysis_display import display_signal_analysis, display_no_data_message
    
    # Get the analysis data
    analysis_data = st.session_state.portfolio_analysis.get(symbol, {}).get('full_data', {})
    
    # Use the shared component to display analysis
    if analysis_data:
        display_signal_analysis(symbol, analysis_data, show_header=True, show_debug=False)
    else:
        display_no_data_message(symbol)

def analyze_portfolio():
    """Analyze all symbols in portfolio"""
    from utils.portfolio_utils import PortfolioAnalyzer
    
    st.session_state.portfolio_analysis = {}
    
    # Create analyzer instance
    analyzer = PortfolioAnalyzer()
    
    for symbol_info in st.session_state.portfolio_symbols:
        symbol = symbol_info['symbol']
        asset_type = symbol_info['asset_type']
        
        try:
            # Get signal for this symbol
            signal_data = analyzer.analyze_symbol(symbol, asset_type)
            if signal_data and not signal_data.get('error'):
                st.session_state.portfolio_analysis[symbol] = {
                    'signal': signal_data.get('signal', {}).get('signal', 'HOLD'),
                    'confidence': signal_data.get('signal', {}).get('confidence', 0),
                    'price': signal_data.get('market_data', {}).get('price', 0),
                    'recent_change': signal_data.get('analysis', {}).get('recent_change', 0),
                    'rsi': signal_data.get('market_data', {}).get('rsi', 0),
                    'volume': signal_data.get('market_data', {}).get('volume', 0),
                    'full_data': signal_data
                }
        except Exception as e:
            st.error(f"❌ Error analyzing {symbol}: {str(e)}")
    
    st.success(f"✅ Analysis complete for {len(st.session_state.portfolio_symbols)} symbols!")
    st.rerun()

# Page setup
setup_page_config("Portfolio Analysis Dashboard", "📊")

# Custom CSS for modern portfolio interface
st.markdown("""
<style>
.portfolio-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 2rem;
    border-radius: 15px;
    color: white;
    margin-bottom: 2rem;
    text-align: center;
}

.portfolio-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
}

.stat-card {
    background: white;
    padding: 1.5rem;
    border-radius: 10px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    border-left: 4px solid #667eea;
}

.portfolio-table {
    background: white;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.signal-badge {
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    font-size: 0.875rem;
    font-weight: 600;
    text-align: center;
}

.buy-signal { background: #E8F5E8; color: #00C851; }
.sell-signal { background: #FFEBEE; color: #FF4444; }
.hold-signal { background: #FFF3E0; color: #FF8800; }

.confidence-bar {
    height: 8px;
    border-radius: 4px;
    background: #e0e0e0;
    overflow: hidden;
    margin-top: 0.5rem;
}

.confidence-fill {
    height: 100%;
    transition: width 0.3s ease;
}

.high-confidence { background: #00C851; }
.medium-confidence { background: #FF8800; }
.low-confidence { background: #FF4444; }

.action-button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 8px;
    cursor: pointer;
    font-weight: 600;
    transition: all 0.3s ease;
}

.action-button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.symbol-row {
    cursor: pointer;
    transition: background-color 0.2s ease;
}

.symbol-row:hover {
    background-color: #f8f9fa;
}

.add-symbol-form {
    background: #f8f9fa;
    padding: 1.5rem;
    border-radius: 10px;
    margin-bottom: 2rem;
}
</style>
""", unsafe_allow_html=True)

# Initialize session state for portfolio
if 'portfolio_symbols' not in st.session_state:
    st.session_state.portfolio_symbols = []
if 'portfolio_analysis' not in st.session_state:
    st.session_state.portfolio_analysis = {}
if 'selected_symbol' not in st.session_state:
    st.session_state.selected_symbol = None

# Header
st.markdown("""
<div class="portfolio-header">
    <h1>📊 Portfolio Analysis Dashboard</h1>
    <p>Comprehensive multi-symbol analysis with detailed drill-down</p>
</div>
""", unsafe_allow_html=True)

# Sidebar for portfolio management
with st.sidebar:
    st.markdown("### 📋 Portfolio Management")
    
    # Add new symbol form
    st.markdown('<div class="add-symbol-form">', unsafe_allow_html=True)
    st.markdown("**Add New Symbol**")
    
    col1, col2 = st.columns(2)
    with col1:
        new_symbol = st.text_input("Symbol", placeholder="e.g., AAPL", key="new_symbol_input").upper()
    with col2:
        asset_type = st.selectbox("Type", ["stock", "regular_etf", "3x_etf"], key="asset_type_select")
    
    if st.button("➕ Add to Portfolio", key="add_symbol_btn", type="primary"):
        if new_symbol and new_symbol not in [s['symbol'] for s in st.session_state.portfolio_symbols]:
            st.session_state.portfolio_symbols.append({
                'symbol': new_symbol,
                'asset_type': asset_type,
                'added_date': datetime.now().strftime("%Y-%m-%d")
            })
            st.success(f"✅ {new_symbol} added to portfolio!")
            st.rerun()
        elif new_symbol in [s['symbol'] for s in st.session_state.portfolio_symbols]:
            st.warning(f"⚠️ {new_symbol} already in portfolio!")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Portfolio summary
    if st.session_state.portfolio_symbols:
        st.markdown("**Portfolio Summary**")
        st.write(f"📊 Total Symbols: {len(st.session_state.portfolio_symbols)}")
        
        asset_type_counts = {}
        for symbol_info in st.session_state.portfolio_symbols:
            atype = symbol_info['asset_type']
            asset_type_counts[atype] = asset_type_counts.get(atype, 0) + 1
        
        for atype, count in asset_type_counts.items():
            icon = {"stock": "📈", "regular_etf": "📊", "3x_etf": "🚀"}.get(atype, "📋")
            st.write(f"{icon} {atype.replace('_', ' ').title()}: {count}")
    
    # Bulk actions
    st.markdown("**Bulk Actions**")
    
    if st.button("🔄 Load Data for All", key="load_all_data_btn", type="primary"):
        if st.session_state.portfolio_symbols:
            with st.spinner("Loading data for all portfolio symbols..."):
                symbols_to_load = [s['symbol'] for s in st.session_state.portfolio_symbols]
                try:
                    response = python_client.post("refresh", json_data={
                        "symbols": symbols_to_load,
                        "data_types": ["price_historical", "indicators"],
                        "force": True
                    })
                    if response.get("success"):
                        st.success("✅ Data loaded successfully for all symbols!")
                    else:
                        st.error(f"❌ Error: {response.get('error', 'Unknown error')}")
                except Exception as e:
                    st.error(f"❌ Failed to load data: {str(e)}")
        else:
            st.warning("⚠️ No symbols in portfolio!")
    
    if st.button("📊 Analyze All", key="analyze_all_btn", type="primary"):
        if st.session_state.portfolio_symbols:
            analyze_portfolio()
        else:
            st.warning("⚠️ No symbols in portfolio!")
    
    if st.button("🗑️ Clear Portfolio", key="clear_portfolio_btn"):
        st.session_state.portfolio_symbols = []
        st.session_state.portfolio_analysis = {}
        st.success("✅ Portfolio cleared!")
        st.rerun()

# Main content area
if not st.session_state.portfolio_symbols:
    # Empty state with prominent add functionality
    st.markdown("""
    <div style="text-align: center; padding: 4rem; color: #666;">
        <h2>📋 Your Portfolio is Empty</h2>
        <p>Start building your portfolio by adding symbols below.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Prominent add symbol section in main area
    st.markdown("### 🚀 Add Your First Symbols")
    
    # Add symbols form in main content
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        new_symbol = st.text_input("📈 Enter Symbol", placeholder="e.g., AAPL, TSLA, QQQ", key="main_symbol_input").upper()
    
    with col2:
        asset_type = st.selectbox("📊 Asset Type", ["stock", "regular_etf", "3x_etf"], key="main_asset_type_select")
    
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)  # Spacer for alignment
        if st.button("➕ Add Symbol", key="main_add_symbol_btn", type="primary", use_container_width=True):
            if new_symbol and len(new_symbol.strip()) >= 1:
                if new_symbol not in [s['symbol'] for s in st.session_state.portfolio_symbols]:
                    st.session_state.portfolio_symbols.append({
                        'symbol': new_symbol.strip(),
                        'asset_type': asset_type,
                        'added_date': datetime.now().strftime("%Y-%m-%d")
                    })
                    st.success(f"✅ {new_symbol.strip()} added to portfolio!")
                    st.rerun()
                else:
                    st.warning(f"⚠️ {new_symbol.strip()} already in portfolio!")
            else:
                st.error("❌ Please enter a valid symbol")
    
    # Quick add popular symbols
    st.markdown("#### 🌟 Quick Add Popular Symbols")
    
    popular_symbols = [
        {"symbol": "AAPL", "type": "stock", "name": "Apple"},
        {"symbol": "MSFT", "type": "stock", "name": "Microsoft"},
        {"symbol": "GOOGL", "type": "stock", "name": "Google"},
        {"symbol": "TSLA", "type": "stock", "name": "Tesla"},
        {"symbol": "QQQ", "type": "regular_etf", "name": "Invesco QQQ"},
        {"symbol": "SPY", "type": "regular_etf", "name": "SPDR S&P 500"},
        {"symbol": "TQQQ", "type": "3x_etf", "name": "ProShares UltraPro QQQ"},
        {"symbol": "SOXL", "type": "3x_etf", "name": "ProShares UltraPro Semiconductor"}
    ]
    
    # Create columns for quick add buttons
    cols = st.columns(4)
    for i, symbol_info in enumerate(popular_symbols):
        with cols[i % 4]:
            if st.button(
                f"{symbol_info['symbol']}\n{symbol_info['name']}", 
                key=f"quick_add_{symbol_info['symbol']}",
                help=f"Add {symbol_info['name']} ({symbol_info['type'].replace('_', ' ').title()})",
                use_container_width=True
            ):
                if symbol_info['symbol'] not in [s['symbol'] for s in st.session_state.portfolio_symbols]:
                    st.session_state.portfolio_symbols.append({
                        'symbol': symbol_info['symbol'],
                        'asset_type': symbol_info['type'],
                        'added_date': datetime.now().strftime("%Y-%m-%d")
                    })
                    st.success(f"✅ {symbol_info['symbol']} added to portfolio!")
                    st.rerun()
                else:
                    st.warning(f"⚠️ {symbol_info['symbol']} already in portfolio!")

else:
    # Portfolio exists - show management and analysis
    
    # Portfolio Management Section
    st.markdown("### 📋 Portfolio Management")
    
    # Add new symbol section
    with st.expander("➕ Add New Symbols", expanded=False):
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            new_symbol = st.text_input("📈 Enter Symbol", placeholder="e.g., NVDA, AMD, IWM", key="portfolio_add_input").upper()
        
        with col2:
            asset_type = st.selectbox("📊 Asset Type", ["stock", "regular_etf", "3x_etf"], key="portfolio_add_type")
        
        with col3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ Add to Portfolio", key="portfolio_add_btn", type="primary", use_container_width=True):
                if new_symbol and len(new_symbol.strip()) >= 1:
                    if new_symbol not in [s['symbol'] for s in st.session_state.portfolio_symbols]:
                        st.session_state.portfolio_symbols.append({
                            'symbol': new_symbol.strip(),
                            'asset_type': asset_type,
                            'added_date': datetime.now().strftime("%Y-%m-%d")
                        })
                        st.success(f"✅ {new_symbol.strip()} added to portfolio!")
                        st.rerun()
                    else:
                        st.warning(f"⚠️ {new_symbol.strip()} already in portfolio!")
                else:
                    st.error("❌ Please enter a valid symbol")
    
    # Portfolio summary cards
    st.markdown("#### 📊 Portfolio Overview")
    
    # Calculate portfolio statistics
    total_symbols = len(st.session_state.portfolio_symbols)
    analyzed_symbols = len([s for s in st.session_state.portfolio_analysis.keys() if s in [sym['symbol'] for sym in st.session_state.portfolio_symbols]])
    buy_signals = sum(1 for analysis in st.session_state.portfolio_analysis.values() if analysis.get('signal') == 'BUY')
    sell_signals = sum(1 for analysis in st.session_state.portfolio_analysis.values() if analysis.get('signal') == 'SELL')
    
    # Asset type distribution
    asset_type_counts = {}
    for symbol_info in st.session_state.portfolio_symbols:
        atype = symbol_info['asset_type']
        asset_type_counts[atype] = asset_type_counts.get(atype, 0) + 1
    
    # Display stats in columns
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("📈 Total Symbols", total_symbols)
    
    with col2:
        st.metric("📊 Analyzed", f"{analyzed_symbols}/{total_symbols}")
    
    with col3:
        st.metric("🟢 BUY Signals", buy_signals)
    
    with col4:
        st.metric("🔴 SELL Signals", sell_signals)
    
    with col5:
        hold_signals = total_symbols - buy_signals - sell_signals
        st.metric("🟡 HOLD Signals", hold_signals)
    
    # Asset type breakdown
    if asset_type_counts:
        st.markdown("#### 📋 Asset Type Distribution")
        cols = st.columns(len(asset_type_counts))
        for i, (atype, count) in enumerate(asset_type_counts.items()):
            with cols[i]:
                icon = {"stock": "📈", "regular_etf": "📊", "3x_etf": "🚀"}.get(atype, "📋")
                st.markdown(f"""
                <div style="text-align: center; padding: 1rem; background: #f8f9fa; border-radius: 10px;">
                    <div style="font-size: 2rem;">{icon}</div>
                    <div style="font-weight: bold;">{atype.replace('_', ' ').title()}</div>
                    <div style="font-size: 1.5rem; font-weight: bold; color: #667eea;">{count}</div>
                </div>
                """, unsafe_allow_html=True)
    
    # Bulk actions
    st.markdown("#### 🔄 Bulk Operations")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🔄 Load Data for All", key="load_all_data_main", type="primary", use_container_width=True):
            if st.session_state.portfolio_symbols:
                with st.spinner("Loading data for all portfolio symbols..."):
                    symbols_to_load = [s['symbol'] for s in st.session_state.portfolio_symbols]
                    try:
                        response = python_client.post("refresh", json_data={
                            "symbols": symbols_to_load,
                            "data_types": ["price_historical", "indicators"],
                            "force": True
                        })
                        if response.get("success"):
                            st.success("✅ Data loaded successfully for all symbols!")
                        else:
                            st.error(f"❌ Error: {response.get('error', 'Unknown error')}")
                    except Exception as e:
                        st.error(f"❌ Failed to load data: {str(e)}")
            else:
                st.warning("⚠️ No symbols in portfolio!")
    
    with col2:
        if st.button("📊 Analyze All", key="analyze_all_main", type="primary", use_container_width=True):
            if st.session_state.portfolio_symbols:
                analyze_portfolio()
            else:
                st.warning("⚠️ No symbols in portfolio!")
    
    with col3:
        if st.button("📥 Export Portfolio", key="export_portfolio", use_container_width=True):
            portfolio_data = {
                'symbols': st.session_state.portfolio_symbols,
                'analysis': st.session_state.portfolio_analysis,
                'export_date': datetime.now().isoformat()
            }
            st.download_button(
                "📄 Download JSON",
                data=json.dumps(portfolio_data, indent=2),
                file_name=f"portfolio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
    
    with col4:
        if st.button("🗑️ Clear Portfolio", key="clear_portfolio_main", use_container_width=True):
            if st.session_state.portfolio_symbols:
                st.warning("⚠️ This will remove all symbols from your portfolio!")
                if st.button("Confirm Clear All", key="confirm_clear", type="primary"):
                    st.session_state.portfolio_symbols = []
                    st.session_state.portfolio_analysis = {}
                    st.success("✅ Portfolio cleared!")
                    st.rerun()
            else:
                st.warning("⚠️ Portfolio is already empty!")
    
    # Portfolio table
    st.markdown("### 📋 Portfolio Holdings & Management")
    
    # Create portfolio dataframe
    portfolio_data = []
    for symbol_info in st.session_state.portfolio_symbols:
        symbol = symbol_info['symbol']
        asset_type = symbol_info['asset_type']
        analysis = st.session_state.portfolio_analysis.get(symbol, {})
        
        portfolio_data.append({
            'Symbol': symbol,
            'Type': asset_type.replace('_', ' ').title(),
            'Signal': analysis.get('signal', 'HOLD'),
            'Confidence': analysis.get('confidence', 0),
            'Price': analysis.get('price', 0),
            'Change': analysis.get('recent_change', 0),
            'RSI': analysis.get('rsi', 0),
            'Volume': analysis.get('volume', 0),
            'Status': '🟢 Analyzed' if analysis else '🟡 Pending',
            'Added Date': symbol_info.get('added_date', 'N/A')
        })
    
    if portfolio_data:
        df_portfolio = pd.DataFrame(portfolio_data)
        
        # Enhanced table with individual actions
        st.markdown('<div class="portfolio-table">', unsafe_allow_html=True)
        
        for i, row in df_portfolio.iterrows():
            symbol = df_portfolio.iloc[i]['Symbol']
            symbol_info = next((s for s in st.session_state.portfolio_symbols if s['symbol'] == symbol), None)
            
            # Format signal badge
            signal = row['Signal']
            signal_classes = {'BUY': 'buy-signal', 'SELL': 'sell-signal', 'HOLD': 'hold-signal'}
            signal_class = signal_classes.get(signal, 'hold-signal')
            signal_badge = f'<span class="signal-badge {signal_class}">{signal}</span>'
            
            # Format confidence bar
            confidence = float(row['Confidence']) if row['Confidence'] else 0
            if confidence >= 0.6:
                color_class = 'high-confidence'
            elif confidence >= 0.4:
                color_class = 'medium-confidence'
            else:
                color_class = 'low-confidence'
            
            confidence_bar = f'''
            <div>
                {confidence:.1%}
                <div class="confidence-bar">
                    <div class="confidence-fill {color_class}" style="width: {confidence * 100}%"></div>
                </div>
            </div>
            '''
            
            # Format other values
            try:
                price = f"${float(row['Price']):.2f}"
            except:
                price = str(row['Price'])
            
            try:
                change_val = float(row['Change'])
                change_color = '#00C851' if change_val >= 0 else '#FF4444'
                change = f'<span style="color: {change_color}">{change_val:+.2%}</span>'
            except:
                change = str(row['Change'])
            
            try:
                volume = f"{float(row['Volume']):,.0f}"
            except:
                volume = str(row['Volume'])
            
            # Create row with actions
            col1, col2, col3, col4, col5, col6, col7, col8, col9, col10, col11 = st.columns([1, 1, 1, 1.5, 1, 1, 1, 1.5, 1, 1, 1.5])
            
            with col1:
                st.markdown(f"**{symbol}**")
            
            with col2:
                st.markdown(row['Type'])
            
            with col3:
                st.markdown(signal_badge, unsafe_allow_html=True)
            
            with col4:
                st.markdown(confidence_bar, unsafe_allow_html=True)
            
            with col5:
                st.markdown(price)
            
            with col6:
                st.markdown(change, unsafe_allow_html=True)
            
            with col7:
                st.markdown(f"{row['RSI']:.1f}")
            
            with col8:
                st.markdown(volume)
            
            with col9:
                st.markdown(row['Status'])
            
            with col10:
                st.markdown(row['Added Date'])
            
            with col11:
                # Action buttons for each symbol
                col_btn1, col_btn2 = st.columns(2)
                
                with col_btn1:
                    if st.button("📊", key=f"details_{symbol}", help="View Details", use_container_width=True):
                        st.session_state.selected_symbol = symbol
                        st.rerun()
                
                with col_btn2:
                    if st.button("🗑️", key=f"delete_{symbol}", help="Remove from Portfolio", use_container_width=True):
                        # Remove symbol from portfolio
                        st.session_state.portfolio_symbols = [s for s in st.session_state.portfolio_symbols if s['symbol'] != symbol]
                        # Remove from analysis
                        if symbol in st.session_state.portfolio_analysis:
                            del st.session_state.portfolio_analysis[symbol]
                        st.success(f"✅ {symbol} removed from portfolio!")
                        st.rerun()
            
            st.markdown("---")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Check for symbol detail request
        query_params = st.query_params
        if 'symbol_detail' in query_params:
            selected_symbol = query_params['symbol_detail']
            if selected_symbol in [s['symbol'] for s in st.session_state.portfolio_symbols]:
                st.session_state.selected_symbol = selected_symbol
                # Clear the query param
                st.query_params.clear()
    
    # Detailed analysis section (shown when symbol is selected)
    if st.session_state.selected_symbol:
        symbol_detail = st.session_state.selected_symbol
        symbol_info = next((s for s in st.session_state.portfolio_symbols if s['symbol'] == symbol_detail), None)
        
        if symbol_info:
            st.markdown("---")
            st.markdown(f"### 📊 Detailed Analysis: {symbol_detail}")
            
            # Back button
            if st.button("← Back to Portfolio", key="back_to_portfolio"):
                st.session_state.selected_symbol = None
                st.rerun()
            
            # Load the detailed analysis page content
            show_detailed_analysis(symbol_info['symbol'], symbol_info['asset_type'])

# Sidebar - now simplified with just navigation and settings
with st.sidebar:
    st.markdown("### 🧭 Navigation")
    
    # Quick navigation
    if st.button("🏠 Portfolio Overview", key="nav_overview", use_container_width=True):
        st.session_state.selected_symbol = None
        st.rerun()
    
    st.divider()
    
    # Navigation to other analysis pages
    st.markdown("### 📊 Analysis Pages")
    
    if st.button("🔬 Universal Backtest Advanced", key="nav_universal_backtest", use_container_width=True, help="Go to detailed single-symbol analysis"):
        # Pass selected symbol if available
        if st.session_state.selected_symbol:
            # Set the symbol in session state for the backtest page
            st.session_state.transfer_symbol = st.session_state.selected_symbol
        st.switch_page("pages/13_Universal_Backtest_Advanced.py")
    
    if st.button("📈 Trading Dashboard", key="nav_trading_dashboard", use_container_width=True, help="Go to trading dashboard"):
        st.switch_page("pages/9_Trading_Dashboard.py")
    
    if st.button("🔄 Universal Backtest", key="nav_universal_basic", use_container_width=True, help="Go to basic universal backtest"):
        st.switch_page("pages/10_Universal_Backtest.py")
    
    st.divider()
    
    # Portfolio quick stats (compact)
    if st.session_state.portfolio_symbols:
        st.markdown("### 📊 Quick Stats")
        st.write(f"📈 Symbols: {len(st.session_state.portfolio_symbols)}")
        analyzed = len([s for s in st.session_state.portfolio_analysis.keys() if s in [sym['symbol'] for sym in st.session_state.portfolio_symbols]])
        st.write(f"📊 Analyzed: {analyzed}")
        
        buy_signals = sum(1 for analysis in st.session_state.portfolio_analysis.values() if analysis.get('signal') == 'BUY')
        sell_signals = sum(1 for analysis in st.session_state.portfolio_analysis.values() if analysis.get('signal') == 'SELL')
        st.write(f"🟢 BUY: {buy_signals}")
        st.write(f"🔴 SELL: {sell_signals}")
        
        st.divider()
        
        # Quick actions for selected symbol
        if st.session_state.selected_symbol:
            st.markdown("### 🎯 Quick Actions")
            selected_symbol = st.session_state.selected_symbol
            
            if st.button("🔄 Refresh Analysis", key="quick_refresh", use_container_width=True, help=f"Refresh analysis for {selected_symbol}"):
                with st.spinner(f"Refreshing analysis for {selected_symbol}..."):
                    # Get symbol info
                    symbol_info = next((s for s in st.session_state.portfolio_symbols if s['symbol'] == selected_symbol), None)
                    if symbol_info:
                        # Re-analyze this specific symbol
                        from utils.portfolio_utils import PortfolioAnalyzer
                        analyzer = PortfolioAnalyzer()
                        
                        try:
                            signal_data = analyzer.analyze_symbol(selected_symbol, symbol_info['asset_type'])
                            if signal_data and not signal_data.get('error'):
                                # Update analysis in session state
                                st.session_state.portfolio_analysis[selected_symbol] = {
                                    'signal': signal_data.get('signal', {}).get('signal', 'HOLD'),
                                    'confidence': signal_data.get('signal', {}).get('confidence', 0),
                                    'price': signal_data.get('market_data', {}).get('price', 0),
                                    'recent_change': signal_data.get('analysis', {}).get('recent_change', 0),
                                    'rsi': signal_data.get('market_data', {}).get('rsi', 0),
                                    'volume': signal_data.get('market_data', {}).get('volume', 0),
                                    'full_data': signal_data
                                }
                                st.success(f"✅ Analysis refreshed for {selected_symbol}!")
                                st.rerun()
                            else:
                                st.error(f"❌ Error refreshing {selected_symbol}: {signal_data.get('error', 'Unknown error')}")
                        except Exception as e:
                            st.error(f"❌ Failed to refresh {selected_symbol}: {str(e)}")
            
            if st.button("📊 Open in Backtest", key="open_in_backtest", use_container_width=True, help=f"Analyze {selected_symbol} in Universal Backtest"):
                # Set the symbol for transfer
                st.session_state.transfer_symbol = selected_symbol
                st.switch_page("pages/13_Universal_Backtest_Advanced.py")
    
    st.divider()
    
    # Settings
    st.markdown("### ⚙️ Settings")
    
    # Auto-refresh option
    auto_refresh = st.checkbox("🔄 Auto-refresh data", key="auto_refresh", help="Automatically refresh data every 5 minutes")
    
    if auto_refresh:
        st.info("📅 Data will refresh every 5 minutes")
    
    st.divider()
    
    # Help
    st.markdown("### 📚 Help")
    st.markdown("""
    **How to use:**
    1. Add symbols to portfolio
    2. Load data for all symbols
    3. Run analysis on all symbols
    4. Click 📊 for detailed view
    5. Click 🗑️ to remove symbols
    
    **Asset Types:**
    - 📈 Stock: Individual stocks
    - 📊 ETF: Regular ETFs
    - 🚀 3x ETF: Leveraged ETFs
    """)

# Render sidebar
render_sidebar()
