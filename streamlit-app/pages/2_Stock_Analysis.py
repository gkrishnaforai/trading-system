"""
Stock Analysis Page
Comprehensive stock analysis with indicators, signals, and advanced features
"""
import streamlit as st
import sys
import os
import pandas as pd
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar
from shared_functions import (
    get_stock_data, fetch_historical_data, refresh_data,
    plot_stock_chart, get_fundamentals, get_news, get_earnings, get_industry_peers,
    get_swing_signal
)
from api_client import APIError

setup_page_config("Stock Analysis", "📊")

st.title("📊 Stock Analysis")

# Sidebar
subscription_level = render_sidebar()

# Stock symbol input with data fetch button
col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

with col1:
    symbol = st.text_input("Enter Stock Symbol", value="AAPL", placeholder="e.g., AAPL, MSFT, GOOGL", key="stock_search_symbol")

with col2:
    st.write("")  # Spacing
    fetch_data_button = st.button("📥 Fetch Data", help="Fetch historical data and calculate indicators", use_container_width=True)

with col3:
    st.write("")  # Spacing
    period = st.selectbox("Period", ["1y", "6mo", "3mo", "1mo", "2y", "5y"], index=0, help="Historical data period")

with col4:
    st.write("")  # Spacing
    # Quick action buttons will be shown below after symbol is entered

# Fetch historical data if button clicked
if fetch_data_button and symbol:
    with st.spinner(f"📥 Fetching {period} of historical data for {symbol.upper()}... This may take 1-2 minutes."):
        try:
            fetch_result = fetch_historical_data(symbol.upper(), period=period, calculate_indicators=True)
            if fetch_result and fetch_result.get('success'):
                st.success(f"✅ Data fetched successfully!")
                # Display detailed results with validation
                display_fetch_results(fetch_result)
                st.balloons()
                st.rerun()
            elif fetch_result:
                st.warning(f"⚠️ {fetch_result.get('message', 'Data fetch may have failed.')}")
            else:
                st.error("❌ Failed to fetch data - no response from API")
        except APIError as e:
            st.error(f"❌ Failed to fetch data: {e}")
        except Exception as e:
            st.error(f"❌ Unexpected error: {e}")

# Quick Add to Watchlist/Portfolio (Industry Standard: Available immediately when symbol entered)
if symbol:
    # Show quick action buttons immediately (Industry Standard: Visible on search/results page)
    st.markdown("---")
    st.markdown("**💡 Quick Actions** (Available immediately - Industry Standard)")
    col1, col2 = st.columns(2)
    with col1:
        quick_add_watchlist = st.button("➕ Add to Watchlist", key="quick_watchlist_btn", use_container_width=True, help="Add this symbol to your watchlist")
    with col2:
        quick_add_portfolio = st.button("💼 Add to Portfolio", key="quick_portfolio_btn", use_container_width=True, help="Add this symbol to your portfolio")
else:
    quick_add_watchlist = False
    quick_add_portfolio = False
    
    # Handle quick actions
    if quick_add_watchlist:
        with st.expander("➕ Add to Watchlist", expanded=True):
            try:
                from api_client import get_go_api_client
                go_client = get_go_api_client()
                user_id = st.text_input("User ID", value="user1", key="quick_watchlist_user")
                
                # Get user's watchlists
                watchlists_response = go_client.get(f"api/v1/watchlists/user/{user_id}")
                watchlists = watchlists_response.get('watchlists', []) if watchlists_response else []
                
                if watchlists:
                    watchlist_options = {w.get('watchlist_name'): w.get('watchlist_id') for w in watchlists}
                    selected_watchlist_name = st.selectbox(
                        "Select Watchlist",
                        options=list(watchlist_options.keys()),
                        key="quick_select_watchlist"
                    )
                    selected_watchlist_id = watchlist_options.get(selected_watchlist_name)
                    
                    notes = st.text_area("Notes (optional)", key="quick_watchlist_notes")
                    
                    if st.button("✅ Add Symbol", key="quick_confirm_watchlist"):
                        try:
                            add_response = go_client.post(
                                f"api/v1/watchlists/{selected_watchlist_id}/items",
                                json_data={
                                    "stock_symbol": symbol.upper(),
                                    "notes": notes if notes else None,
                                    "priority": 0
                                }
                            )
                            st.success(f"✅ {symbol.upper()} added to {selected_watchlist_name}!")
                            st.json(add_response)
                        except APIError as e:
                            st.error(f"❌ Error: {e}")
                else:
                    st.info("💡 No watchlists found. Create a watchlist first in the Watchlist Management page.")
                    if st.button("📋 Go to Watchlist Management"):
                        st.switch_page("pages/4_Watchlist.py")
            except APIError as e:
                st.error(f"❌ Error loading watchlists: {e}")
    
    if quick_add_portfolio:
        with st.expander("💼 Add to Portfolio", expanded=True):
            try:
                from api_client import get_go_api_client
                go_client = get_go_api_client()
                user_id = st.text_input("User ID", value="user1", key="quick_portfolio_user")
                portfolio_id = st.text_input("Portfolio ID", key="quick_portfolio_id", placeholder="e.g., portfolio1")
                
                col1, col2 = st.columns(2)
                with col1:
                    quantity = st.number_input("Quantity", min_value=0.01, value=1.0, step=0.01, key="quick_quantity")
                    avg_entry_price = st.number_input("Avg Entry Price ($)", min_value=0.01, value=100.0, step=0.01, key="quick_entry_price")
                
                with col2:
                    position_type = st.selectbox("Position Type", ["long", "short", "call_option", "put_option"], key="quick_position_type")
                    from datetime import date
                    purchase_date = st.date_input("Purchase Date", value=date.today(), key="quick_purchase_date")
                
                notes = st.text_area("Notes (optional)", key="quick_portfolio_notes")
                
                if st.button("✅ Add to Portfolio", key="quick_confirm_portfolio"):
                    if not portfolio_id:
                        st.error("❌ Portfolio ID is required")
                    else:
                        try:
                            add_response = go_client.post(
                                f"api/v1/portfolio/{user_id}/{portfolio_id}/holdings",
                                json_data={
                                    "stock_symbol": symbol.upper(),
                                    "quantity": quantity,
                                    "avg_entry_price": avg_entry_price,
                                    "position_type": position_type,
                                    "purchase_date": purchase_date.strftime("%Y-%m-%d"),
                                    "notes": notes if notes else None
                                }
                            )
                            st.success(f"✅ {symbol.upper()} added to portfolio!")
                            st.json(add_response)
                        except APIError as e:
                            st.error(f"❌ Error: {e}")
            except Exception as e:
                st.error(f"❌ Error: {e}")
    
    st.markdown("---")
    
    # Now fetch and display stock data (Industry Standard: Fetch on-demand if not available)
    with st.spinner("Fetching data..."):
        try:
            data = get_stock_data(symbol.upper(), subscription_level)
        except APIError as e:
            st.error(f"❌ Failed to fetch stock data: {e}")
            st.stop()
        except Exception as e:
            st.error(f"❌ Unexpected error: {e}")
            st.stop()
        
        if data:
            indicators = data.get("indicators", {})
            signal_data = data.get("signal")
            
            # Display key metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Signal", signal_data.get("type", "N/A").upper() if signal_data else "N/A")
            
            with col2:
                rsi = indicators.get("rsi")
                st.metric("RSI", f"{rsi:.1f}" if rsi else "N/A")
            
            with col3:
                trend = indicators.get("long_term_trend", "N/A")
                st.metric("Long-term Trend", trend.upper() if trend else "N/A")
            
            with col4:
                momentum = indicators.get("momentum_score")
                if momentum and subscription_level in ["pro", "elite"]:
                    st.metric("Momentum Score", f"{momentum:.1f}")
                else:
                    st.metric("Momentum Score", "Pro/Elite Only")
            
            # Chart
            st.plotly_chart(plot_stock_chart(data), use_container_width=True)
            
            # Signal details
            if signal_data:
                st.subheader("Trading Signal")
                st.write(f"**Type:** {signal_data.get('type', 'N/A').upper()}")
                st.write(f"**Reason:** {signal_data.get('reason', 'N/A')}")
                
                if signal_data.get("pullback_zone") and subscription_level in ["pro", "elite"]:
                    pb = signal_data["pullback_zone"]
                    st.write(f"**Pullback Zone:** ${pb.get('lower', 0):.2f} - ${pb.get('upper', 0):.2f}")
                
                if signal_data.get("stop_loss") and subscription_level in ["pro", "elite"]:
                    st.write(f"**Stop Loss:** ${signal_data['stop_loss']:.2f}")
            
            # Advanced Analysis Section (Collapsible with Tabs)
            with st.expander("🔬 Advanced Analysis", expanded=False):
                if subscription_level == "basic":
                    st.warning("⚠️ Advanced Analysis is available for Pro and Elite subscribers only.")
                else:
                    # Create tabs for different advanced sections
                    # Add swing trading tab for Elite/Admin users
                    if subscription_level in ["elite", "admin"]:
                        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
                            "📊 Moving Averages",
                            "📉 MACD & RSI",
                            "📈 Volume",
                            "🧮 ATR & Volatility",
                            "🧠 AI Narrative",
                            "📚 Fundamentals",
                            "🏭 Industry & Peers",
                            "📈 Swing Trading"
                        ])
                    else:
                        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
                            "📊 Moving Averages",
                            "📉 MACD & RSI",
                            "📈 Volume",
                            "🧮 ATR & Volatility",
                            "🧠 AI Narrative",
                            "📚 Fundamentals",
                            "🏭 Industry & Peers"
                        ])
                        tab8 = None
                    
                    # Tab 1: Moving Averages
                    with tab1:
                        st.subheader("Moving Averages")
                        ma7 = indicators.get('ma7', 0)
                        ma21 = indicators.get('ma21', 0)
                        ema20 = indicators.get('ema20', 0)
                        sma50 = indicators.get('sma50', 0)
                        ema50 = indicators.get('ema50', 0)
                        sma200 = indicators.get('sma200', 0)
                        
                        if all([v == 0 or v is None for v in [ma7, ma21, ema20, sma50, ema50, sma200]]):
                            st.warning("⚠️ Indicators not calculated yet. Click '📥 Fetch Data' to calculate indicators.")
                            if st.button("🔄 Calculate Indicators Now", key="calc_indicators_ma"):
                                with st.spinner("Calculating indicators..."):
                                    refresh_result = refresh_data(symbol.upper(), data_types=["indicators"], force=True)
                                    if refresh_result and refresh_result.get('summary', {}).get('total_successful', 0) > 0:
                                        st.success("✅ Indicators calculated! Refreshing...")
                                        st.rerun()
                        else:
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write("**Short-term:**")
                                st.metric("MA7", f"{ma7:.2f}" if ma7 and ma7 > 0 else "N/A")
                                st.metric("MA21", f"{ma21:.2f}" if ma21 and ma21 > 0 else "N/A")
                                st.metric("EMA20", f"{ema20:.2f}" if ema20 and ema20 > 0 else "N/A")
                            with col2:
                                st.write("**Long-term:**")
                                st.metric("SMA50", f"{sma50:.2f}" if sma50 and sma50 > 0 else "N/A")
                                st.metric("EMA50", f"{ema50:.2f}" if ema50 and ema50 > 0 else "N/A")
                                st.metric("SMA200", f"{sma200:.2f}" if sma200 and sma200 > 0 else "N/A")
                    
                    # Tab 2: MACD & RSI
                    with tab2:
                        st.subheader("MACD & RSI Analysis")
                        macd = indicators.get('macd', 0)
                        macd_signal = indicators.get('macd_signal', 0)
                        macd_hist = indicators.get('macd_histogram', 0)
                        rsi = indicators.get('rsi', 0)
                        
                        if (macd == 0 or macd is None) and (rsi == 0 or rsi is None):
                            st.warning("⚠️ MACD & RSI indicators not calculated yet.")
                            if st.button("🔄 Calculate Indicators Now", key="calc_indicators_macd"):
                                with st.spinner("Calculating indicators..."):
                                    refresh_result = refresh_data(symbol.upper(), data_types=["indicators"], force=True)
                                    if refresh_result and refresh_result.get('summary', {}).get('total_successful', 0) > 0:
                                        st.success("✅ Indicators calculated! Refreshing...")
                                        st.rerun()
                        else:
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write("**MACD:**")
                                if macd and macd != 0:
                                    st.metric("MACD Line", f"{macd:.4f}")
                                else:
                                    st.write("MACD Line: N/A")
                                if macd_signal and macd_signal != 0:
                                    st.metric("Signal Line", f"{macd_signal:.4f}")
                                else:
                                    st.write("Signal Line: N/A")
                                if macd_hist and macd_hist != 0:
                                    st.metric("Histogram", f"{macd_hist:.4f}")
                                else:
                                    st.write("Histogram: N/A")
                            with col2:
                                st.write("**RSI:**")
                                if rsi and rsi > 0:
                                    st.metric("RSI", f"{rsi:.2f}")
                                    if rsi > 70:
                                        st.warning("⚠️ Overbought (>70)")
                                    elif rsi < 30:
                                        st.success("✅ Oversold (<30)")
                                    else:
                                        st.info("ℹ️ Neutral (30-70)")
                                else:
                                    st.write("RSI: N/A")
                    
                    # Tab 3: Volume
                    with tab3:
                        st.subheader("Volume Analysis")
                        # Get volume from indicators (volume_ma is the 20-day moving average)
                        volume_current = indicators.get('volume') or 0
                        volume_avg = indicators.get('volume_ma') or 0
                        
                        if volume_avg == 0 or volume_current == 0:
                            st.warning("⚠️ Volume data not available. Click '📥 Fetch Data' to fetch volume data.")
                        else:
                            col1, col2 = st.columns(2)
                            with col1:
                                st.metric("Current Volume", f"{int(volume_current):,}")
                            with col2:
                                st.metric("Average Volume (20-day MA)", f"{int(volume_avg):,}")
                            
                            if volume_current > volume_avg * 1.5:
                                st.success("✅ Volume spike detected (>150% of average)")
                            elif volume_current < volume_avg * 0.5:
                                st.warning("⚠️ Low volume (<50% of average)")
                    
                    # Tab 4: ATR & Volatility
                    with tab4:
                        st.subheader("ATR & Volatility")
                        atr = indicators.get('atr', 0)
                        volatility = indicators.get('volatility', 0)
                        
                        if atr == 0 and volatility == 0:
                            st.warning("⚠️ ATR & Volatility not calculated yet.")
                            if st.button("🔄 Calculate Indicators Now", key="calc_indicators_atr"):
                                with st.spinner("Calculating indicators..."):
                                    refresh_result = refresh_data(symbol.upper(), data_types=["indicators"], force=True)
                                    if refresh_result and refresh_result.get('summary', {}).get('total_successful', 0) > 0:
                                        st.success("✅ Indicators calculated! Refreshing...")
                                        st.rerun()
                        else:
                            col1, col2 = st.columns(2)
                            with col1:
                                if atr and atr > 0:
                                    st.metric("ATR (14)", f"${atr:.2f}")
                                else:
                                    st.write("ATR: N/A")
                            with col2:
                                if volatility and volatility > 0:
                                    st.metric("Volatility", f"{volatility:.2%}")
                                else:
                                    st.write("Volatility: N/A")
                    
                    # Tab 5: AI Narrative
                    with tab5:
                        st.subheader("AI Narrative")
                        try:
                            blog_data = get_llm_blog(symbol.upper())
                            if blog_data:
                                st.markdown(blog_data.get('content', 'No narrative available'))
                            else:
                                st.info("📝 No AI narrative available yet. Generate a report to create one.")
                        except Exception as e:
                            st.warning(f"⚠️ Could not load AI narrative: {e}")
                    
                    # Tab 6: Fundamentals
                    with tab6:
                        st.subheader("Fundamentals")
                        try:
                            fundamentals = get_fundamentals(symbol.upper())
                            if fundamentals:
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write("**Company Info:**")
                                    st.write(f"Market Cap: {fundamentals.get('market_cap', 'N/A')}")
                                    st.write(f"P/E Ratio: {fundamentals.get('pe_ratio', 'N/A')}")
                                    st.write(f"Dividend Yield: {fundamentals.get('dividend_yield', 'N/A')}")
                                with col2:
                                    st.write("**Financials:**")
                                    st.write(f"Revenue: {fundamentals.get('revenue', 'N/A')}")
                                    st.write(f"Profit Margin: {fundamentals.get('profit_margin', 'N/A')}")
                                    st.write(f"EPS: {fundamentals.get('eps', 'N/A')}")
                            else:
                                st.info("📊 No fundamentals data available. Click '📥 Fetch Data' to fetch fundamentals.")
                        except Exception as e:
                            st.warning(f"⚠️ Could not load fundamentals: {e}")
                    
                    # Tab 7: Industry & Peers
                    with tab7:
                        st.subheader("Industry & Peers")
                        try:
                            peers_data = get_industry_peers(symbol.upper())
                            if peers_data:
                                st.write(f"**Sector:** {peers_data.get('sector', 'N/A')}")
                                st.write(f"**Industry:** {peers_data.get('industry', 'N/A')}")
                                
                                peers = peers_data.get('peers', [])
                                if peers:
                                    st.write("**Industry Peers:**")
                                    df_peers = pd.DataFrame(peers)
                                    st.dataframe(df_peers)
                                else:
                                    st.info("No peer data available")
                            else:
                                st.info("📊 No industry peers data available. Click '📥 Fetch Data' to fetch peer data.")
                        except Exception as e:
                            st.warning(f"⚠️ Could not load industry peers: {e}")
                    
                    # Tab 8: Swing Trading (Elite/Admin only)
                    if tab8 is not None:
                        with tab8:
                            st.subheader("📈 Swing Trading Analysis")
                            st.markdown("**Quick swing trading signal analysis**")
                            
                            user_id = st.text_input("User ID", value="user1", key="swing_analysis_user")
                            
                            if st.button("🚀 Generate Swing Signal", key="swing_quick_analysis", use_container_width=True, type="primary"):
                                with st.spinner(f"📊 Analyzing {symbol.upper()} for swing trading signals..."):
                                    try:
                                        swing_result = get_swing_signal(symbol.upper(), user_id)
                                        
                                        if swing_result:
                                            signal = swing_result.get('signal', 'HOLD')
                                            confidence = swing_result.get('confidence', 0)
                                            reason = swing_result.get('reason', 'No reason provided')
                                            metadata = swing_result.get('metadata', {})
                                            
                                            # Signal display
                                            if signal == 'BUY':
                                                st.success(f"🟢 **Signal: {signal}** (Confidence: {confidence:.0%})")
                                            elif signal == 'SELL':
                                                st.error(f"🔴 **Signal: {signal}** (Confidence: {confidence:.0%})")
                                            else:
                                                st.info(f"🟡 **Signal: {signal}** (Confidence: {confidence:.0%})")
                                            
                                            st.write(f"**Reason:** {reason}")
                                            
                                            # Trade details
                                            if metadata:
                                                st.subheader("📋 Trade Details")
                                                col1, col2, col3 = st.columns(3)
                                                
                                                with col1:
                                                    if metadata.get('entry_price'):
                                                        st.metric("Entry Price", f"${metadata.get('entry_price', 0):.2f}")
                                                    if metadata.get('stop_loss'):
                                                        st.metric("Stop Loss", f"${metadata.get('stop_loss', 0):.2f}")
                                                
                                                with col2:
                                                    if metadata.get('take_profit'):
                                                        st.metric("Take Profit", f"${metadata.get('take_profit', 0):.2f}")
                                                    if metadata.get('risk_reward_ratio'):
                                                        st.metric("Risk/Reward", f"{metadata.get('risk_reward_ratio', 0):.2f}")
                                                
                                                with col3:
                                                    if metadata.get('position_size'):
                                                        st.metric("Position Size", f"{metadata.get('position_size', 0):.2%}")
                                                    if metadata.get('max_hold_days'):
                                                        st.metric("Max Hold Days", f"{metadata.get('max_hold_days', 0)}")
                                            
                                            # Full response
                                            with st.expander("📄 View Full Response"):
                                                st.json(swing_result)
                                    
                                    except APIError as e:
                                        error_msg = str(e)
                                        if "No market data available" in error_msg or "404" in error_msg:
                                            st.warning("⚠️ Data not available for swing analysis")
                                            st.info("💡 Click '📥 Fetch Data' at the top to fetch historical data first.")
                                        else:
                                            st.error(f"❌ Error: {error_msg}")
                                    except Exception as e:
                                        st.error(f"❌ Unexpected error: {e}")

