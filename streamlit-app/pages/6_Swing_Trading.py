"""
Swing Trading Page (Elite & Admin)
Swing trading signals, risk management, and trade execution
"""
import streamlit as st
import sys
import os
import pandas as pd
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar
from api_client import get_go_api_client, APIError
from shared_functions import fetch_historical_data

setup_page_config("Swing Trading", "📈")

def _display_fetch_results(fetch_response):
    """Display detailed fetch results with validation info"""
    if not fetch_response:
        return
    
    st.markdown("---")
    st.subheader("📊 Data Fetch Details")
    
    results = fetch_response.get('results', {})
    summary = fetch_response.get('summary', {})
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Requested", summary.get('total_requested', 0))
    with col2:
        st.metric("✅ Successful", summary.get('total_successful', 0))
    with col3:
        st.metric("❌ Failed", summary.get('total_failed', 0))
    with col4:
        st.metric("⏭️ Skipped", summary.get('total_skipped', 0))
    
    # Detailed results for each data type
    for data_type, result in results.items():
        if result is None:
            continue
        
        status = result.get('status', 'unknown')
        status_icon = "✅" if status == "success" else "❌" if status == "failed" else "⚠️"
        
        with st.expander(f"{status_icon} {data_type.replace('_', ' ').title()}: {status.upper()}", expanded=(status != "success")):
            st.write(f"**Status:** {status}")
            st.write(f"**Message:** {result.get('message', 'N/A')}")
            
            if result.get('rows_affected'):
                st.write(f"**Rows Affected:** {result.get('rows_affected')}")
            
            if result.get('error'):
                st.error(f"**Error:** {result.get('error')}")
            
            # Show validation report if available
            validation = result.get('validation')
            if validation:
                st.markdown("**🔍 Data Validation Report:**")
                val_status = validation.get('overall_status', 'unknown')
                val_color = "🟢" if val_status == "pass" else "🟡" if val_status == "warning" else "🔴"
                st.write(f"{val_color} **Overall Status:** {val_status.upper()}")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Rows", validation.get('total_rows', 0))
                with col2:
                    st.metric("Rows Dropped", validation.get('rows_dropped', 0))
                with col3:
                    st.metric("After Cleaning", validation.get('rows_after_cleaning', 0))
                
                if validation.get('critical_issues', 0) > 0:
                    st.error(f"🔴 **Critical Issues:** {validation.get('critical_issues', 0)}")
                if validation.get('warnings', 0) > 0:
                    st.warning(f"⚠️ **Warnings:** {validation.get('warnings', 0)}")
                
                # Show validation results
                val_results = validation.get('validation_results', [])
                if val_results:
                    with st.expander("📋 Detailed Validation Checks"):
                        for val_result in val_results:
                            check_name = val_result.get('check_name', 'Unknown')
                            passed = val_result.get('passed', False)
                            severity = val_result.get('severity', 'info')
                            
                            check_icon = "✅" if passed else "❌" if severity == "critical" else "⚠️"
                            st.write(f"{check_icon} **{check_name}:** {'PASSED' if passed else 'FAILED'}")
                            
                            if not passed:
                                issues = val_result.get('issues', [])
                                for issue in issues:
                                    st.write(f"   - {issue.get('message', 'N/A')}")
                                    if issue.get('recommendation'):
                                        st.info(f"   💡 {issue.get('recommendation')}")
                
                # Show recommendations
                recommendations = validation.get('recommendations', [])
                if recommendations:
                    st.info("**💡 Recommendations:**")
                    for rec in recommendations:
                        st.write(f"   - {rec}")


def _display_layers(layers: dict):
    if not layers or not isinstance(layers, dict):
        return

    st.markdown("---")
    st.subheader("🧠 Layered Swing Model (1 → 5)")

    l1 = layers.get("layer_1_regime") or {}
    l2 = layers.get("layer_2_direction") or {}
    l3 = layers.get("layer_3_allocation") or {}
    l4 = layers.get("layer_4_reality_adjustment") or {}
    l5 = layers.get("layer_5_daily_output") or {}

    # Layer 5: One clear output
    st.markdown("### ✅ Daily Output")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Date", l5.get("date", ""))
    with c2:
        st.metric("Action", l5.get("action", "HOLD"))
    with c3:
        st.metric("Vehicle", l5.get("symbol", "CASH"))
    with c4:
        alloc = l5.get("allocation_pct")
        st.metric("Allocation", f"{alloc:.0%}" if isinstance(alloc, (int, float)) else "N/A")
    with c5:
        conf = l5.get("confidence")
        st.metric("Confidence", f"{conf:.2f}" if isinstance(conf, (int, float)) else "N/A")


def _display_market_conditions_monitor(signal_response: dict):
    if not signal_response or not isinstance(signal_response, dict):
        return
    metadata = signal_response.get("metadata") or {}
    monitor = metadata.get("market_conditions_monitor") or {}
    if not isinstance(monitor, dict) or not monitor:
        return

    status = (monitor.get("status") or "").upper()
    color = (monitor.get("color") or "").lower()
    score = monitor.get("score")
    drivers = monitor.get("drivers") or []

    if color == "green":
        color_icon = "🟢"
    elif color == "orange":
        color_icon = "🟠"
    elif color == "red":
        color_icon = "🔴"
    else:
        color_icon = "⚪"

    st.markdown("---")
    st.subheader("🧭 Market Conditions Monitor")

    c1, c2 = st.columns([1, 3])
    with c1:
        st.metric("Status", f"{color_icon} {status or 'N/A'}")
        if isinstance(score, (int, float)):
            st.metric("Risk Score", f"{score:.2f}")
    with c2:
        if drivers and isinstance(drivers, list):
            for d in drivers[:8]:
                st.write(f"- {d}")

    # Layer 1
    with st.expander("Layer 1: Market Regime Detection", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Regime", str(l1.get("regime", "unknown")).upper())
        with col2:
            rc = l1.get("regime_confidence")
            st.metric("Regime Confidence", f"{rc:.2f}" if isinstance(rc, (int, float)) else "N/A")
        with col3:
            vix = l1.get("vix")
            st.metric("VIX", f"{vix:.2f}" if isinstance(vix, (int, float)) else "N/A")
        with col4:
            st.metric("NASDAQ Trend", str(l1.get("nasdaq_trend", "neutral")))

        col1, col2, col3 = st.columns(3)
        with col1:
            yc = l1.get("yield_curve_spread")
            st.metric("Yield Curve (10y-3m)", f"{yc:.2f}" if isinstance(yc, (int, float)) else "N/A")
        with col2:
            br = l1.get("breadth")
            st.metric("Breadth (% > 50d)", f"{br:.0%}" if isinstance(br, (int, float)) else "N/A")
        with col3:
            st.write("")

    # Layer 2
    with st.expander("Layer 2: Direction & Confidence", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            pu = l2.get("prob_up")
            st.metric("P(up)", f"{pu:.0%}" if isinstance(pu, (int, float)) else "N/A")
        with col2:
            pdn = l2.get("prob_down")
            st.metric("P(down)", f"{pdn:.0%}" if isinstance(pdn, (int, float)) else "N/A")
        with col3:
            ds = l2.get("direction_score")
            st.metric("Direction Score", f"{ds:.2f}" if isinstance(ds, (int, float)) else "N/A")

    # Layer 3
    with st.expander("Layer 3: Allocation Engine", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Suggested Vehicle", l3.get("suggested_vehicle", "CASH"))
        with col2:
            ap = l3.get("allocation_pct")
            st.metric("Allocation %", f"{ap:.0%}" if isinstance(ap, (int, float)) else "N/A")

    # Layer 4
    with st.expander("Layer 4: Leveraged ETF Reality Adjustment", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            op = l4.get("original_position_size")
            st.metric("Original Size", f"{op:.0%}" if isinstance(op, (int, float)) else "N/A")
        with col2:
            ap = l4.get("adjusted_position_size")
            st.metric("Adjusted Size", f"{ap:.0%}" if isinstance(ap, (int, float)) else "N/A")
        with col3:
            hd = l4.get("hold_duration_days")
            st.metric("Est. Hold Days", str(hd) if hd is not None else "N/A")

    # Reasoning
    reasoning = l5.get("reasoning")
    if reasoning:
        with st.expander("Why? (Reasoning)", expanded=False):
            for r in reasoning:
                st.write(f"- {r}")

st.title("📈 Swing Trading (Elite & Admin)")

# Sidebar
subscription_level = render_sidebar()

if subscription_level not in ["elite", "admin"]:
    st.warning("⚠️ Swing Trading is available for Elite and Admin users only.")
    st.info("💡 Upgrade to Elite to access swing trading features.")
else:
    # Tabs for different swing trading features
    tab1, tab2, tab3, tab4 = st.tabs(["🎯 Signals", "💼 Trades", "📊 Performance", "⚙️ Risk Management"])
    
    with tab1:
        st.subheader("Generate Swing Trading Signals")
        st.markdown("**Industry Standard**: Analyze any symbol directly - no portfolio/watchlist required")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            symbol = st.text_input("Symbol", value="TQQQ", key="swing_symbol", placeholder="e.g., TQQQ, SQQQ, SPY, QQQ")
        with col2:
            st.write("")  # Spacing
            user_id = st.text_input("User ID", value="user1", key="swing_user")
        
        # Fetch data button
        if st.button("📥 Fetch Data First", key="fetch_data_swing", use_container_width=True):
            with st.spinner(f"📥 Fetching data for {symbol.upper()}..."):
                try:
                    fetch_response = fetch_historical_data(symbol.upper(), period="1y", calculate_indicators=True)
                    if fetch_response and fetch_response.get('success'):
                        st.success("✅ Data fetched successfully!")
                        _display_fetch_results(fetch_response)
                        st.balloons()
                    else:
                        st.error("❌ Failed to fetch data. Please check the error details above.")
                except APIError as e:
                    st.error(f"❌ Error: {e}")
        
        # Quick analysis button
        if st.button("🚀 Generate Swing Signal", key="generate_swing_signal", use_container_width=True, type="primary"):
            if not symbol:
                st.error("⚠️ Please enter a symbol")
            else:
                with st.spinner(f"📊 Analyzing {symbol.upper()} for swing trading signals..."):
                    try:
                        response = get_swing_signal(symbol.upper(), subscription_level=subscription_level)
                        if response and response.get("success"):
                            st.success("✅ Swing signal generated successfully!")
                            st.session_state[f"swing_signal_{symbol}"] = response
                        else:
                            st.warning(response.get("message", "⚠️ Failed to generate swing signal"))
                            confidence = response.get('confidence', 0)
                            reason = response.get('reason', 'No reason provided')
                            metadata = response.get('metadata', {})
                            
                            # Signal display with color coding
                            if signal == 'BUY':
                                st.success(f"🟢 **Signal: {signal}** (Confidence: {confidence:.0%})")
                            elif signal == 'SELL':
                                st.error(f"🔴 **Signal: {signal}** (Confidence: {confidence:.0%})")
                            else:
                                st.info(f"🟡 **Signal: {signal}** (Confidence: {confidence:.0%})")
                            
                            # Display detailed reason (with diagnostics)
                            st.markdown("**📋 Signal Reason:**")
                            # Parse reason if it contains diagnostics
                            if "|" in reason:
                                # Split by | and display as bullet points
                                reason_parts = [r.strip() for r in reason.split("|")]
                                for part in reason_parts:
                                    if part.startswith("💡"):
                                        st.info(part)
                                    elif part.startswith("⚠️"):
                                        st.warning(part)
                                    else:
                                        st.write(f"   • {part}")
                            else:
                                st.write(reason)
                            
                            # Display metadata if available
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

                            # Layered breakdown (preferred)
                            layers = response.get("layers")
                            _display_market_conditions_monitor(response)

                            if layers:
                                _display_layers(layers)
                            
                            # Action buttons (Industry Standard: Add to Watchlist/Portfolio after analysis)
                            st.divider()
                            st.subheader("💡 Next Steps")
                            
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                add_to_watchlist = st.button("➕ Add to Watchlist", key=f"add_watchlist_{symbol}", use_container_width=True)
                            
                            with col2:
                                add_to_portfolio = st.button("💼 Add to Portfolio", key=f"add_portfolio_{symbol}", use_container_width=True)
                            
                            with col3:
                                set_alert = st.button("🔔 Set Alert", key=f"set_alert_{symbol}", use_container_width=True)
                            
                            # Add to Watchlist functionality
                            if add_to_watchlist:
                                with st.expander("➕ Add to Watchlist", expanded=True):
                                    try:
                                        go_client = get_go_api_client()
                                        # Get user's watchlists
                                        watchlists_response = go_client.get(f"api/v1/watchlists/user/{user_id}")
                                        watchlists = watchlists_response.get('watchlists', []) if watchlists_response else []
                                        
                                        if watchlists:
                                            watchlist_options = {w.get('watchlist_name'): w.get('watchlist_id') for w in watchlists}
                                            selected_watchlist_name = st.selectbox(
                                                "Select Watchlist",
                                                options=list(watchlist_options.keys()),
                                                key=f"select_watchlist_{symbol}"
                                            )
                                            selected_watchlist_id = watchlist_options.get(selected_watchlist_name)
                                            
                                            notes = st.text_area("Notes (optional)", key=f"watchlist_notes_{symbol}")
                                            
                                            if st.button("✅ Add Symbol", key=f"confirm_add_watchlist_{symbol}"):
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
                                            if st.button("📋 Go to Watchlist Management", key=f"goto_watchlist_{symbol}"):
                                                st.switch_page("pages/4_Watchlist.py")
                                    except APIError as e:
                                        st.error(f"❌ Error loading watchlists: {e}")
                            
                            # Add to Portfolio functionality
                            if add_to_portfolio:
                                with st.expander("💼 Add to Portfolio", expanded=True):
                                    try:
                                        go_client = get_go_api_client()
                                        # Get user's portfolios (we need to get them from the user)
                                        # For now, let user enter portfolio ID
                                        portfolio_id = st.text_input("Portfolio ID", key=f"portfolio_id_{symbol}", placeholder="e.g., portfolio1")
                                        
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            quantity = st.number_input("Quantity", min_value=0.01, value=1.0, step=0.01, key=f"quantity_{symbol}")
                                            avg_entry_price = st.number_input("Avg Entry Price ($)", min_value=0.01, value=float(metadata.get('entry_price', 100.0)) if metadata.get('entry_price') else 100.0, step=0.01, key=f"entry_price_{symbol}")
                                        
                                        with col2:
                                            position_type = st.selectbox("Position Type", ["long", "short", "call_option", "put_option"], key=f"position_type_{symbol}")
                                            purchase_date = st.date_input("Purchase Date", key=f"purchase_date_{symbol}")
                                        
                                        notes = st.text_area("Notes (optional)", key=f"portfolio_notes_{symbol}")
                                        
                                        if st.button("✅ Add to Portfolio", key=f"confirm_add_portfolio_{symbol}"):
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
                            
                            # Set Alert functionality (placeholder)
                            if set_alert:
                                st.info("💡 Alert feature - coming soon! This will set up price alerts for this symbol.")
                            
                            # Full response in expander
                            with st.expander("📄 View Full API Response"):
                                st.json(response)
                    except APIError as e:
                        error_msg = str(e)
                        if "No market data available" in error_msg or "404" in error_msg:
                            st.warning("⚠️ Data not available for this symbol")
                            st.info(f"💡 **Tip**: Click '📥 Fetch Data First' above to fetch historical data, then try again.")
                        else:
                            st.error(f"❌ Error: {error_msg}")
                    except Exception as e:
                        st.error(f"❌ Unexpected error: {e}")
    
    with tab2:
        st.subheader("Active Swing Trades")
        user_id = st.text_input("User ID", value="user1", key="swing_trades_user")
        
        if st.button("Load Trades", key="load_swing_trades"):
            st.info("💡 Swing trade management endpoints will be added")
    
    with tab3:
        st.subheader("Swing Trading Performance")
        user_id = st.text_input("User ID", value="user1", key="swing_perf_user")
        
        if st.button("Load Performance", key="load_swing_perf"):
            st.info("💡 Performance analytics will show win rate, Sharpe ratio, etc.")
    
    with tab4:
        st.subheader("Risk Management")
        user_id = st.text_input("User ID", value="user1", key="swing_risk_user")
        new_trade_risk = st.number_input("New Trade Risk ($)", min_value=0.0, value=500.0, key="swing_risk_amount")
        
        if st.button("Check Portfolio Heat", key="check_heat"):
            try:
                client = get_go_api_client()
                response = client.post(
                    "api/v1/admin/swing/risk/check",
                    json_data={
                        "user_id": user_id,
                        "new_trade_risk": new_trade_risk
                    }
                )
                if response:
                    st.json(response)
            except Exception as e:
                st.error(f"❌ Error: {e}")
