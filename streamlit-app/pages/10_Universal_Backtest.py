"""
Universal Backtest Dashboard
Supports 3x ETFs, Regular ETFs, and Individual Stocks with Fear/Greed integration
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import json

# Import centralized API configuration
from api_config import api_config

from utils import setup_page_config, render_sidebar
from api_client import get_go_api_client, APIClient, APIError

setup_page_config("Universal Backtest", "🔄")

# Asset configurations
ASSET_CONFIGS = {
    "3x_ETFs": {
        "assets": ["TQQQ", "SOXL", "FNGO", "LABU", "TECL"],
        "description": "3x Leveraged ETFs - High volatility, enhanced Fear/Greed logic",
        "volatility_threshold": 8.0,
        "rsi_oversold": 48,
        "risk_management": "Aggressive volatility detection",
        "engine_type": "unified_tqqq_swing"  # Can be extended for other 3x ETFs
    },
    "Regular_ETFs": {
        "assets": ["QQQ", "SPY", "SMH", "IWM", "VTI"],
        "description": "Standard ETFs - Moderate volatility, mean reversion focus",
        "volatility_threshold": 5.0,
        "rsi_oversold": 35,
        "risk_management": "Standard risk management",
        "engine_type": "swing_engine"  # Will need to create this
    },
    "Individual_Stocks": {
        "assets": ["NVDA", "GOOGL", "AAPL", "TSLA", "MSFT", "AMD"],
        "description": "Individual Stocks - Earnings-aware, company-specific risk",
        "volatility_threshold": 6.0,
        "rsi_oversold": 30,
        "risk_management": "Stock-specific risk management",
        "engine_type": "stock_swing_engine"  # Will need to create this
    }
}

def get_3x_etf_signal(etf_symbol: str, date: str):
    """Get signal for 3x ETF using universal API"""
    try:
        # Use centralized API configuration
        api_url = api_config.get_universal_signal_url()
        payload = {
            "symbol": etf_symbol,
            "date": date,
            "asset_type": "3x_etf"
        }
        
        response = requests.post(api_url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                signal_data = data["data"]
                
                # Add ETF-specific metadata
                etf_config = ETF_3X_CONFIGS[etf_symbol]
                signal_data["etf_info"] = {
                    "name": etf_config["name"],
                    "sector": etf_config["sector"],
                    "volatility_profile": etf_config["volatility_profile"],
                    "engine_used": "Universal 3x ETF Engine"
                }
                
                return signal_data
            else:
                return {"error": data.get("error", "Unknown error")}
        else:
            return {"error": f"API Error: {response.status_code} - {response.text}"}
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


def get_universal_signal(asset_symbol: str, date: str, asset_category: str):
    """Get signal for any asset using universal API"""
    try:
        # Use centralized API configuration
        api_url = api_config.get_universal_signal_url()
        payload = {
            "symbol": asset_symbol,
            "date": date,
            "asset_type": asset_category
        }
        
        response = requests.post(api_url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return data["data"]
            else:
                return {"error": data.get("error", "Unknown error")}
        else:
            return {"error": f"API Error: {response.status_code} - {response.text}"}
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}

def display_enhanced_backtest_results(results: dict, asset_symbol: str, asset_category: str):
    """Enhanced display for universal backtest with Fear/Greed integration"""
    
    st.subheader(f"📊 {asset_symbol} Signal Analysis ({asset_category.replace('_', ' ').title()})")
    
    if results["mode"] == "Single Date":
        signal = results["signal"]
        market = results["market_data"]
        performance = results["performance"]
        analysis = results.get("analysis", {})
        
        # 🎯 Signal Summary with Asset-Specific Colors
        signal_value = signal.get("signal", "N/A")
        confidence = signal.get("confidence", 0)
        
        # Enhanced signal color mapping
        signal_colors = {
            "buy": ("🟢", "green"),
            "sell": ("🔴", "red"), 
            "hold": ("🟡", "orange")
        }
        signal_emoji, signal_color = signal_colors.get(signal_value.lower(), ("⚪", "gray"))
        
        # Main signal display
        st.markdown(f"### {signal_emoji} **{signal_value.upper()}**")
        st.markdown(f"**Confidence:** {confidence:.1%}")
        st.markdown(f"**Asset:** {asset_symbol} ({asset_category.replace('_', ' ').title()})")
        
        # 🎭 Fear/Greed State Panel (Same as before)
        metadata = signal.get("metadata", {})
        fear_greed_state = metadata.get("fear_greed_state", "unknown")
        fear_greed_bias = metadata.get("fear_greed_bias", "unknown")
        recovery_detected = metadata.get("recovery_detected", False)
        
        # Enhanced Fear/Greed color mapping with descriptions
        fg_colors = {
            "extreme_fear": ("🟣", "purple", "Extreme Fear - Capitulation"),
            "fear": ("🔵", "blue", "Fear - Buying Opportunity"), 
            "neutral": ("⚪", "gray", "Neutral - Balanced"),
            "greed": ("🟠", "orange", "Greed - Caution"),
            "extreme_greed": ("🔴", "red", "Extreme Greed - Euphoria")
        }
        
        fg_emoji, fg_color, fg_description = fg_colors.get(fear_greed_state, ("⚪", "gray", "Unknown"))
        
        # Bias color mapping
        bias_colors = {
            "strongly_bullish": ("🟢", "Strong Buy"),
            "bullish": ("🟡", "Buy"),
            "neutral": ("⚪", "Neutral"),
            "bearish": ("🟠", "Sell"),
            "strongly_bearish": ("🔴", "Strong Sell")
        }
        bias_emoji, bias_description = bias_colors.get(fear_greed_bias, ("⚪", "Unknown"))
        
        # Fear/Greed Panel
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"### {fg_emoji} **Fear/Greed State**")
            st.markdown(f"**{fear_greed_state.replace('_', ' ').title()}**")
            st.caption(fg_description)
            
        with col2:
            st.markdown(f"### {bias_emoji} **Signal Bias**")
            st.markdown(f"**{fear_greed_bias.replace('_', ' ').title()}**")
            st.caption(bias_description)
            
        with col3:
            if recovery_detected:
                st.markdown("### 🔄 **Recovery**")
                st.success("**Detected**")
                st.caption("BUY-in-Fear Opportunity")
            else:
                st.markdown("### 🔄 **Recovery**")
                st.warning("**Not Detected**")
                st.caption("Waiting for stabilization")
        
        # 🌊 Market Context Panel (Enhanced)
        st.markdown("### 🌊 Market Context")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            volatility = metadata.get("volatility", analysis.get("real_volatility", 0))
            volatility_float = float(volatility) if volatility else 0.0
            vol_color = "🔴" if volatility_float > 8 else "🟡" if volatility_float > 5 else "🟢"
            vol_status = "High" if volatility_float > 8 else "Moderate" if volatility_float > 5 else "Low"
            st.metric(f"{vol_color} Volatility", f"{volatility_float:.2f}%")
            st.caption(f"Status: {vol_status}")
            
        with col2:
            vix_level = analysis.get("vix_level", 0)
            vix_float = float(vix_level) if vix_level else 0.0
            vix_color = "🔴" if vix_float > 30 else "🟡" if vix_float > 20 else "🟢"
            vix_status = "Extreme Fear" if vix_float > 30 else "Fear" if vix_float > 20 else "Calm"
            st.metric(f"{vix_color} VIX", f"{vix_float:.2f}")
            st.caption(f"Status: {vix_status}")
            
        with col3:
            recent_change = metadata.get("recent_change", analysis.get("recent_change", 0))
            change_float = float(recent_change) if recent_change else 0.0
            change_color = "🔴" if change_float < -3 else "🟡" if change_float < 0 else "🟢"
            change_status = "Strong Decline" if change_float < -3 else "Decline" if change_float < 0 else "Rise"
            st.metric(f"{change_color} 3-Day Change", f"{change_float:.2f}%")
            st.caption(f"Status: {change_status}")
            
        with col4:
            rsi = metadata.get("rsi", market.get("rsi", 50))
            rsi_float = float(rsi) if rsi else 50.0
            rsi_color = "🔴" if rsi_float < 30 else "🟡" if rsi_float > 70 else "🟢"
            rsi_status = "Oversold" if rsi_float < 30 else "Overbought" if rsi_float > 70 else "Neutral"
            st.metric(f"{rsi_color} RSI", f"{rsi_float:.1f}")
            st.caption(f"Status: {rsi_status}")
        
        # 🎭 Market Regime Panel
        regime = metadata.get("regime", "unknown")
        
        # Enhanced regime information
        regime_insights = {
            "volatility_expansion": {
                "icon": "🌊",
                "title": "Volatility Expansion",
                "description": "High volatility environment - risk management priority",
                "action": "Watch for recovery signals, avoid selling into panic"
            },
            "mean_reversion": {
                "icon": "🔄", 
                "title": "Mean Reversion",
                "description": "Price reverting to mean - pullback opportunities",
                "action": "Look for oversold entries and bounce plays"
            },
            "trend_continuation": {
                "icon": "📈",
                "title": "Trend Continuation", 
                "description": "Strong trend in place - momentum trading",
                "action": "Follow the trend - buy dips, sell rallies"
            },
            "breakout": {
                "icon": "🚀",
                "title": "Breakout",
                "description": "Price breaking key levels - momentum plays",
                "action": "Momentum trading - watch for false breakouts"
            }
        }
        
        regime_info = regime_insights.get(regime, {
            "icon": "❓",
            "title": "Unknown Regime",
            "description": "Regime not identified",
            "action": "Proceed with caution"
        })
        
        st.markdown(f"### {regime_info['icon']} **{regime_info['title']} Regime**")
        st.markdown(f"**Description:** {regime_info['description']}")
        st.markdown(f"**Strategy:** {regime_info['action']}")
        
        # 📝 Enhanced Signal Reasoning with Categories
        if signal.get("reasoning"):
            st.markdown("### 📝 Signal Reasoning")
            
            # Enhanced categorization
            signal_ladder_reasons = []
            fear_greed_reasons = []
            technical_reasons = []
            action_items = []
            
            for reason in signal.get("reasoning", []):
                if "Signal Ladder" in reason:
                    signal_ladder_reasons.append(reason)
                elif "WAIT FOR" in reason or "→" in reason:
                    action_items.append(reason)
                elif "Fear" in reason or "Recovery" in reason or "VIX" in reason or "volatility" in reason:
                    fear_greed_reasons.append(reason)
                elif "RSI" in reason or "Price" in reason or "SMA" in reason:
                    technical_reasons.append(reason)
                else:
                    technical_reasons.append(reason)
            
            # Display Signal Ladder (Most Important)
            if signal_ladder_reasons:
                st.markdown("**🎯 Signal Ladder Analysis:**")
                for reason in signal_ladder_reasons:
                    st.success(f"🎭 {reason}")
            
            # Display Action Items
            if action_items:
                st.markdown("**⚡ Action Items:**")
                for reason in action_items:
                    st.info(f"📋 {reason}")
            
            # Display Fear/Greed Factors
            if fear_greed_reasons:
                st.markdown("**🧠 Fear/Greed Factors:**")
                for reason in fear_greed_reasons:
                    st.warning(f"🎪 {reason}")
            
            # Display Technical Factors
            if technical_reasons:
                st.markdown("**📊 Technical Factors:**")
                for reason in technical_reasons:
                    st.caption(f"📈 {reason}")
        
        # 💡 Asset-Specific Actionable Insights
        st.markdown("### 💡 Actionable Insights")
        
        insights = []
        
        # Asset-category specific insights
        if asset_category == "3x_ETFs":
            if fear_greed_state in ["fear", "extreme_fear"]:
                insights.append("🎯 **3x ETF Strategy**: Extreme volatility - HOLD or very small positions")
                insights.append("⚡ **Leverage Risk**: 3x exposure requires tight risk management")
                insights.append("🛡️ **Volatility Target**: Wait for flattening before considering entries")
        elif asset_category == "Regular_ETFs":
            insights.append("📊 **ETF Strategy**: Standard volatility - normal position sizes")
            insights.append("🔄 **Mean Reversion**: ETFs tend to revert to mean more reliably")
        else:  # Individual Stocks
            insights.append("🏢 **Stock Strategy**: Company-specific factors at play")
            insights.append("📈 **Earnings Awareness**: Watch for earnings dates and news")
        
        # Signal-specific insights based on Fear/Greed state
        if fear_greed_state in ["fear", "extreme_fear"]:
            if signal_value == "hold":
                insights.append("🎯 **Fear Strategy**: HOLD - Don't sell into panic")
                insights.append("⏳ **Wait For**: Volatility flattening or green close")
            elif signal_value == "buy" and recovery_detected:
                insights.append("🔄 **Recovery Play**: Small position for mean-reversion")
        
        # Display insights
        for insight in insights:
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
            st.metric("High", f"${market.get('high', 0):.2f}")
            st.metric("Low", f"${market.get('low', 0):.2f}")

def main():
    """Main dashboard function"""
    
    # Render sidebar
    subscription_level = render_sidebar()
    
    st.title("🔄 Universal Backtest Dashboard")
    st.markdown("*Advanced Fear/Greed integration for multiple asset types*")
    
    # Asset Category Selection
    st.markdown("### 🎯 Select Asset Category")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🚀 3x ETFs", key="3x_etf", use_container_width=True, help="TQQQ, SOXL, FNGO - High volatility"):
            st.session_state.asset_category = "3x_ETFs"
    
    with col2:
        if st.button("📊 Regular ETFs", key="regular_etf", use_container_width=True, help="QQQ, SPY, SMH - Standard volatility"):
            st.session_state.asset_category = "Regular_ETFs"
    
    with col3:
        if st.button("🏢 Individual Stocks", key="stocks", use_container_width=True, help="NVDA, GOOGL, AAPL - Stock-specific"):
            st.session_state.asset_category = "Individual_Stocks"
    
    # Initialize asset category
    if "asset_category" not in st.session_state:
        st.session_state.asset_category = "3x_ETFs"
    
    asset_category = st.session_state.asset_category
    config = ASSET_CONFIGS[asset_category]
    
    # Display category info
    st.markdown(f"### {asset_category.replace('_', ' ').title()}")
    st.markdown(f"*{config['description']}*")
    
    # Asset Selection
    col1, col2 = st.columns([2, 1])
    
    with col1:
        selected_asset = st.selectbox(
            "Select Asset:",
            config["assets"],
            key="selected_asset"
        )
    
    with col2:
        st.metric("Volatility Threshold", f"{config['volatility_threshold']}%")
        st.metric("RSI Oversold", config['rsi_oversold'])
    
    # Date Selection
    st.markdown("### 📅 Select Date Range")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        backtest_mode = st.selectbox(
            "Backtest Mode:",
            ["Single Date", "Date Range", "Quick Test Week"],
            key="backtest_mode"
        )
    
    with col2:
        if backtest_mode == "Single Date":
            selected_date = st.date_input(
                "Select Date:",
                datetime.now().date() - timedelta(days=1),
                key="single_date"
            )
        elif backtest_mode == "Date Range":
            start_date = st.date_input(
                "Start Date:",
                datetime.now().date() - timedelta(days=30),
                key="start_date"
            )
            end_date = st.date_input(
                "End Date:",
                datetime.now().date() - timedelta(days=1),
                key="end_date"
            )
    
    with col3:
        if backtest_mode == "Quick Test Week":
            test_week = st.selectbox(
                "Test Week:",
                ["This Week", "Last Week", "Two Weeks Ago"],
                key="test_week"
            )
    
    # Run Backtest Button
    if st.button(f"🚀 Run {selected_asset} Backtest", type="primary", use_container_width=True):
        with st.spinner(f"Generating {selected_asset} signals..."):
            
            if backtest_mode == "Single Date":
                date_str = selected_date.strftime("%Y-%m-%d")
                results = get_universal_signal(selected_asset, date_str, asset_category)
                
                if "error" in results:
                    st.error(f"❌ Error generating signal: {results['error']}")
                else:
                    # Format results for display
                    display_results = {
                        "mode": "Single Date",
                        "signal": results["signal"],
                        "market_data": results["market_data"],
                        "analysis": results.get("analysis", {}),
                        "performance": None
                    }
                    
                    display_enhanced_backtest_results(display_results, selected_asset, asset_category)
            
            elif backtest_mode == "Date Range":
                st.info("📊 Date range backtest coming soon...")
                # TODO: Implement multi-date backtest
                
            elif backtest_mode == "Quick Test Week":
                st.info("⚡ Quick test week coming soon...")
                # TODO: Implement quick test week
    
    # Asset Configuration Info
    with st.expander(f"🔧 {asset_category.replace('_', ' ').title()} Configuration"):
        st.json(config)

if __name__ == "__main__":
    main()
