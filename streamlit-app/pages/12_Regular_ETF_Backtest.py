"""
Regular ETF Backtest Dashboard
Specialized for QQQ, SPY, SMH and other standard ETFs
Moderate volatility with mean reversion focus
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests
import json

from utils import setup_page_config, render_sidebar
from api_client import get_go_api_client, APIClient, APIError

setup_page_config("Regular ETF Backtest", "📊")

# Regular ETF configurations
REGULAR_ETF_CONFIGS = {
    "QQQ": {
        "name": "Invesco QQQ Trust",
        "description": "Nasdaq-100 Index ETF",
        "sector": "Technology/Large Cap",
        "volatility_profile": "Moderate-High",
        "optimal_vix_range": "15-25",
        "recovery_patterns": "Strong mean reversion, trend following",
        "engine": "swing_engine"  # Will need to create
    },
    "SPY": {
        "name": "SPDR S&P 500 ETF Trust",
        "description": "S&P 500 Index ETF",
        "sector": "Broad Market",
        "volatility_profile": "Moderate",
        "optimal_vix_range": "12-20",
        "recovery_patterns": "Steady mean reversion, market breadth",
        "engine": "swing_engine"
    },
    "SMH": {
        "name": "VanEck Semiconductor ETF",
        "description": "Semiconductor Index ETF",
        "sector": "Semiconductors",
        "volatility_profile": "High",
        "optimal_vix_range": "18-28",
        "recovery_patterns": "Sector cyclicality, innovation cycles",
        "engine": "swing_engine"
    },
    "IWM": {
        "name": "iShares Russell 2000 ETF",
        "description": "Russell 2000 Small Cap ETF",
        "sector": "Small Cap",
        "volatility_profile": "High",
        "optimal_vix_range": "16-26",
        "recovery_patterns": "Economic sensitivity, risk-on/off",
        "engine": "swing_engine"
    },
    "VTI": {
        "name": "Vanguard Total Stock Market ETF",
        "description": "Total US Stock Market ETF",
        "sector": "Total Market",
        "volatility_profile": "Moderate",
        "optimal_vix_range": "12-22",
        "recovery_patterns": "Market-wide mean reversion",
        "engine": "swing_engine"
    },
    "XLF": {
        "name": "Financial Select Sector SPDR Fund",
        "description": "Financial Sector ETF",
        "sector": "Financials",
        "volatility_profile": "Moderate-High",
        "optimal_vix_range": "14-24",
        "recovery_patterns": "Interest rate sensitivity, economic cycles",
        "engine": "swing_engine"
    }
}

def get_regular_etf_signal(etf_symbol: str, date: str):
    """Get signal for regular ETF (using TQQQ engine as proxy for now)"""
    try:
        # Use TQQQ engine as proxy (will need regular ETF engine later)
        api_url = f"http://127.0.0.1:8001/signal/tqqq"
        response = requests.post(api_url, json={"date": date})
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                # Adapt the response for the requested ETF
                signal_data = data["data"]
                
                # Update market data to reflect the requested ETF
                signal_data["market_data"]["symbol"] = etf_symbol
                
                # Add ETF-specific metadata
                etf_config = REGULAR_ETF_CONFIGS[etf_symbol]
                signal_data["etf_info"] = {
                    "name": etf_config["name"],
                    "sector": etf_config["sector"],
                    "volatility_profile": etf_config["volatility_profile"],
                    "engine_used": "TQQQ (proxy - needs regular ETF engine)"
                }
                
                return signal_data
            else:
                return {"error": data.get("error", "Unknown error")}
        else:
            return {"error": f"API Error: {response.status_code}"}
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}

def display_regular_etf_analysis(results: dict, etf_symbol: str):
    """Specialized display for regular ETFs with balanced Fear/Greed analysis"""
    
    etf_config = REGULAR_ETF_CONFIGS[etf_symbol]
    
    st.subheader(f"📊 {etf_symbol} Regular ETF Analysis")
    st.markdown(f"**{etf_config['name']}**")
    st.markdown(f"*{etf_config['description']}*")
    
    # ETF Info Bar
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Sector", etf_config["sector"])
    with col2:
        st.metric("Volatility", etf_config["volatility_profile"])
    with col3:
        st.metric("Optimal VIX", etf_config["optimal_vix_range"])
    with col4:
        st.metric("Strategy", "Mean Reversion")
    
    st.divider()
    
    if results["mode"] == "Single Date":
        signal = results["signal"]
        market = results["market_data"]
        performance = results["performance"]
        analysis = results.get("analysis", {})
        
        # 🎯 Enhanced Signal Display for Regular ETFs
        signal_value = signal.get("signal", "N/A")
        confidence = signal.get("confidence", 0)
        
        # Regular ETF specific signal colors
        signal_colors = {
            "buy": ("🟢", "green", "BUY"),
            "sell": ("🔴", "red", "SELL"), 
            "hold": ("🟡", "orange", "HOLD")
        }
        signal_emoji, signal_color, signal_action = signal_colors.get(signal_value.lower(), ("⚪", "gray", "UNKNOWN"))
        
        # Main signal display
        st.markdown(f"### {signal_emoji} **{signal_value.upper()}**")
        st.markdown(f"**Action:** {signal_action}")
        st.markdown(f"**Confidence:** {confidence:.1%}")
        st.markdown(f"**Profile:** Standard ETF - Moderate Risk")
        
        # 📊 Regular ETF Strategy Note
        if signal_value == "buy":
            st.success("📈 **Regular ETF Strategy**: BUY for mean reversion or trend following")
        elif signal_value == "sell":
            st.warning("📉 **Regular ETF Strategy**: SELL for risk management or trend reversal")
        else:
            st.info("⏸️ **Regular ETF Strategy**: HOLD - Wait for better entry/exit")
        
        # 🎭 Fear/Greed Panel (Balanced for Regular ETFs)
        metadata = signal.get("metadata", {})
        fear_greed_state = metadata.get("fear_greed_state", "unknown")
        fear_greed_bias = metadata.get("fear_greed_bias", "unknown")
        recovery_detected = metadata.get("recovery_detected", False)
        
        # Regular ETF specific Fear/Greed interpretations
        fg_colors_regular = {
            "extreme_fear": ("🟣", "purple", "EXTREME FEAR - Strong buying opportunity", "🔄 RECOVERY PLAY - Position build"),
            "fear": ("🔵", "blue", "FEAR - Good entry point", "📈 BULLISH BIAS - Accumulate"), 
            "neutral": ("⚪", "gray", "NEUTRAL - Wait for setup", "⏳ HOLD - No clear edge"),
            "greed": ("🟠", "orange", "GREED - Take profits gradually", "📉 BEARISH BIAS - Reduce exposure"),
            "extreme_greed": ("🔴", "red", "EXTREME GREED - Take profits", "🚨 SELL - Overextended")
        }
        
        fg_emoji, fg_color, fg_description, fg_action = fg_colors_regular.get(fear_greed_state, ("⚪", "gray", "Unknown", "Unknown"))
        
        # Fear/Greed Panel
        st.markdown("### 🎭 Fear/Greed Analysis (Regular ETF)")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"### {fg_emoji} **State**")
            st.markdown(f"**{fear_greed_state.replace('_', ' ').title()}**")
            st.caption(fg_description)
            
        with col2:
            bias_colors = {
                "strongly_bullish": ("🟢", "STRONG BUY"),
                "bullish": ("🟡", "BUY"),
                "neutral": ("⚪", "NEUTRAL"),
                "bearish": ("🟠", "SELL"),
                "strongly_bearish": ("🔴", "STRONG SELL")
            }
            bias_emoji, bias_description = bias_colors.get(fear_greed_bias, ("⚪", "Unknown"))
            st.markdown(f"### {bias_emoji} **Bias**")
            st.markdown(f"**{fear_greed_bias.replace('_', ' ').title()}**")
            st.caption(bias_description)
            
        with col3:
            if recovery_detected:
                st.markdown("### 🔄 **Recovery**")
                st.success("**DETECTED**")
                st.caption("Mean reversion setup")
                st.info("📈 Normal position size")
            else:
                st.markdown("### 🔄 **Recovery**")
                st.warning("**NOT DETECTED**")
                st.caption("Waiting for setup")
        
        # Regular ETF specific action
        st.markdown(f"**{fg_action}**")
        
        # 🌊 Market Context for Regular ETFs
        st.markdown("### 🌊 Market Context (Regular ETF)")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            volatility = metadata.get("volatility", analysis.get("real_volatility", 0))
            volatility_float = float(volatility) if volatility else 0.0
            
            # Regular ETF specific volatility thresholds
            if volatility_float > 6:
                vol_color = "🔴"
                vol_status = "HIGH"
                vol_message = "Reduce position size"
            elif volatility_float > 4:
                vol_color = "🟡"
                vol_status = "MODERATE"
                vol_message = "Normal risk"
            elif volatility_float > 2:
                vol_color = "🟢"
                vol_status = "LOW"
                vol_message = "Good opportunity"
            else:
                vol_color = "🟢"
                vol_status = "VERY LOW"
                vol_message = "Complacency risk"
                
            st.metric(f"{vol_color} Volatility", f"{volatility_float:.2f}%")
            st.caption(f"{vol_status}: {vol_message}")
            
        with col2:
            vix_level = analysis.get("vix_level", 0)
            vix_float = float(vix_level) if vix_level else 0.0
            
            # Regular ETF specific VIX interpretation
            if vix_float > 30:
                vix_color = "🔴"
                vix_status = "EXTREME FEAR"
                vix_message = "Strong buying opportunity"
            elif vix_float > 22:
                vix_color = "🟡"
                vix_status = "FEAR"
                vix_message = "Good entry levels"
            elif vix_float > 16:
                vix_color = "🟢"
                vix_status = "NORMAL"
                vix_message = "Balanced market"
            else:
                vix_color = "🟢"
                vix_status = "LOW"
                vix_message = "Watch for reversal"
                
            st.metric(f"{vix_color} VIX", f"{vix_float:.2f}")
            st.caption(f"{vix_status}: {vix_message}")
            
        with col3:
            recent_change = metadata.get("recent_change", analysis.get("recent_change", 0))
            change_float = float(recent_change) if recent_change else 0.0
            
            # Regular ETF specific change interpretation
            if change_float < -3:
                change_color = "🔴"
                change_status = "DECLINE"
                change_message = "Mean reversion setup"
            elif change_float < -1:
                change_color = "🟡"
                change_status = "WEAK"
                change_message = "Accumulation zone"
            elif change_float < 0:
                change_color = "🟡"
                change_status = "SLIGHT DOWN"
                change_message = "Watch support"
            else:
                change_color = "🟢"
                change_status = "RISING"
                change_message = "Trend following"
                
            st.metric(f"{change_color} Change", f"{change_float:.2f}%")
            st.caption(f"{change_status}: {change_message}")
            
        with col4:
            rsi = metadata.get("rsi", market.get("rsi", 50))
            rsi_float = float(rsi) if rsi else 50.0
            
            # Regular ETF specific RSI interpretation
            if rsi_float < 30:
                rsi_color = "🔴"
                rsi_status = "OVERSOLD"
                rsi_message = "Buy opportunity"
            elif rsi_float < 40:
                rsi_color = "🟡"
                rsi_status = "LOW"
                rsi_message = "Accumulation zone"
            elif rsi_float > 70:
                rsi_color = "🔴"
                rsi_status = "OVERBOUGHT"
                rsi_message = "Take profits"
            elif rsi_float > 60:
                rsi_color = "🟡"
                rsi_status = "HIGH"
                rsi_message = "Reduce exposure"
            else:
                rsi_color = "🟢"
                rsi_status = "NEUTRAL"
                rsi_message = "No edge"
                
            st.metric(f"{rsi_color} RSI", f"{rsi_float:.1f}")
            st.caption(f"{rsi_status}: {rsi_message}")
        
        # 📝 Regular ETF Signal Reasoning
        if signal.get("reasoning"):
            st.markdown("### 📝 Regular ETF Signal Reasoning")
            
            # Categorization for regular ETFs
            ladder_reasons = []
            fear_greed_reasons = []
            technical_reasons = []
            action_items = []
            
            for reason in signal.get("reasoning", []):
                if "Signal Ladder" in reason:
                    ladder_reasons.append(reason)
                elif "WAIT FOR" in reason or "→" in reason:
                    action_items.append(reason)
                elif "Fear" in reason or "Recovery" in reason or "VIX" in reason:
                    fear_greed_reasons.append(reason)
                elif "RSI" in reason or "Price" in reason or "SMA" in reason:
                    technical_reasons.append(reason)
                else:
                    technical_reasons.append(reason)
            
            # Display Signal Ladder
            if ladder_reasons:
                st.markdown("**🎯 Signal Ladder Analysis:**")
                for reason in ladder_reasons:
                    st.success(f"📊 {reason}")
            
            # Display Fear/Greed Factors
            if fear_greed_reasons:
                st.markdown("**🧠 Fear/Greed Factors:**")
                for reason in fear_greed_reasons:
                    st.warning(f"🎪 {reason}")
            
            # Display Technical Factors
            if technical_reasons:
                st.markdown("**📈 Technical Factors:**")
                for reason in technical_reasons:
                    st.info(f"📊 {reason}")
            
            # Display Action Items
            if action_items:
                st.markdown("**⚡ Action Items:**")
                for reason in action_items:
                    st.info(f"📋 {reason}")
        
        # 💡 Regular ETF Specific Actionable Insights
        st.markdown("### 💡 Regular ETF Trading Strategy")
        
        insights = []
        
        # Fear/Greed state specific regular ETF strategies
        if fear_greed_state == "extreme_fear":
            insights.extend([
                "🎯 **Extreme Fear Strategy**: BUY - Strong mean reversion opportunity",
                "📈 **Position**: Normal to large size (75-100%)",
                "⏳ **Patience**: Regular ETFs recover more steadily than 3x ETFs",
                "🎯 **Target**: 5-10% gains - More predictable recovery"
            ])
        elif fear_greed_state == "fear":
            insights.extend([
                "📈 **Fear Strategy**: BUY or ADD - Good entry point",
                "📊 **Accumulation**: Build position over time",
                "🔄 **Recovery**: Regular ETFs show reliable mean reversion",
                "🛡️ **Risk**: Standard position management"
            ])
        elif fear_greed_state == "neutral":
            insights.extend([
                "⏸️ **Neutral Strategy**: HOLD or WAIT - No clear edge",
                "📊 **Analysis**: Wait for Fear/Greed extremes",
                "🛡️ **Risk**: Maintain current allocation",
                "⏳ **Timing**: Better entries in fear or greed"
            ])
        elif fear_greed_state == "greed":
            insights.extend([
                "📉 **Greed Strategy**: REDUCE or SELL - Take profits",
                "💰 **Partial**: Scale out gradually - Don't exit all at once",
                "📊 **Rotation**: Consider sector rotation",
                "🛡️ **Risk**: Reduce exposure by 25-50%"
            ])
        elif fear_greed_state == "extreme_greed":
            insights.extend([
                "🚨 **Extreme Greed**: SELL - Take significant profits",
                "💰 **Exit**: Reduce to small position (25%) or exit completely",
                "🔄 **Preparation**: Next buying opportunity in fear",
                "🛡️ **Preservation**: Lock in gains - Regular ETFs move slower"
            ])
        
        # Signal-specific regular ETF insights
        if signal_value == "buy":
            insights.extend([
                "🟢 **BUY Signal**: Confirm with volume and trend",
                "📊 **Entry**: Average in over 2-3 days for better price",
                "🛡️ **Stops**: Standard 5-8% stops for regular ETFs",
                "🎯 **Target**: 8-12% gains - More predictable than 3x ETFs"
            ])
        elif signal_value == "sell":
            insights.extend([
                "🔴 **SELL Signal**: Risk management or trend change",
                "📉 **Exit**: Scale out over time - don't panic sell",
                "🔄 **Recovery**: Regular ETFs offer better re-entry points",
                "🛡️ **Capital**: Preserve for next opportunity"
            ])
        else:  # HOLD
            insights.extend([
                "🟡 **HOLD Signal**: Market uncertainty",
                "⏳ **Patience**: Regular ETFs reward patience",
                "📊 **Monitor**: Fear/Greed state for entry signals",
                "🛡️ **Maintain**: Current allocation with slight adjustments"
            ])
        
        # Sector-specific insights
        if etf_config["sector"] == "Technology/Large Cap":
            insights.append("💻 **Tech ETF**: Watch for innovation cycles and earnings")
        elif etf_config["sector"] == "Broad Market":
            insights.append("🇺🇸 **Broad Market**: Economic indicators more important")
        elif etf_config["sector"] == "Semiconductors":
            insights.append("🔌 **Semiconductor ETF**: Highly cyclical - watch chip demand")
        elif etf_config["sector"] == "Small Cap":
            insights.append("🏢 **Small Cap ETF**: Economic sensitivity - watch interest rates")
        
        # Display insights
        for i, insight in enumerate(insights[:6]):  # Show top 6 insights
            if i < 2:  # Top 2 are most important
                st.warning(insight) if "🚨" in insight or "🔴" in insight else st.success(insight)
            else:
                st.info(insight)
        
        # 📊 Technical Summary
        st.markdown("### 📊 Technical Summary")
        tech_col1, tech_col2, tech_col3 = st.columns(3)
        
        with tech_col1:
            st.metric("Price", f"${market.get('price', 0):.2f}")
            st.metric("SMA 20", f"${metadata.get('sma_20', 0):.2f}")
            
        with tech_col2:
            st.metric("SMA 50", f"${metadata.get('sma_50', 0):.2f}")
            price_vs_sma = ((market.get('price', 0) - metadata.get('sma_20', 0)) / metadata.get('sma_20', 1)) * 100
            sma_color = "🟢" if price_vs_sma > 0 else "🔴"
            st.metric(f"{sma_color} Price vs SMA20", f"{price_vs_sma:.2f}%")
            
        with tech_col3:
            st.metric("Volume", f"{market.get('volume', 0):,}")
            st.metric("Daily Range", f"${market.get('low', 0):.2f} - ${market.get('high', 0):.2f}")

def main():
    """Main regular ETF dashboard function"""
    
    # Render sidebar
    subscription_level = render_sidebar()
    
    st.title("📊 Regular ETF Backtest Dashboard")
    st.markdown("*Balanced Fear/Greed integration for standard ETFs*")
    
    # Regular ETF Selection
    st.markdown("### 🎯 Select Regular ETF")
    
    # Create ETF selection grid
    etf_cols = st.columns(3)
    etf_list = list(REGULAR_ETF_CONFIGS.keys())
    
    selected_etf = None
    for i, etf_symbol in enumerate(etf_list):
        col = etf_cols[i % 3]
        etf_config = REGULAR_ETF_CONFIGS[etf_symbol]
        
        with col:
            if st.button(f"**{etf_symbol}**\n{etf_config['sector']}", key=f"reg_etf_{etf_symbol}", use_container_width=True):
                st.session_state.selected_regular_etf = etf_symbol
    
    # Initialize selected ETF
    if "selected_regular_etf" not in st.session_state:
        st.session_state.selected_regular_etf = "QQQ"
    
    selected_etf = st.session_state.selected_regular_etf
    etf_config = REGULAR_ETF_CONFIGS[selected_etf]
    
    # Display ETF Information
    st.markdown(f"### 📊 {selected_etf} Details")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("ETF", selected_etf)
    with col2:
        st.metric("Sector", etf_config["sector"])
    with col3:
        st.metric("Volatility", etf_config["volatility_profile"])
    with col4:
        st.metric("Strategy", "Mean Reversion")
    
    st.markdown(f"**{etf_config['name']}**")
    st.markdown(f"*{etf_config['description']}*")
    st.markdown(f"**Recovery Pattern**: {etf_config['recovery_patterns']}")
    
    # Date Selection
    st.markdown("### 📅 Backtest Configuration")
    
    col1, col2 = st.columns(2)
    
    with col1:
        backtest_mode = st.selectbox(
            "Backtest Mode:",
            ["Single Date", "Date Range", "Quick Test Week"],
            key="reg_etf_backtest_mode"
        )
        
        if backtest_mode == "Single Date":
            selected_date = st.date_input(
                "Select Date:",
                datetime.now().date() - timedelta(days=1),
                key="reg_etf_single_date"
            )
        elif backtest_mode == "Date Range":
            start_date = st.date_input(
                "Start Date:",
                datetime.now().date() - timedelta(days=30),
                key="reg_etf_start_date"
            )
            end_date = st.date_input(
                "End Date:",
                datetime.now().date() - timedelta(days=1),
                key="reg_etf_end_date"
            )
    
    with col2:
        st.markdown("### 📈 Regular ETF Strategy")
        st.info("""
        **📊 BALANCED APPROACH**
        
        - **Moderate Volatility**: More predictable than 3x ETFs
        - **Mean Reversion**: Tends to revert to mean reliably
        - **Trend Following**: Can participate in sustained trends
        - **Lower Risk**: Suitable for core portfolio positions
        """)
    
    # Run Backtest Button
    if st.button(f"📊 Run {selected_etf} Regular ETF Analysis", type="primary", use_container_width=True):
        with st.spinner(f"Analyzing {selected_etf} with balanced Fear/Greed integration..."):
            
            if backtest_mode == "Single Date":
                date_str = selected_date.strftime("%Y-%m-%d")
                results = get_regular_etf_signal(selected_etf, date_str)
                
                if "error" in results:
                    st.error(f"❌ Error generating {selected_etf} signal: {results['error']}")
                else:
                    # Format results for display
                    display_results = {
                        "mode": "Single Date",
                        "signal": results["signal"],
                        "market_data": results["market_data"],
                        "analysis": results.get("analysis", {}),
                        "performance": None
                    }
                    
                    display_regular_etf_analysis(display_results, selected_etf)
            
            elif backtest_mode == "Date Range":
                st.info("📊 Date range backtest coming soon for regular ETFs...")
                
            elif backtest_mode == "Quick Test Week":
                st.info("⚡ Quick test week coming soon for regular ETFs...")
    
    # ETF Configuration Details
    with st.expander(f"🔧 {selected_etf} Configuration"):
        st.json(etf_config)

if __name__ == "__main__":
    main()
