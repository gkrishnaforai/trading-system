"""
Stock Overview Page (Professional)
Shows last 7 days of news, ratings, price targets for a stock.
Includes a button to view detailed technical/fundamental analysis.
"""
import streamlit as st
import requests
from datetime import datetime, timedelta
import pandas as pd
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import get_go_api_client
from api_client import APIClient
from shared_functions import get_stock_data, refresh_data, plot_stock_chart
from components.analysis_display import display_signal_analysis, display_no_data_message
import pandas as pd

# Page config
st.set_page_config(
    page_title="Stock Overview",
    page_icon="📈",
    layout="wide",
)

# Initialize API client
api = get_go_api_client()
# Always set correct URL based on environment
import os
if os.path.exists('/.dockerenv'):
    api.base_url = "http://go-api:8000"
else:
    api.base_url = "http://localhost:8000"
print(f"DEBUG PRO: final api.base_url = {api.base_url}")

def format_change(val):
    """Format price change with color."""
    if val is None:
        return "—"
    change = f"{val:+.2f}"
    if val > 0:
        return f"🟢 {change}"
    elif val < 0:
        return f"🔴 {change}"
    else:
        return f"⚪ {change}"

def render_news_section(news_items):
    """Render news cards."""
    if not news_items:
        st.info("No recent news.")
        return
    cols = st.columns(min(len(news_items), 3))
    for i, article in enumerate(news_items[:6]):
        with cols[i % 3]:
            st.markdown(
                f"""
                <div style="border:1px solid #e0e0e0; padding:1rem; border-radius:8px; margin-bottom:1rem;">
                    <h5><a href="{article.get('link', '#')}" target="_blank">{article.get('title', 'No title')}</a></h5>
                    <p style="font-size:0.85em; color:#666;">{article.get('publisher', 'Unknown')} • {article.get('published_date', '')}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

def render_ratings_section(ratings):
    """Render ratings/price target cards."""
    if not ratings:
        st.info("No recent ratings.")
        return
    for r in ratings[:4]:
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            st.markdown(f"**{r.get('grading_company', '')}**")
            st.markdown(f"{r.get('previous_grade', '')} → {r.get('new_grade', '')}")
        with col2:
            st.markdown(f"*{r.get('action', '')}*")
            st.caption(r.get('grade_date', ''))
        with col3:
            if r.get('action', '').lower() in ('upgrade', 'initiated'):
                st.success("📈")
            elif r.get('action', '').lower() == 'downgrade':
                st.error("📉")
            else:
                st.info("📊")
        st.divider()

def render_price_target_section(targets):
    """Render price target summary."""
    if not targets:
        st.info("No price targets.")
        return
    # Aggregate targets
    df = pd.DataFrame(targets)
    avg_target = df['price_target'].mean()
    high_target = df['price_target'].max()
    low_target = df['price_target'].min()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Average Target", f"${avg_target:.2f}")
    with col2:
        st.metric("High Target", f"${high_target:.2f}")
    with col3:
        st.metric("Low Target", f"${low_target:.2f}")

def main():
    st.title("📈 Stock Overview")
    st.caption("Professional snapshot with last 7 days of news, ratings, and price targets")

    # Read symbol from query params if available
    query_params = st.query_params
    default_symbol = "AAPL"
    if "symbol" in query_params:
        default_symbol = query_params["symbol"]

    # Symbol selector and view options
    col1, col2 = st.columns([3, 1])
    with col1:
        symbol = st.text_input("Enter Stock Symbol", value=default_symbol, max_chars=10).strip().upper()
    with col2:
        email_view = st.checkbox("📧 Email View", help="Compact view optimized for email delivery")
    
    if not symbol:
        st.warning("Enter a symbol to view overview.")
        return

    # Fetch all data using enhanced alert-context endpoint (single API call)
    try:
        url = f"api/v1/stock/{symbol}/alert-context?days=7&grades_limit=50&news_limit=20"
        response = api.get(url)
        
        # Check if this is a "no data available" response
        if response.get("data_available") == False:
            st.error(f"No data available for {symbol}. Please run the batch worker to fetch market data first.")
            return
            
        # Extract all data from alert-context response
        stock = response.get("stock", {})
        fundamentals = response.get("fundamentals", {})
        news = response.get("news", [])
        grade_actions = response.get("grade_actions", [])
        consensus_data = response.get("consensus_data", {})
        price_targets = response.get("price_targets", {})
        
        # Get latest available price from multiple sources
        current_price = (
            stock.get('price') or  # From stock data
            fundamentals.get('current_price') or  # From fundamentals
            fundamentals.get('price') or  # Alternative fundamentals field
            fundamentals.get('close') or  # Close price
            None
        )
        
        if not stock or not stock.get("symbol"):
            st.error(f"Stock {symbol} not found.")
            return
    except Exception as e:
        st.error(f"Failed to fetch stock data for given stock symbol: {e}")
        return

    # Email-Optimized Summary Section (for quick scanning)
    st.markdown("## 📧 Email Alert Summary")
    
    # Key metrics row
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        current_price = fundamentals.get('current_price') or stock.get('current_price')
        st.metric("Current Price", f"${current_price:.2f}" if current_price else "N/A")
    with col2:
        if consensus_data:
            st.metric("Consensus", consensus_data.get('consensus_rating', 'N/A'))
        else:
            st.metric("Consensus", "No Data")
    with col3:
        if grade_actions:
            recent_upgrades = len([g for g in grade_actions if g.get('action') == 'upgrade'])
            st.metric("Recent Upgrades", recent_upgrades)
        else:
            st.metric("Recent Upgrades", "No Data")
    with col4:
        if price_targets and price_targets.get('price_targets'):
            avg_target = sum(pt.get('price_target', 0) for pt in price_targets['price_targets']) / len(price_targets['price_targets'])
            st.metric("Avg Target", f"${avg_target:.2f}")
        else:
            st.metric("Avg Target", "No Data")
    with col5:
        if news:
            st.metric("News Articles", len(news))
        else:
            st.metric("News Articles", "No Data")
    
    # Alert indicators
    alert_col1, alert_col2, alert_col3 = st.columns(3)
    with alert_col1:
        if consensus_data and consensus_data.get('consensus_rating') in ['Strong Buy', 'Buy']:
            st.success("🟢 Bullish Consensus")
        elif consensus_data and consensus_data.get('consensus_rating') in ['Strong Sell', 'Sell']:
            st.error("🔴 Bearish Consensus")
        else:
            st.info("🟡 Neutral/Mixed")
    
    with alert_col2:
        if grade_actions:
            upgrades = len([g for g in grade_actions if g.get('action') == 'upgrade'])
            downgrades = len([g for g in grade_actions if g.get('action') == 'downgrade'])
            if upgrades > downgrades:
                st.success(f"🟢 {upgrades} Upgrades vs {downgrades} Downgrades")
            elif downgrades > upgrades:
                st.error(f"🔴 {downgrades} Downgrades vs {upgrades} Upgrades")
            else:
                st.info(f"🟡 {upgrades} Upgrades, {downgrades} Downgrades")
        else:
            st.info("🟡 No Recent Rating Changes")
    
    with alert_col3:
        if price_targets and price_targets.get('price_targets') and current_price:
            avg_target = sum(pt.get('price_target', 0) for pt in price_targets['price_targets']) / len(price_targets['price_targets'])
            upside = ((avg_target - current_price) / current_price) * 100
            if upside > 10:
                st.success(f"🟢 {upside:.1f}% Upside Potential")
            elif upside < -10:
                st.error(f"🔴 {upside:.1f}% Downside Risk")
            else:
                st.info(f"🟡 {upside:.1f}% from Current")
        else:
            st.info("🟡 No Target Data")
    
    st.divider()

    # Email View - Compact, scannable format
    if email_view:
        st.markdown("## 📧 Email Alert Format")
        st.markdown(f"**{symbol} Stock Alert - {datetime.now().strftime('%Y-%m-%d %H:%M')}**")
        
        # One-liner summary
        summary_parts = []
        if consensus_data:
            summary_parts.append(f"Consensus: {consensus_data.get('consensus_rating', 'N/A')}")
        if current_price:
            summary_parts.append(f"Price: ${current_price:.2f}")
        if price_targets and price_targets.get('price_targets'):
            avg_target = sum(pt.get('price_target', 0) for pt in price_targets['price_targets']) / len(price_targets['price_targets'])
            if current_price:
                upside = ((avg_target - current_price) / current_price) * 100
                summary_parts.append(f"Avg Target: ${avg_target:.2f} ({upside:+.1f}%)")
            else:
                summary_parts.append(f"Avg Target: ${avg_target:.2f}")
        if grade_actions:
            upgrades = len([g for g in grade_actions if g.get('action') == 'upgrade'])
            downgrades = len([g for g in grade_actions if g.get('action') == 'downgrade'])
            summary_parts.append(f"Ratings: {upgrades}↑/{downgrades}↓")
        
        st.markdown(f"**Quick Summary:** {' | '.join(summary_parts)}")
        
        # Key highlights in bullet points
        st.markdown("### 🔍 Key Highlights:")
        highlights = []
        
        if consensus_data:
            rating = consensus_data.get('consensus_rating', 'N/A')
            if rating in ['Strong Buy', 'Buy']:
                highlights.append(f"🟢 **Bullish Consensus** ({rating})")
            elif rating in ['Strong Sell', 'Sell']:
                highlights.append(f"🔴 **Bearish Consensus** ({rating})")
            else:
                highlights.append(f"🟡 **Neutral Consensus** ({rating})")
        
        if grade_actions:
            upgrades = len([g for g in grade_actions if g.get('action') == 'upgrade'])
            downgrades = len([g for g in grade_actions if g.get('action') == 'downgrade'])
            if upgrades > downgrades:
                highlights.append(f"🟢 **Recent Momentum** ({upgrades} upgrades vs {downgrades} downgrades)")
            elif downgrades > upgrades:
                highlights.append(f"🔴 **Recent Pressure** ({downgrades} downgrades vs {upgrades} upgrades)")
        
        if price_targets and price_targets.get('price_targets') and current_price:
            avg_target = sum(pt.get('price_target', 0) for pt in price_targets['price_targets']) / len(price_targets['price_targets'])
            upside = ((avg_target - current_price) / current_price) * 100
            if upside > 10:
                highlights.append(f"🟢 **Strong Upside Potential** ({upside:.1f}% to avg target)")
            elif upside < -10:
                highlights.append(f"🔴 **Downside Risk** ({upside:.1f}% from avg target)")
        
        if news:
            highlights.append(f"📰 **{len(news)} Recent News Articles**")
        
        for highlight in highlights:
            st.markdown(f"- {highlight}")
        
        # Detailed sections (collapsed)
        with st.expander("📊 Detailed Analyst Ratings", expanded=False):
            if grade_actions:
                for action in grade_actions[:5]:  # Show top 5
                    action_emoji = "🟢" if action.get('action') == 'upgrade' else "🔴" if action.get('action') == 'downgrade' else "🟡"
                    st.markdown(f"{action_emoji} **{action.get('grading_company', 'N/A')}**: {action.get('previous_grade', 'N/A')} → {action.get('new_grade', 'N/A')} ({action.get('grade_date', 'N/A')})")
            else:
                st.info("No recent rating changes")
        
        with st.expander("🎯 Price Targets", expanded=False):
            if price_targets and price_targets.get('price_targets'):
                for target in price_targets['price_targets'][:3]:  # Show top 3
                    st.markdown(f"📈 **${target.get('price_target', 0):.2f}** - {target.get('analyst_firm', 'N/A')} ({target.get('target_date', 'N/A')})")
            else:
                st.info("No price targets available")
        
        with st.expander("📰 Recent News Headlines", expanded=False):
            if news:
                for article in news[:3]:  # Show top 3
                    st.markdown(f"📰 **{article.get('title', 'N/A')}** - {article.get('source', 'N/A')} ({article.get('published_date', 'N/A')})")
            else:
                st.info("No recent news")
        
        st.markdown("---")
        st.markdown(f"*Data sourced from {len(grade_actions) if grade_actions else 0} analysts, {price_targets.get('count', 0) if price_targets else 0} price targets, and {len(news) if news else 0} news articles*")
        st.markdown(f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        
        return  # Skip the regular view when in email mode

    # Header with key metrics (using available data)
    indicators = stock.get('indicators', {})
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        # Try to get current price from fundamentals or indicators
        price = fundamentals.get('price') or fundamentals.get('close') or 0
        st.metric("Price", f"${price:.2f}")
    with col2:
        market_cap = fundamentals.get('market_cap') or fundamentals.get('market_capitalization') or 0
        st.metric("Market Cap", f"${market_cap:,.0f}" if market_cap > 0 else "N/A")
    with col3:
        st.metric("SMA50", f"{indicators.get('sma50', 0):.2f}")
    with col4:
        st.metric("RSI", f"{indicators.get('rsi', 0):.1f}")
    with col5:
        st.metric("SMA200", f"{indicators.get('sma200', 0):.2f}")

    st.divider()

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📰 News", "⭐ Ratings", "🎯 Price Targets", "📈 Consensus", "🔍 Analysis"])

    with tab1:
        st.subheader("Recent News (Last 7 Days)")
        if news:
            render_news_section(news)
        else:
            st.info("No recent news available for this symbol.")

    with tab2:
        st.subheader("Analyst Ratings & Grade Actions")
        
        # Show grade actions (from separate call)
        if grade_actions:
            st.subheader("Recent Grade Actions")
            render_ratings_section(grade_actions)
        else:
            st.info("No recent grade actions available for this symbol.")
        
        # Note about individual analyst ratings
        st.info("💡 Individual analyst ratings can be loaded via the Analysis tab's data loading features")

    with tab3:
        st.subheader("Price Targets")
        if price_targets and price_targets.get("price_targets"):
            targets = price_targets["price_targets"]
            st.write(f"📊 Found {price_targets.get('count', 0)} price targets")
            
            for target in targets:
                with st.container():
                    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
                    with col1:
                        st.metric("Target Price", f"${target.get('price_target', 0):.2f}")
                    with col2:
                        st.write(f"**Firm:** {target.get('analyst_firm', 'N/A')}")
                    with col3:
                        st.write(f"**Analyst:** {target.get('analyst_name', 'N/A')}")
                    with col4:
                        if target.get('rating'):
                            st.write(f"**Rating:** {target.get('rating', 'N/A')}")
                    st.write(f"**Date:** {target.get('target_date', 'N/A')}")
                    st.divider()
        else:
            st.info("No price targets available for this symbol.")
    
    with tab4:
        st.subheader("Consensus Data")
        if consensus_data:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Consensus Rating", consensus_data.get('consensus_rating', 'N/A'))
                st.metric("Total Analysts", consensus_data.get('total_analysts', 0))
            with col2:
                st.write("**Buy Distribution:**")
                st.write(f"🟢 Strong Buy: {consensus_data.get('strong_buy', 0)}")
                st.write(f"� Buy: {consensus_data.get('buy', 0)}")
                st.write(f"🟡 Hold: {consensus_data.get('hold', 0)}")
            with col3:
                st.write("**Sell Distribution:**")
                st.write(f"🔴 Sell: {consensus_data.get('sell', 0)}")
                st.write(f"🔴 Strong Sell: {consensus_data.get('strong_sell', 0)}")
                st.write(f"📊 Consensus Score: {consensus_data.get('consensus_score', 0):.2f}")
            
            st.write(f"**Last Updated:** {consensus_data.get('last_updated', 'N/A')}")
        else:
            st.info("No consensus data available for this symbol.")

    with tab5:
        # Copy the exact show_symbol_analysis function from Enhanced Portfolio Analysis
        def show_symbol_analysis(symbol: str):
            """Show detailed analysis for a symbol using shared component"""
            st.markdown(f"### 📊 Detailed Analysis - {symbol}")
            
            # Action buttons for symbol analysis
            st.markdown("#### 🎯 Analysis Actions")
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                if st.button("🔄 Load All Data", type="primary", width='stretch', help=f"Load fresh data for {symbol}"):
                    # Load all data types for a single symbol (similar to Trading Dashboard)
                    all_data_types = [
                        "price_historical", "indicators", "fundamentals", 
                        "news", "earnings", "analyst_ratings", "insider_trading"
                    ]
                    try:
                        refresh_result = refresh_data(symbol.upper(), data_types=all_data_types, force=True)
                        if refresh_result and refresh_result.get('summary', {}).get('total_successful', 0) > 0:
                            st.success(f"✅ Data loaded for {symbol}")
                            st.rerun()
                        else:
                            st.warning("⚠️ Data loading may have failed")
                    except Exception as e:
                        st.error(f"❌ Error loading data: {e}")
            
            with col2:
                if st.button("📊 Refresh Analysis", width='stretch', help=f"Refresh analysis for {symbol}"):
                    try:
                        refresh_result = refresh_data(symbol.upper(), data_types=["price_historical", "indicators"], force=True)
                        if refresh_result:
                            st.success("✅ Analysis refreshed")
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error refreshing: {e}")
            
            with col3:
                if st.button("🔄 Refresh Page", width='stretch'):
                    st.rerun()
            
            st.markdown("---")
            
            # Get detailed analysis using the same method as Enhanced Portfolio Analysis
            with st.spinner(f"Loading fresh analysis for {symbol}..."):
                asset_type = "stock"  # Default, could be enhanced to get from holdings
                try:
                    payload = {
                        "symbol": symbol,
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "asset_type": asset_type
                    }
                    
                    analysis_data = api.post(
                        "api/v1/admin/universal/signal/universal",
                        json_data=payload,
                        timeout=180,
                    )
                    
                    if analysis_data and analysis_data.get("success"):
                        analysis_data = analysis_data["data"]
                    else:
                        analysis_data = {"error": analysis_data.get("error", "Unknown error")}
                        
                except Exception as e:
                    analysis_data = {"error": f"Request failed: {str(e)}"}
            
            # Enrich displayed technical reasoning with fundamentals overlay (best-effort).
            try:
                if isinstance(analysis_data, dict):
                    overlay = analysis_data.get("fundamentals_overlay")
                    sig = analysis_data.get("signal")
                    if isinstance(overlay, dict) and isinstance(sig, dict):
                        risk_state = str(overlay.get("risk_state") or "UNKNOWN")
                        pos_mult = overlay.get("position_size_multiplier")
                        conf_cap = overlay.get("confidence_cap")
                        alerts = overlay.get("active_fundamental_alerts") or []

                        # Cap displayed confidence if present.
                        try:
                            if conf_cap is not None and sig.get("confidence") is not None:
                                sig["confidence"] = float(min(float(sig.get("confidence")), float(conf_cap)))
                        except Exception:
                            pass

                        # Append overlay to reasoning.
                        try:
                            rs = []
                            if isinstance(sig.get("reasoning"), list):
                                rs = [str(x) for x in sig.get("reasoning") if x is not None]
                            overlay_reason = f"Fundamentals overlay: risk_state={risk_state}, position_size_multiplier={pos_mult}, confidence_cap={conf_cap}"
                            if isinstance(alerts, list) and alerts:
                                top = "; ".join([str(a) for a in alerts[:3] if a is not None])
                                overlay_reason = overlay_reason + f" | alerts: {top}"
                            rs.append(overlay_reason)
                            sig["reasoning"] = rs
                        except Exception:
                            pass
                        analysis_data["signal"] = sig
            except Exception:
                pass
            
            # Display analysis using shared component
            if analysis_data and not analysis_data.get('error'):
                display_signal_analysis(symbol, analysis_data, show_header=True, show_debug=True)
            else:
                display_no_data_message(symbol, analysis_data.get('error') if analysis_data else None, context="main")
            
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
                    display_no_data_message(symbol, analysis_data.get('error') if analysis_data else None, context="tab1")
            
            with tab2:
                # Fundamentals analysis with industry comparison
                try:
                    # Get industry comparison data
                    with st.spinner(f"Loading industry comparison for {symbol}..."):
                        try:
                            industry_comparison = api.get(f"api/v1/admin/industry/{symbol}/comparison")
                        except:
                            industry_comparison = None
                    
                    # Display industry comparison if available
                    if industry_comparison and industry_comparison.get('metrics'):
                        st.markdown("#### 🏭 Industry Comparison")
                        
                        metrics = industry_comparison['metrics']
                        industry = industry_comparison.get('industry', 'Unknown')
                        
                        st.write(f"**Industry:** {industry}")
                        
                        # Create comparison table
                        comparison_data = []
                        
                        # Revenue Growth
                        if 'revenue_growth' in metrics:
                            rg = metrics['revenue_growth']
                            comparison_data.append({
                                'Metric': 'Revenue Growth',
                                'Value': f"{rg['symbol_value']:.1%}" if rg['symbol_value'] else 'N/A',
                                'Target': '≥ 15%',
                                'Status': '✅' if rg.get('meets_target') else '❌'
                            })
                        
                        # Gross Margin vs Industry
                        if 'gross_margin' in metrics:
                            gm = metrics['gross_margin']
                            symbol_val = f"{gm['symbol_value']:.1%}" if gm['symbol_value'] else 'N/A'
                            median_val = f"{gm['industry_median']:.1%}" if gm['industry_median'] else 'N/A'
                            vs_median = f"{gm['vs_median_pct']:+.1f}%" if gm.get('vs_median_pct') else 'N/A'
                            status = '✅' if gm.get('outperforms') else '❌'
                            
                            comparison_data.append({
                                'Metric': 'Gross Margin vs Industry',
                                'Value': f"{symbol_val} (vs {median_val})",
                                'Target': 'Above Median',
                                'Status': status,
                                'vs_median': vs_median
                            })
                        
                        # ROIC
                        if 'roic' in metrics:
                            roic = metrics['roic']
                            symbol_val = f"{roic['symbol_value']:.1%}" if roic['symbol_value'] else 'N/A'
                            target_met = roic['symbol_value'] and roic['symbol_value'] >= 0.15  # 15%
                            comparison_data.append({
                                'Metric': 'ROIC',
                                'Value': symbol_val,
                                'Target': '≥ 15%',
                                'Status': '✅' if target_met else '❌'
                            })
                        
                        # Debt/Equity
                        if 'debt_to_equity' in metrics:
                            de = metrics['debt_to_equity']
                            symbol_val = f"{de['symbol_value']:.2f}" if de['symbol_value'] else 'N/A'
                            target_met = de['symbol_value'] and de['symbol_value'] <= 1.5
                            comparison_data.append({
                                'Metric': 'Debt/Equity',
                                'Value': symbol_val,
                                'Target': '< 1.5',
                                'Status': '✅' if target_met else '❌'
                            })
                        
                        # Display comparison table
                        if comparison_data:
                            import pandas as pd
                            df_comparison = pd.DataFrame(comparison_data)
                            st.dataframe(df_comparison, use_container_width=True, hide_index=True)
                        
                        # Summary
                        st.markdown("#### 📊 Investment Quality Checklist")
                        checklist_items = []
                        
                        if 'revenue_growth' in metrics and metrics['revenue_growth'].get('meets_target'):
                            checklist_items.append("✅ Revenue growth > 15%")
                        else:
                            checklist_items.append("❌ Revenue growth > 15%")
                        
                        if 'gross_margin' in metrics and metrics['gross_margin'].get('outperforms'):
                            checklist_items.append("✅ Gross margin > industry median")
                        else:
                            checklist_items.append("❌ Gross margin > industry median")
                        
                        if 'roic' in metrics and metrics['roic']['symbol_value'] and metrics['roic']['symbol_value'] >= 0.15:
                            checklist_items.append("✅ ROIC > 15%")
                        else:
                            checklist_items.append("❌ ROIC > 15%")
                        
                        if 'debt_to_equity' in metrics and metrics['debt_to_equity']['symbol_value'] and metrics['debt_to_equity']['symbol_value'] <= 1.5:
                            checklist_items.append("✅ Debt/Equity < 1.5")
                        else:
                            checklist_items.append("❌ Debt/Equity < 1.5")
                        
                        # Check FCF (from fundamentals data)
                        fundamentals = response.get('fundamentals', {})
                        fcf = fundamentals.get('free_cash_flow')
                        if fcf and fcf > 0:
                            checklist_items.append("✅ Positive FCF")
                        else:
                            checklist_items.append("❌ Positive FCF")
                        
                        for item in checklist_items:
                            st.write(item)
                        
                        # Overall score
                        passed = sum(1 for item in checklist_items if item.startswith("✅"))
                        total = len(checklist_items)
                        score_pct = (passed / total) * 100
                        
                        st.markdown(f"#### 🎯 Overall Score: {passed}/{total} ({score_pct:.0f}%)")
                        
                        if score_pct >= 80:
                            st.success("🌟 Excellent investment quality!")
                        elif score_pct >= 60:
                            st.info("👍 Good investment quality")
                        elif score_pct >= 40:
                            st.warning("⚠️ Moderate investment quality")
                        else:
                            st.error("🚨 Poor investment quality")
                    
                    # Original growth health analysis
                    with st.spinner(f"Loading fundamentals analysis for {symbol}..."):
                        response = api.get(f"api/v1/admin/growth-quality/growth-health/{symbol}")

                        if response and isinstance(response, dict):
                            data = response
                            st.markdown("#### 📈 Growth Health Analysis")
                            
                            # Display key metrics
                            if isinstance(data, dict):
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write("**Growth Metrics:**")
                                    for key in ['revenue_growth', 'earnings_growth', 'margin_trend']:
                                        if key in data:
                                            st.write(f"- {key}: {data[key]}")
                                
                                with col2:
                                    st.write("**Quality Metrics:**")
                                    for key in ['roe_trend', 'debt_ratio', 'cash_flow']:
                                        if key in data:
                                            st.write(f"- {key}: {data[key]}")
                            
                            st.success("✅ Fundamentals analysis loaded")
                        else:
                            err = response.get('error', 'Unknown error') if isinstance(response, dict) else 'Unknown error'
                            st.error(f"❌ Error: {err}")
                            
                            # Show retry button
                            if st.button("🔄 Retry Analysis", key=f"retry_error_fundamentals_{symbol}"):
                                st.rerun()

                    st.markdown("---")
                    try:
                        ew = api.get(f"api/v1/admin/growth-quality/early-warning/{symbol}")
                        if isinstance(ew, dict):
                            st.markdown("#### ⚠️ Early Warning Flags")
                            overall_risk = ew.get("overall_risk", "UNKNOWN")
                            warnings = ew.get("warnings", [])
                            
                            st.metric("Overall Risk", overall_risk)
                            
                            if warnings:
                                st.write("**Warnings:**")
                                for warning in warnings[:5]:  # Show first 5 warnings
                                    st.write(f"- {warning}")
                            else:
                                st.info("No early warning flags detected")
                        else:
                            st.info("No early warning data available")
                    except Exception:
                        st.info("Early warning data not available")

                except Exception as e:
                    st.error(f"❌ Error in fundamentals analysis: {str(e)}")
        
        # Call the adaptive analysis function
        show_adaptive_analysis(symbol, api, response)
        
        # Add fundamental analysis tab
        show_fundamental_analysis(symbol, api)

def show_adaptive_analysis(symbol: str, api, response: dict):
    """Display adaptive signal analysis with scoring and market context"""
    
    st.markdown(f"### 🎯 Adaptive Signal Analysis - {symbol}")
    
    # Get adaptive signal
    with st.spinner("🔄 Generating adaptive signal analysis..."):
        try:
            signal_data = api.post(
                "api/v1/admin/universal/signal/universal",
                json_data={
                    "symbol": symbol,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "asset_type": "stock"
                }
            )
        except Exception as e:
            st.error(f"❌ Error fetching adaptive signal: {e}")
            return
    
    if signal_data and signal_data.get("success"):
        signal = signal_data["data"]["signal"]
        
        # Check if we have adaptive scores (new system)
        if "scores" in signal:
            scores = signal["scores"]
            metadata = signal["metadata"]
            
            # Display adaptive factors
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("#### 🏛️ Market Regime")
                regime = metadata.get("market_regime", "Unknown")
                st.write(f"**Regime:** {regime.replace('_', ' ').title()}")
                regime_confidence = metadata.get("regime_confidence", 0)
                st.write(f"**Confidence:** {regime_confidence:.1%}")
            
            with col2:
                st.markdown("#### 📊 Volatility Profile")
                vol = metadata.get("volatility_profile", "Unknown")
                st.write(f"**Profile:** {vol.title()}")
                atr_pct = metadata.get("volatility_atr_pct", 0)
                st.write(f"**ATR:** {atr_pct:.2%}")
                vol_percentile = metadata.get("volatility_percentile", 0)
                st.write(f"**Percentile:** {vol_percentile:.1%}")
            
            with col3:
                st.markdown("#### 🎯 Relative Strength")
                rs = metadata.get("relative_strength", "Unknown")
                st.write(f"**Strength:** {rs.replace('_', ' ').title()}")
                rs_value = metadata.get("relative_strength_value", 0)
                st.write(f"**vs SPY:** {rs_value:+.2%}")
                consistency = metadata.get("momentum_consistency", 0)
                st.write(f"**Consistency:** {consistency:.1%}")
            
            # Display signal scores
            st.markdown("#### 📈 Signal Scores")
            
            score_data = [
                {"Signal": "BUY", "Score": f"{scores['buy_score']:.2f}", "Level": _get_score_level(scores['buy_score'])},
                {"Signal": "SELL", "Score": f"{scores['sell_score']:.2f}", "Level": _get_score_level(scores['sell_score'])},
                {"Signal": "HOLD", "Score": f"{scores['hold_score']:.2f}", "Level": _get_score_level(scores['hold_score'])},
                {"Signal": "REDUCE", "Score": f"{scores['reduce_score']:.2f}", "Level": _get_score_level(scores['reduce_score'])}
            ]
            
            df_scores = pd.DataFrame(score_data)
            st.dataframe(df_scores, use_container_width=True, hide_index=True)
            
            # Score visualization
            try:
                import plotly.graph_objects as go
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=list(scores.keys()),
                    y=list(scores.values()),
                    marker_color=['green' if k == 'buy_score' else 'red' if k == 'sell_score' else 'gray' for k in scores.keys()]
                ))
                fig.update_layout(
                    title="Signal Score Distribution", 
                    yaxis_title="Score (0-1)",
                    xaxis_title="Signal Type"
                )
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                st.info("Score chart unavailable")
            
            # Display primary signal and confidence
            primary_signal = signal["signal"]
            confidence = signal["confidence"]
            
            # Signal status card
            signal_color = {
                "buy": "green",
                "sell": "red", 
                "hold": "gray",
                "reduce": "orange"
            }.get(primary_signal.lower(), "gray")
            
            st.markdown(f"#### 🎯 Primary Signal: {primary_signal.upper()}")
            st.markdown(f'<div style="background-color: {signal_color}; color: white; padding: 10px; border-radius: 5px; text-align: center;">',
                     unsafe_allow_html=True)
            st.markdown(f'<h3 style="color: white; margin: 0;">{primary_signal.upper()}</h3>', unsafe_allow_html=True)
            st.markdown(f'<p style="color: white; margin: 0;">Confidence: {confidence:.1%}</p>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Display reasoning with adaptive context
            st.markdown("#### 🧠 Adaptive Reasoning")
            for reason in signal["reasoning"]:
                st.write(f"• {reason}")
            
            # Show adaptive configuration used
            config_used = metadata.get("config_used", {})
            if config_used:
                st.markdown("#### ⚙️ Adaptive Configuration")
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**RSI Oversold:** {config_used.get('rsi_oversold', 'N/A')}")
                    st.write(f"**RSI Overbought:** {config_used.get('rsi_overbought', 'N/A')}")
                    st.write(f"**Breakout Threshold:** {config_used.get('breakout_threshold', 'N/A')}")
                with col2:
                    st.write(f"**Confidence Boost:** {config_used.get('confidence_boost', 'N/A')}")
                    st.write(f"**Stop Loss:** {config_used.get('stop_loss_pct', 'N/A')}")
                    st.write(f"**Take Profit:** {config_used.get('take_profit_pct', 'N/A')}")
            
            # Trading implications based on market context
            st.markdown("#### 📋 Trading Implications")
            
            regime = metadata.get("market_regime", "unknown")
            vol_profile = metadata.get("volatility_profile", "unknown")
            rs_tier = metadata.get("relative_strength", "unknown")
            
            implications = []
            
            # Regime-based implications
            if "bull" in regime:
                implications.append("🟢 Bull market: Favor momentum and trend-following strategies")
            elif "bear" in regime:
                implications.append("🔴 Bear market: Focus on capital preservation, deep oversold entries only")
            else:
                implications.append("🟡 Sideways market: Use mean reversion and range-bound strategies")
            
            # Volatility-based implications
            if vol_profile == "high":
                implications.append("⚠️ High volatility: Use wider stops, smaller position sizes")
            elif vol_profile == "low":
                implications.append("✅ Low volatility: Can use tighter stops, larger positions")
            
            # Relative strength implications
            if "outperformer" in rs_tier:
                implications.append("🚀 Strong relative strength: Consider full position sizes")
            elif "underperformer" in rs_tier:
                implications.append("⛔ Weak relative strength: Reduce position sizes or avoid long positions")
            
            for implication in implications:
                st.write(f"• {implication}")
        
        else:
            # Fallback to original display for non-adaptive signals
            st.info("Adaptive scoring not available, showing basic signal")
            st.write(f"**Signal:** {signal['signal'].upper()}")
            st.write(f"**Confidence:** {signal['confidence']:.1%}")
            for reason in signal["reasoning"]:
                st.write(f"• {reason}")
    
    else:
        st.error("❌ Failed to load adaptive signal analysis")

def _get_score_level(score: float) -> str:
    """Convert score to descriptive level"""
    if score >= 0.8:
        return "Very Strong"
    elif score >= 0.6:
        return "Strong"
    elif score >= 0.4:
        return "Moderate"
    elif score >= 0.2:
        return "Weak"
    else:
        return "Very Weak"

def show_fundamental_analysis(symbol: str, api):
    """Display comprehensive fundamental analysis with fair value"""
    
    st.markdown(f"### 💰 Fundamental Analysis - {symbol}")
    
    # Get fair value analysis
    with st.spinner("🔄 Calculating fair value analysis..."):
        try:
            fair_value_data = api.post(
                "api/v1/admin/fundamentals/fair-value",
                json_data={"symbol": symbol}
            )
        except Exception as e:
            st.error(f"❌ Error fetching fair value analysis: {e}")
            return
    
    if fair_value_data and fair_value_data.get("success"):
        analysis = fair_value_data["data"]
        
        # Valuation Summary
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("#### 💰 Valuation")
            current_price = analysis["current_price"]
            fair_value = analysis["fair_value"]
            valuation_ratio = analysis["valuation_ratio"]
            
            if valuation_ratio < 0.9:
                st.success(f"Undervalued: {valuation_ratio:.2f}x fair value")
            elif valuation_ratio > 1.1:
                st.error(f"Overvalued: {valuation_ratio:.2f}x fair value")
            else:
                st.info(f"Fair value: {valuation_ratio:.2f}x")
            
            st.metric("Current Price", f"${current_price:.2f}")
            st.metric("Fair Value", f"${fair_value:.2f}")
            st.metric("Undervaluation", f"{analysis['undervaluation_pct']:+.1f}%")
        
        with col2:
            st.markdown("#### 📈 Quality Score")
            quality_score = analysis["quality_score"]
            
            # Quality gauge
            try:
                import plotly.graph_objects as go
                fig = go.Figure(go.Indicator(
                    mode = "gauge+number+delta",
                    value = quality_score,
                    domain = {'x': [0, 1], 'y': [0, 1]},
                    title = {'text': "Quality Score"},
                    delta = {'reference': 70},
                    gauge = {
                        'axis': {'range': [None, 100]},
                        'bar': {'color': "darkblue"},
                        'steps': [
                            {'range': [0, 40], 'color': "lightgray"},
                            {'range': [40, 70], 'color': "gray"},
                            {'range': [70, 100], 'color': "lightgreen"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': 90
                        }
                    }
                ))
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                st.metric("Quality Score", f"{quality_score}/100")
        
        with col3:
            st.markdown("#### 🎯 Entry Signal")
            entry_signal = analysis["entry_signal"]
            
            signal_color = {
                "BUY": "green",
                "WAIT": "orange", 
                "HOLD": "gray",
                "SELL": "red",
                "REDUCE": "purple"
            }.get(entry_signal["signal"], "gray")
            
            st.markdown(f'<div style="background-color: {signal_color}; color: white; padding: 10px; border-radius: 5px;">',
                     unsafe_allow_html=True)
            st.markdown(f'<h4 style="color: white; margin: 0;">{entry_signal["signal"]}</h4>', unsafe_allow_html=True)
            st.markdown(f'<p style="color: white; margin: 0;">{entry_signal["reason"]}</p>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            if entry_signal.get("confidence"):
                st.metric("Confidence", f"{entry_signal['confidence']:.1%}")
            
            if entry_signal.get("target_price"):
                st.metric("Target", f"${entry_signal['target_price']:.2f}")
            
            if entry_signal.get("stop_loss"):
                st.metric("Stop Loss", f"${entry_signal['stop_loss']:.2f}")
        
        # Detailed metrics
        st.markdown("#### 📊 Fundamental Metrics")
        
        fundamentals = analysis.get("fundamentals", {})
        industry_comparison = analysis.get("industry_comparison", {})
        
        metrics_data = [
            {"Metric": "EPS (TTM)", "Value": f"${fundamentals.get('eps_ttm', 0):.2f}", "YoY Growth": f"{fundamentals.get('eps_yoy_growth', 0):.1%}"},
            {"Metric": "Forward P/E", "Value": f"{fundamentals.get('current_pe', 0):.1f}", "vs Industry": f"{industry_comparison.get('comparisons', {}).get('pe_vs_industry', 0):+.1f}"},
            {"Metric": "PEG Ratio", "Value": f"{fundamentals.get('peg_ratio', 0):.2f}", "Rating": _get_peg_rating(fundamentals.get('peg_ratio', 0))},
            {"Metric": "Gross Margin", "Value": f"{fundamentals.get('gross_margin', 0):.1%}", "vs Industry": f"{industry_comparison.get('comparisons', {}).get('margin_vs_industry', 0):+.1%}"},
            {"Metric": "ROIC", "Value": f"{fundamentals.get('roic', 0):.1%}", "Rating": _get_roic_rating(fundamentals.get('roic', 0))},
            {"Metric": "Debt/Equity", "Value": f"{fundamentals.get('debt_to_equity', 0):.2f}", "Rating": _get_debt_rating(fundamentals.get('debt_to_equity', 0))}
        ]
        
        df_metrics = pd.DataFrame(metrics_data)
        st.dataframe(df_metrics, use_container_width=True, hide_index=True)
        
        # Valuation methods comparison
        st.markdown("#### 🎯 Fair Value Methods")
        
        individual_valuations = analysis.get("individual_valuations", {})
        valuation_metrics = analysis.get("valuation_metrics", {})
        peg_rule_of_40_metrics = valuation_metrics.get("peg_rule_of_40_forward_cagr") if isinstance(valuation_metrics, dict) else None
        peg_rule_of_40_fair_price = None
        if isinstance(peg_rule_of_40_metrics, dict) and peg_rule_of_40_metrics.get("enabled") is True:
            try:
                peg_rule_of_40_fair_price = float(peg_rule_of_40_metrics.get("fair_price"))
            except Exception:
                peg_rule_of_40_fair_price = None

        method_data = [
            {"Method": "PEG Method", "Fair Value": f"${individual_valuations.get('peg_method', 0):.2f}", "vs Current": f"{(individual_valuations.get('peg_method', 0)/current_price - 1):+.1%}"},
            {"Method": "P/E Method", "Fair Value": f"${individual_valuations.get('pe_method', 0):.2f}", "vs Current": f"{(individual_valuations.get('pe_method', 0)/current_price - 1):+.1%}"},
            {"Method": "DCF Method", "Fair Value": f"${individual_valuations.get('dcf_method', 0):.2f}", "vs Current": f"{(individual_valuations.get('dcf_method', 0)/current_price - 1):+.1%}"}
        ]

        if peg_rule_of_40_fair_price is not None and current_price > 0:
            method_data.insert(
                1,
                {
                    "Method": "PEG Rule-of-40 (Forward CAGR)",
                    "Fair Value": f"${peg_rule_of_40_fair_price:.2f}",
                    "vs Current": f"{(peg_rule_of_40_fair_price/current_price - 1):+.1%}",
                },
            )
        
        df_methods = pd.DataFrame(method_data)
        st.dataframe(df_methods, use_container_width=True, hide_index=True)
        
        # Fundamental scores
        st.markdown("#### 📈 Fundamental Signal Scores")
        
        fundamental_scores = analysis.get("fundamental_scores", {})
        score_data = [
            {"Signal": "BUY", "Score": f"{fundamental_scores.get('buy_score', 0):.2f}", "Level": _get_score_level(fundamental_scores.get('buy_score', 0))},
            {"Signal": "SELL", "Score": f"{fundamental_scores.get('sell_score', 0):.2f}", "Level": _get_score_level(fundamental_scores.get('sell_score', 0))},
            {"Signal": "HOLD", "Score": f"{fundamental_scores.get('hold_score', 0):.2f}", "Level": _get_score_level(fundamental_scores.get('hold_score', 0))},
            {"Signal": "REDUCE", "Score": f"{fundamental_scores.get('reduce_score', 0):.2f}", "Level": _get_score_level(fundamental_scores.get('reduce_score', 0))}
        ]
        
        df_fund_scores = pd.DataFrame(score_data)
        st.dataframe(df_fund_scores, use_container_width=True, hide_index=True)
        
        # Fundamental reasoning
        if fundamental_scores.get("reasoning"):
            st.markdown("#### 🧠 Fundamental Reasoning")
            for reason in fundamental_scores["reasoning"]:
                st.write(f"• {reason}")
        
        # Industry comparison
        if industry_comparison:
            st.markdown("#### 🏭 Industry Comparison")
            
            industry = industry_comparison.get("industry", "Unknown")
            benchmarks = industry_comparison.get("benchmarks", {})
            
            col1, col2 = st.columns(2)
            
            # Industry benchmarks with safe formatting
            def format_metric(value, format_str):
                if isinstance(value, (int, float)):
                    return format_str % value
                return str(value)
            
            with col1:
                st.write(f"**Industry:** {industry}")
                st.write(f"**Industry Avg P/E:** {benchmarks.get('avg_pe', 'N/A')}")
                st.write(f"**Industry Avg PEG:** {benchmarks.get('avg_peg', 'N/A')}")
                st.write(f"**Industry Avg Growth:** {format_metric(benchmarks.get('avg_growth', 'N/A'), '%.1f%%')}")
            
            with col2:
                st.write(f"**Industry Avg Margin:** {format_metric(benchmarks.get('avg_margin', 'N/A'), '%.1f%%')}")
                st.write(f"**Industry Avg ROIC:** {format_metric(benchmarks.get('avg_roic', 'N/A'), '%.1f%%')}")
                st.write(f"**Industry Avg D/E:** {format_metric(benchmarks.get('avg_debt_equity', 'N/A'), '%.2f')}")
        
        # Trading recommendations
        st.markdown("#### 📋 Trading Recommendations")
        
        recommendations = []
        
        # Valuation-based recommendations
        if valuation_ratio < 0.85:
            recommendations.append("🟢 **Strong Buy**: Deeply undervalued with good quality")
        elif valuation_ratio < 0.95:
            recommendations.append("🟡 **Buy**: Moderately undervalued")
        elif valuation_ratio > 1.15:
            recommendations.append("🔴 **Avoid**: Significantly overvalued")
        else:
            recommendations.append("⚪ **Hold**: Fair valuation")
        
        # Quality-based recommendations
        if quality_score > 80:
            recommendations.append("⭐ **High Quality**: Excellent fundamentals - consider full position")
        elif quality_score < 40:
            recommendations.append("⚠️ **Low Quality**: Poor fundamentals - avoid or small position")
        
        # Entry timing
        if entry_signal["signal"] == "BUY":
            recommendations.append(f"🎯 **Entry Now**: {entry_signal['reason']}")
        elif entry_signal["signal"] == "WAIT":
            watch_price = entry_signal.get("watch_price", current_price * 0.95)
            recommendations.append(f"⏰ **Wait for Entry**: Consider at ${watch_price:.2f}")
        
        for rec in recommendations:
            st.write(f"• {rec}")
        
    else:
        st.error("❌ Failed to load fundamental analysis")

def _get_peg_rating(peg_ratio: float) -> str:
    """Get PEG rating"""
    if peg_ratio <= 0:
        return "Invalid"
    elif peg_ratio <= 0.5:
        return "Excellent"
    elif peg_ratio <= 1.0:
        return "Good"
    elif peg_ratio <= 1.5:
        return "Fair"
    elif peg_ratio <= 2.0:
        return "Poor"
    else:
        return "Very Poor"

def _get_roic_rating(roic: float) -> str:
    """Get ROIC rating"""
    if roic >= 15:
        return "Excellent"
    elif roic >= 10:
        return "Good"
    elif roic >= 5:
        return "Average"
    elif roic >= 0:
        return "Poor"
    else:
        return "Very Poor"

def _get_debt_rating(debt_to_equity: float) -> str:
    """Get debt rating"""
    if debt_to_equity <= 0.3:
        return "Excellent"
    elif debt_to_equity <= 0.6:
        return "Good"
    elif debt_to_equity <= 1.0:
        return "Average"
    elif debt_to_equity <= 2.0:
        return "Poor"
    else:
        return "Very Poor"

def render_analyst_ratings_section(analyst_ratings):
    """Render individual analyst ratings"""
    if not analyst_ratings:
        st.info("No individual analyst ratings available.")
        return
    
    # Convert to DataFrame for easier manipulation
    df_ratings = pd.DataFrame(analyst_ratings)
    
    if df_ratings.empty:
        st.info("No analyst ratings data available.")
        return
    
    st.subheader("Detailed Ratings")
    
    # Prepare data for display
    display_columns = ['ratingDate', 'gradingCompany', 'previousGrade', 'newGrade', 'action']
    available_columns = [col for col in display_columns if col in df_ratings.columns]
    
    if available_columns:
        display_df = df_ratings[available_columns].copy()
        
        # Format dates
        if 'ratingDate' in display_df.columns:
            display_df['ratingDate'] = pd.to_datetime(display_df['ratingDate']).dt.strftime('%Y-%m-%d')
        
        st.dataframe(display_df, use_container_width=True)
    else:
        st.info("Rating data format not recognized.")
    
    # Show rating distribution
    if 'newGrade' in df_ratings.columns and len(df_ratings) > 0:
        st.subheader("Rating Distribution")
        rating_counts = df_ratings['newGrade'].value_counts()
        st.bar_chart(rating_counts)

def render_consensus_section(consensus_data):
    """Render consensus data summary."""
    if not consensus_data:
        st.info("No consensus data.")
        return
    
    # Get the first (and typically only) consensus record
    consensus = consensus_data[0] if consensus_data else {}
    
    # Display consensus metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Strong Buy", consensus.get("strongBuy", 0))
    with col2:
        st.metric("Buy", consensus.get("buy", 0))
    with col3:
        st.metric("Hold", consensus.get("hold", 0))
    with col4:
        st.metric("Sell", consensus.get("sell", 0))
    
    # Additional consensus details
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Strong Sell", consensus.get("strongSell", 0))
        st.metric("Total Analysts", consensus.get("totalAnalysts", 0))
    with col2:
        st.metric("Consensus Score", consensus.get("consensusScore", 0))
        st.metric("Price Target", f"${consensus.get('priceTarget', 0):.2f}" if consensus.get('priceTarget') else "N/A")
    
    # Consensus trend if available
    if consensus.get("trend"):
        st.subheader("Consensus Trend")
        st.write(consensus["trend"])

if __name__ == "__main__":
    main()