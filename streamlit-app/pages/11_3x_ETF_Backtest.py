"""
3x ETF Backtest Dashboard
Specialized for TQQQ, SOXL, FNGO and other 3x leveraged ETFs
Enhanced Fear/Greed integration with volatility-specific logic
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

setup_page_config("3x ETF Backtest", "🚀")

# 3x ETF specific configurations
ETF_3X_CONFIGS = {
    "TQQQ": {
        "name": "ProShares UltraPro QQQ",
        "description": "3x leveraged Nasdaq 100 ETF",
        "sector": "Technology",
        "volatility_profile": "Very High",
        "optimal_vix_range": "20-35",
        "recovery_patterns": "Strong mean reversion from fear states",
        "engine": "unified_tqqq_swing"
    },
    "SOXL": {
        "name": "ProShares UltraPro Semiconductors",
        "description": "3x leveraged Semiconductor ETF",
        "sector": "Semiconductors",
        "volatility_profile": "Very High",
        "optimal_vix_range": "18-30",
        "recovery_patterns": "Sector-specific fear recovery",
        "engine": "unified_tqqq_swing"  # Using TQQQ engine as proxy
    },
    "FNGO": {
        "name": "MicroSectors FANG+ Innovation 3x Leveraged ETN",
        "description": "3x leveraged FANG+ Innovation ETN",
        "sector": "FANG+ Tech Giants",
        "volatility_profile": "Extreme",
        "optimal_vix_range": "22-40",
        "recovery_patterns": "High volatility mean reversion",
        "engine": "unified_tqqq_swing"  # Using TQQQ engine as proxy
    },
    "LABU": {
        "name": "ProShares UltraPro Healthcare",
        "description": "3x leveraged Healthcare ETF",
        "sector": "Healthcare",
        "volatility_profile": "High",
        "optimal_vix_range": "15-28",
        "recovery_patterns": "Defensive sector recovery",
        "engine": "unified_tqqq_swing"  # Using TQQQ engine as proxy
    },
    "TECL": {
        "name": "ProShares UltraPro Technology",
        "description": "3x leveraged Technology ETF",
        "sector": "Technology",
        "volatility_profile": "Very High",
        "optimal_vix_range": "18-35",
        "recovery_patterns": "Tech sector fear recovery",
        "engine": "unified_tqqq_swing"  # Using TQQQ engine as proxy
    }
}

def get_3x_etf_signal(etf_symbol: str, date: str):
    """Get signal for 3x ETF using TQQQ engine as proxy"""
    try:
        # Use TQQQ engine for all 3x ETFs (they have similar volatility patterns)
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
                etf_config = ETF_3X_CONFIGS[etf_symbol]
                signal_data["etf_info"] = {
                    "name": etf_config["name"],
                    "sector": etf_config["sector"],
                    "volatility_profile": etf_config["volatility_profile"],
                    "engine_used": "TQQQ (proxy)"
                }
                
                return signal_data
            else:
                return {"error": data.get("error", "Unknown error")}
        else:
            return {"error": f"API Error: {response.status_code}"}
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}

def display_3x_etf_analysis(results: dict, etf_symbol: str):
    """Specialized display for 3x ETFs with enhanced Fear/Greed analysis"""
    
    etf_config = ETF_3X_CONFIGS[etf_symbol]
    
    st.subheader(f"🚀 {etf_symbol} 3x ETF Analysis")
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
        st.metric("Engine", etf_config["engine"])
    
    st.divider()
    
    if results["mode"] == "Single Date":
        signal = results["signal"]
        market = results["market_data"]
        performance = results["performance"]
        analysis = results.get("analysis", {})
        
        # 🎯 Enhanced Signal Display for 3x ETFs
        signal_value = signal.get("signal", "N/A")
        confidence = signal.get("confidence", 0)
        
        # 3x ETF specific signal colors
        signal_colors = {
            "buy": ("🟢", "green", "AGGRESSIVE BUY"),
            "sell": ("🔴", "red", "EMERGENCY SELL"), 
            "hold": ("🟡", "orange", "DEFENSIVE HOLD")
        }
        signal_emoji, signal_color, signal_action = signal_colors.get(signal_value.lower(), ("⚪", "gray", "UNKNOWN"))
        
        # Main signal display with 3x ETF emphasis
        st.markdown(f"### {signal_emoji} **{signal_value.upper()}**")
        st.markdown(f"**Action:** {signal_action}")
        st.markdown(f"**Confidence:** {confidence:.1%}")
        st.markdown(f"**Leverage:** 3x (High Risk/High Reward)")
        
        # ⚠️ 3x ETF Risk Warning
        if signal_value == "buy":
            st.warning("⚠️ **3x ETF Warning**: BUY signals require tight stops due to high volatility")
        elif signal_value == "sell":
            st.error("🚨 **3x ETF Alert**: SELL signals indicate extreme market stress - immediate action recommended")
        else:
            st.info("🛡️ **3x ETF Strategy**: HOLD positions during uncertainty - avoid overtrading")
        
        # 🎭 Fear/Greed Panel (Enhanced for 3x ETFs)
        metadata = signal.get("metadata", {})
        fear_greed_state = metadata.get("fear_greed_state", "unknown")
        fear_greed_bias = metadata.get("fear_greed_bias", "unknown")
        recovery_detected = metadata.get("recovery_detected", False)
        
        # 3x ETF specific Fear/Greed interpretations
        fg_colors_3x = {
            "extreme_fear": ("🟣", "purple", "EXTREME FEAR - Capitulation Zone", "🔄 RECOVERY OPPORTUNITY - Small positions only"),
            "fear": ("🔵", "blue", "FEAR - Buying Opportunity", "📈 BULLISH BIAS - Mean reversion setup"), 
            "neutral": ("⚪", "gray", "NEUTRAL - Wait & See", "⏳ HOLD - No clear edge"),
            "greed": ("🟠", "orange", "GREED - Caution Zone", "📉 BEARISH BIAS - Reduce exposure"),
            "extreme_greed": ("🔴", "red", "EXTREME GREED - Euphoria", "🚨 STRONG SELL - Overextended")
        }
        
        fg_emoji, fg_color, fg_description, fg_action = fg_colors_3x.get(fear_greed_state, ("⚪", "gray", "Unknown", "Unknown"))
        
        # Fear/Greed Panel
        st.markdown("### 🎭 Fear/Greed Analysis (3x ETF)")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"### {fg_emoji} **State**")
            st.markdown(f"**{fear_greed_state.replace('_', ' ').title()}**")
            st.caption(fg_description)
            
        with col2:
            bias_colors = {
                "strongly_bullish": ("🟢", "AGGRESSIVE BUY"),
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
                st.caption("BUY-in-Fear Active")
                st.info("⚡ Small position (25-40%)")
            else:
                st.markdown("### 🔄 **Recovery**")
                st.warning("**NOT DETECTED**")
                st.caption("Waiting for setup")
        
        # 3x ETF specific action
        st.markdown(f"**{fg_action}**")
        
        # 🌊 Enhanced Market Context for 3x ETFs
        st.markdown("### 🌊 Market Context (3x ETF Focus)")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            volatility = metadata.get("volatility", analysis.get("real_volatility", 0))
            volatility_float = float(volatility) if volatility else 0.0
            
            # 3x ETF specific volatility thresholds
            if volatility_float > 10:
                vol_color = "🔴"
                vol_status = "EXTREME"
                vol_message = "Danger Zone - Tight stops"
            elif volatility_float > 7:
                vol_color = "🟡"
                vol_status = "HIGH"
                vol_message = "Caution - Reduce size"
            elif volatility_float > 4:
                vol_color = "🟢"
                vol_status = "MODERATE"
                vol_message = "Normal - Proceed"
            else:
                vol_color = "🟢"
                vol_status = "LOW"
                vol_message = "Calm - Opportunity"
                
            st.metric(f"{vol_color} Volatility", f"{volatility_float:.2f}%")
            st.caption(f"{vol_status}: {vol_message}")
            
        with col2:
            vix_level = analysis.get("vix_level", 0)
            vix_float = float(vix_level) if vix_level else 0.0
            
            # 3x ETF specific VIX interpretation
            if vix_float > 35:
                vix_color = "🔴"
                vix_status = "EXTREME FEAR"
                vix_message = "Capitulation - Recovery setup"
            elif vix_float > 25:
                vix_color = "🟡"
                vix_status = "HIGH FEAR"
                vix_message = "Fear environment - Be selective"
            elif vix_float > 18:
                vix_color = "🟢"
                vix_status = "MODERATE"
                vix_message = "Normal volatility"
            else:
                vix_color = "🟢"
                vix_status = "LOW"
                vix_message = "Complacency - Risk"
                
            st.metric(f"{vix_color} VIX", f"{vix_float:.2f}")
            st.caption(f"{vix_status}: {vix_message}")
            
        with col3:
            recent_change = metadata.get("recent_change", analysis.get("recent_change", 0))
            change_float = float(recent_change) if recent_change else 0.0
            
            # 3x ETF specific change interpretation
            if change_float < -5:
                change_color = "🔴"
                change_status = "CRASH"
                change_message = "Panic selling - Recovery possible"
            elif change_float < -2:
                change_color = "🟡"
                change_status = "DECLINE"
                change_message = "Correction - Watch support"
            elif change_float < 0:
                change_color = "🟡"
                change_status = "WEAK"
                change_message = "Distribution - Be cautious"
            else:
                change_color = "🟢"
                change_status = "RISING"
                change_message = "Accumulation - Follow trend"
                
            st.metric(f"{change_color} Change", f"{change_float:.2f}%")
            st.caption(f"{change_status}: {change_message}")
            
        with col4:
            rsi = metadata.get("rsi", market.get("rsi", 50))
            rsi_float = float(rsi) if rsi else 50.0
            
            # 3x ETF specific RSI interpretation
            if rsi_float < 25:
                rsi_color = "🔴"
                rsi_status = "EXTREME OVERSOLD"
                rsi_message = "Capitulation - Recovery setup"
            elif rsi_float < 35:
                rsi_color = "🟡"
                rsi_status = "OVERSOLD"
                rsi_message = "Fear zone - Buying opportunity"
            elif rsi_float > 75:
                rsi_color = "🔴"
                rsi_status = "EXTREME OVERBOUGHT"
                rsi_message = "Euphoria - Exit time"
            elif rsi_float > 65:
                rsi_color = "🟡"
                rsi_status = "OVERBOUGHT"
                rsi_message = "Greed - Reduce exposure"
            else:
                rsi_color = "🟢"
                rsi_status = "NEUTRAL"
                rsi_message = "Balanced - No edge"
                
            st.metric(f"{rsi_color} RSI", f"{rsi_float:.1f}")
            st.caption(f"{rsi_status}: {rsi_message}")
        
        # 📝 3x ETF Specific Signal Reasoning
        if signal.get("reasoning"):
            st.markdown("### 📝 3x ETF Signal Reasoning")
            
            # Enhanced categorization for 3x ETFs
            ladder_reasons = []
            fear_greed_reasons = []
            volatility_reasons = []
            action_items = []
            
            for reason in signal.get("reasoning", []):
                if "Signal Ladder" in reason:
                    ladder_reasons.append(reason)
                elif "WAIT FOR" in reason or "→" in reason:
                    action_items.append(reason)
                elif "Fear" in reason or "Recovery" in reason or "VIX" in reason:
                    fear_greed_reasons.append(reason)
                elif "volatility" in reason or "Volatility" in reason:
                    volatility_reasons.append(reason)
                else:
                    fear_greed_reasons.append(reason)
            
            # Display Signal Ladder (Most Important for 3x ETFs)
            if ladder_reasons:
                st.markdown("**🎯 Signal Ladder (3x ETF Priority):**")
                for reason in ladder_reasons:
                    st.success(f"🚀 {reason}")
            
            # Display Volatility Analysis
            if volatility_reasons:
                st.markdown("**🌊 Volatility Analysis (Critical for 3x ETFs):**")
                for reason in volatility_reasons:
                    st.error(f"⚡ {reason}")
            
            # Display Fear/Greed Factors
            if fear_greed_reasons:
                st.markdown("**🧠 Fear/Greed Factors:**")
                for reason in fear_greed_reasons:
                    st.warning(f"🎪 {reason}")
            
            # Display Action Items
            if action_items:
                st.markdown("**⚡ Immediate Actions:**")
                for reason in action_items:
                    st.info(f"📋 {reason}")
        
        # 💡 3x ETF Specific Actionable Insights
        st.markdown("### 💡 3x ETF Trading Strategy")
        
        insights = []
        
        # Fear/Greed state specific 3x ETF strategies
        if fear_greed_state == "extreme_fear":
            insights.extend([
                "🎯 **Extreme Fear Strategy**: SMALL BUY (25-40%) - Recovery setup",
                "⚡ **Entry**: On volatility flattening or green close confirmation",
                "🛡️ **Risk**: Tight stops (2-3%) - 3x leverage amplifies losses",
                "🎯 **Target**: Quick exit (5-8%) - Don't get greedy in fear"
            ])
        elif fear_greed_state == "fear":
            insights.extend([
                "📈 **Fear Strategy**: BUY or HOLD - Mean reversion opportunity",
                "⏳ **Patience**: Wait for volatility to stabilize before adding",
                "🔄 **Recovery**: Watch for stabilization patterns",
                "📊 **Size**: Normal position (50-75%) - Fear environment"
            ])
        elif fear_greed_state == "neutral":
            insights.extend([
                "⏸️ **Neutral Strategy**: HOLD - No clear edge",
                "📊 **Analysis**: Wait for Fear/Greed signals",
                "🛡️ **Risk**: Maintain defensive posture",
                "⏳ **Timing**: Better entries in fear or greed extremes"
            ])
        elif fear_greed_state == "greed":
            insights.extend([
                "📉 **Greed Strategy**: SELL or REDUCE - Take profits",
                "⚠️ **Warning**: Greed leads to corrections in 3x ETFs",
                "🛡️ **Risk**: Reduce exposure to 25-50%",
                "🎯 **Target**: Lock in profits - Don't give back gains"
            ])
        elif fear_greed_state == "extreme_greed":
            insights.extend([
                "🚨 **Extreme Greed**: EMERGENCY SELL - Capitulation coming",
                "⚡ **Exit**: Immediate or very tight stops",
                "🔄 **Preparation**: Get ready for fear buying opportunity",
                "🛡️ **Cash**: Move to cash - Preserve capital"
            ])
        
        # Signal-specific 3x ETF insights
        if signal_value == "buy":
            insights.extend([
                "🟢 **BUY Signal**: Confirm recovery is underway",
                "📊 **Volume**: Check for buying volume confirmation",
                "⚡ **Speed**: 3x ETFs move fast - be ready to exit",
                "🛡️ **Stops**: Set immediately - No exceptions"
            ])
        elif signal_value == "sell":
            insights.extend([
                "🔴 **SELL Signal**: Market stress detected",
                "🚨 **Urgency**: 3x ETFs decline 3x faster",
                "💰 **Protect**: Capital preservation over profit",
                "🔄 **Preparation**: Next buying opportunity in fear"
            ])
        else:  # HOLD
            insights.extend([
                "🟡 **HOLD Signal**: Market uncertainty",
                "⏳ **Patience**: Wait for clear setup",
                "📊 **Monitor**: Fear/Greed state changes",
                "🛡️ **Defense**: Avoid overtrading"
            ])
        
        # Display insights with priority
        for i, insight in enumerate(insights[:8]):  # Show top 8 insights
            if i < 3:  # Top 3 are most important
                st.error(insight) if "🚨" in insight or "🔴" in insight else st.warning(insight) if "⚡" in insight else st.success(insight)
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
    """Main 3x ETF dashboard function"""
    
    # Render sidebar
    subscription_level = render_sidebar()
    
    st.title("🚀 3x ETF Backtest Dashboard")
    st.markdown("*Specialized Fear/Greed integration for 3x leveraged ETFs*")
    
    # 3x ETF Selection
    st.markdown("### 🎯 Select 3x ETF")
    
    # Create ETF selection grid
    etf_cols = st.columns(3)
    etf_list = list(ETF_3X_CONFIGS.keys())
    
    selected_etf = None
    for i, etf_symbol in enumerate(etf_list):
        col = etf_cols[i % 3]
        etf_config = ETF_3X_CONFIGS[etf_symbol]
        
        with col:
            if st.button(f"**{etf_symbol}**\n{etf_config['sector']}", key=f"etf_{etf_symbol}", use_container_width=True):
                st.session_state.selected_etf = etf_symbol
    
    # Initialize selected ETF
    if "selected_etf" not in st.session_state:
        st.session_state.selected_etf = "TQQQ"
    
    selected_etf = st.session_state.selected_etf
    etf_config = ETF_3X_CONFIGS[selected_etf]
    
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
        st.metric("Optimal VIX", etf_config["optimal_vix_range"])
    
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
            key="etf_backtest_mode"
        )
        
        if backtest_mode == "Single Date":
            selected_date = st.date_input(
                "Select Date:",
                datetime.now().date() - timedelta(days=1),
                key="etf_single_date"
            )
        elif backtest_mode == "Date Range":
            start_date = st.date_input(
                "Start Date:",
                datetime.now().date() - timedelta(days=30),
                key="etf_start_date"
            )
            end_date = st.date_input(
                "End Date:",
                datetime.now().date() - timedelta(days=1),
                key="etf_end_date"
            )
    
    with col2:
        st.markdown("### ⚠️ 3x ETF Risk Warning")
        st.error("""
        **🚨 HIGH RISK WARNING**
        
        - **3x Daily Leverage**: Compounds losses rapidly
        - **Volatility Decay**: Long-term underperformance in volatile markets
        - **Not for Long-Term Holding**: Designed for short-term trading
        - **Require Active Management**: Daily monitoring essential
        """)
    
    # Run Backtest Button
    if st.button(f"🚀 Run {selected_etf} 3x ETF Analysis", type="primary", use_container_width=True):
        with st.spinner(f"Analyzing {selected_etf} with Fear/Greed integration..."):
            
            if backtest_mode == "Single Date":
                date_str = selected_date.strftime("%Y-%m-%d")
                results = get_3x_etf_signal(selected_etf, date_str)
                
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
                    
                    display_3x_etf_analysis(display_results, selected_etf)
            
            elif backtest_mode == "Date Range":
                st.info("📊 Date range backtest coming soon for 3x ETFs...")
                
            elif backtest_mode == "Quick Test Week":
                st.info("⚡ Quick test week coming soon for 3x ETFs...")
    
    # ETF Configuration Details
    with st.expander(f"🔧 {selected_etf} Configuration"):
        st.json(etf_config)

if __name__ == "__main__":
    main()
