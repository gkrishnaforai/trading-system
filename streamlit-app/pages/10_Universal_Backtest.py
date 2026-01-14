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
    """Enhanced display for universal backtest with Fear/Greed integration and clear direction insights"""
    
    # 🎨 Create visually appealing header with stock direction
    st.markdown(f"""
    <div style="
        background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        text-align: center;
        color: white;
    ">
        <h2 style="margin: 0; font-size: 2.5em;">📈 {asset_symbol}</h2>
        <p style="margin: 5px 0; font-size: 1.2em;">{asset_category.replace('_', ' ').title()} Analysis</p>
        <p style="margin: 0; opacity: 0.8;">Real-time Signal & Direction Analysis</p>
    </div>
    """, unsafe_allow_html=True)
    
    if results["mode"] == "Single Date":
        signal = results["signal"]
        market = results["market_data"]
        performance = results["performance"]
        analysis = results.get("analysis", {})
        
        # 🎯 Enhanced Signal Display with Clear Direction
        signal_value = signal.get("signal", "N/A")
        confidence = signal.get("confidence", 0)
        
        # Direction-based color mapping
        signal_config = {
            "buy": {
                "emoji": "🟢",
                "color": "#00C851",
                "bg_color": "#E8F5E8",
                "direction": "BULLISH 📈",
                "action": "BUY OPPORTUNITY",
                "trend_arrow": "↗️",
                "description": "Stock poised for upward movement"
            },
            "sell": {
                "emoji": "🔴",
                "color": "#FF4444",
                "bg_color": "#FFEBEE",
                "direction": "BEARISH 📉",
                "action": "SELL WARNING",
                "trend_arrow": "↘️",
                "description": "Stock showing downward pressure"
            },
            "hold": {
                "emoji": "🟡",
                "color": "#FF8800",
                "bg_color": "#FFF3E0",
                "direction": "NEUTRAL ➡️",
                "action": "WAIT & WATCH",
                "trend_arrow": "➡️",
                "description": "Stock in consolidation phase"
            }
        }
        
        config = signal_config.get(signal_value.lower(), {
            "emoji": "⚪", "color": "#999", "bg_color": "#F5F5F5",
            "direction": "UNKNOWN ❓", "action": "ANALYZING",
            "trend_arrow": "❓", "description": "Signal unclear"
        })
        
        # 🎨 Main Signal Card with Direction
        st.markdown(f"""
        <div style="
            background: {config['bg_color']};
            border: 2px solid {config['color']};
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            margin-bottom: 25px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        ">
            <div style="font-size: 4em; margin-bottom: 10px;">{config['emoji']}</div>
            <h1 style="color: {config['color']}; margin: 0; font-size: 2.5em;">{signal_value.upper()}</h1>
            <div style="font-size: 1.5em; margin: 10px 0; color: {config['color']}; font-weight: bold;">
                {config['direction']} {config['trend_arrow']}
            </div>
            <div style="font-size: 1.2em; margin: 5px 0;">{config['action']}</div>
            <div style="font-size: 1em; opacity: 0.8; margin-top: 10px;">{config['description']}</div>
            <div style="margin-top: 15px; font-size: 1.1em;">
                <strong>Confidence:</strong> {confidence:.1%}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 📊 Quick Direction Summary
        col1, col2, col3 = st.columns(3)
        
        with col1:
            price = market.get('price', 0)
            st.metric(
                f"{config['trend_arrow']} Current Price",
                f"${price:.2f}",
                delta=None
            )
        
        with col2:
            change = market.get('change', 0)
            change_pct = market.get('change_percent', 0)
            change_color = "normal" if change >= 0 else "inverse"
            st.metric(
                "📈 Daily Change",
                f"{change:+.2f}",
                f"{change_pct:+.2f}%",
                delta_color=change_color
            )
        
        with col3:
            volume = market.get('volume', 0)
            st.metric(
                "📊 Volume",
                f"{volume:,.0f}",
                "Trading Activity"
            )
        
        # 🎭 Fear/Greed State Panel (Enhanced for direction)
        metadata = signal.get("metadata", {})
        fear_greed_state = metadata.get("fear_greed_state", "unknown")
        fear_greed_bias = metadata.get("fear_greed_bias", "unknown")
        recovery_detected = metadata.get("recovery_detected", False)
        
        # Enhanced Fear/Greed mapping with direction insights
        fg_config = {
            "extreme_fear": {
                "emoji": "🟣", "color": "#6A1B9A", "bg_color": "#EDE7F6",
                "market_state": "CAPITULATION", "direction_bias": "BOTTOMING PROCESS 🔄",
                "opportunity": "RECOVERY SETUP", "risk": "HIGH REWARD POTENTIAL"
            },
            "fear": {
                "emoji": "🔵", "color": "#1976D2", "bg_color": "#E3F2FD",
                "market_state": "ACCUMULATION", "direction_bias": "BUYING OPPORTUNITY 📈",
                "opportunity": "MEAN REVERSION", "risk": "MODERATE RISK"
            },
            "neutral": {
                "emoji": "⚪", "color": "#757575", "bg_color": "#FAFAFA",
                "market_state": "CONSOLIDATION", "direction_bias": "WAIT FOR BREAKOUT ⏳",
                "opportunity": "PATTERN FORMATION", "risk": "LOW ACTIVITY"
            },
            "greed": {
                "emoji": "🟠", "color": "#F57C00", "bg_color": "#FFF3E0",
                "market_state": "DISTRIBUTION", "direction_bias": "SELLING PRESSURE 📉",
                "opportunity": "PROFIT TAKING", "risk": "CORRECTION RISK"
            },
            "extreme_greed": {
                "emoji": "🔴", "color": "#D32F2F", "bg_color": "#FFEBEE",
                "market_state": "EUPHORIA", "direction_bias": "TOP FORMATION 🚨",
                "opportunity": "SHORT OPPORTUNITY", "risk": "HIGH CORRECTION RISK"
            }
        }
        
        fg_info = fg_config.get(fear_greed_state, fg_config["neutral"])
        
        # 🎨 Fear/Greed Panel
        st.markdown(f"""
        <div style="
            background: {fg_info['bg_color']};
            border-left: 5px solid {fg_info['color']};
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
        ">
            <h3 style="color: {fg_info['color']}; margin-top: 0;">🎭 Market Psychology</h3>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-top: 15px;">
                <div style="text-align: center;">
                    <div style="font-size: 2em;">{fg_info['emoji']}</div>
                    <div style="font-weight: bold; color: {fg_info['color']};">{fg_info['market_state']}</div>
                    <div style="font-size: 0.9em; opacity: 0.8;">{fear_greed_state.replace('_', ' ').title()}</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 1.5em; margin-bottom: 5px;">🧭</div>
                    <div style="font-weight: bold;">{fg_info['direction_bias']}</div>
                    <div style="font-size: 0.9em; opacity: 0.8;">Market Direction</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 1.5em; margin-bottom: 5px;">🎯</div>
                    <div style="font-weight: bold;">{fg_info['opportunity']}</div>
                    <div style="font-size: 0.9em; opacity: 0.8;">Trading Opportunity</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 🌊 Market Context with Direction Indicators
        st.markdown("### 🌊 Market Context & Direction Indicators")
        
        # Get market metrics
        volatility = metadata.get("volatility", analysis.get("real_volatility", 0))
        vix_level = analysis.get("vix_level", 0)
        recent_change = metadata.get("recent_change", analysis.get("recent_change", 0))
        rsi = metadata.get("rsi", market.get("rsi", 50))
        
        # Convert to floats
        vol_float = float(volatility) if volatility else 0.0
        vix_float = float(vix_level) if vix_level else 0.0
        change_float = float(recent_change) if recent_change else 0.0
        rsi_float = float(rsi) if rsi else 50.0
        
        # Create direction indicators
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            vol_status = "🔴 Extreme" if vol_float > 8 else "🟡 High" if vol_float > 5 else "🟢 Normal"
            vol_direction = "⚡ HIGH VOLATILITY" if vol_float > 5 else "😌 CALM MARKET"
            st.metric(f"🌊 Volatility", f"{vol_float:.2f}%", vol_status)
            st.caption(f"Direction: {vol_direction}")
        
        with col2:
            vix_status = "🔴 Fear" if vix_float > 30 else "🟡 Alert" if vix_float > 20 else "🟢 Calm"
            vix_direction = "😱 FEAR PREMIUM" if vix_float > 25 else "😌 LOW FEAR"
            st.metric(f"😱 VIX", f"{vix_float:.2f}", vix_status)
            st.caption(f"Direction: {vix_direction}")
        
        with col3:
            change_status = "🔴 Declining" if change_float < -2 else "🟡 Weak" if change_float < 0 else "🟢 Rising"
            change_direction = "📉 DOWNTREND" if change_float < -2 else "📈 UPTREND" if change_float > 2 else "➡️ SIDEWAYS"
            st.metric(f"📈 3-Day Change", f"{change_float:.2f}%", change_status)
            st.caption(f"Direction: {change_direction}")
        
        with col4:
            rsi_status = "🔴 Oversold" if rsi_float < 30 else "🟡 Overbought" if rsi_float > 70 else "🟢 Neutral"
            rsi_direction = "🔄 RECOVERY SETUP" if rsi_float < 30 else "⚠️ CORRECTION RISK" if rsi_float > 70 else "😌 BALANCED"
            st.metric(f"📊 RSI", f"{rsi_float:.1f}", rsi_status)
            st.caption(f"Direction: {rsi_direction}")
        
        # 🎯 Overall Direction Summary
        st.markdown("### 🎯 Overall Direction Analysis")
        
        # Calculate overall direction score
        direction_score = 0
        direction_factors = []
        
        # Signal contribution
        if signal_value == "buy":
            direction_score += 3
            direction_factors.append("🟢 Strong BUY signal")
        elif signal_value == "sell":
            direction_score -= 3
            direction_factors.append("🔴 Strong SELL signal")
        
        # Fear/Greed contribution
        if fear_greed_state in ["fear", "extreme_fear"]:
            direction_score += 2
            direction_factors.append("🟢 Fear environment (buying opportunity)")
        elif fear_greed_state in ["greed", "extreme_greed"]:
            direction_score -= 2
            direction_factors.append("🔴 Greed environment (selling pressure)")
        
        # Technical contribution
        if change_float > 2:
            direction_score += 1
            direction_factors.append("📈 Positive momentum")
        elif change_float < -2:
            direction_score -= 1
            direction_factors.append("📉 Negative momentum")
        
        # Determine overall direction
        if direction_score >= 3:
            overall_direction = "🟢 STRONGLY BULLISH"
            direction_color = "#00C851"
            direction_bg = "#E8F5E8"
            direction_emoji = "🚀"
            direction_advice = "Strong upward momentum - Consider buying"
        elif direction_score >= 1:
            overall_direction = "🟡 MODERATELY BULLISH"
            direction_color = "#FF8800"
            direction_bg = "#FFF3E0"
            direction_emoji = "📈"
            direction_advice = "Upward bias - Cautious buying"
        elif direction_score <= -3:
            overall_direction = "🔴 STRONGLY BEARISH"
            direction_color = "#FF4444"
            direction_bg = "#FFEBEE"
            direction_emoji = "📉"
            direction_advice = "Strong downward pressure - Consider selling"
        elif direction_score <= -1:
            overall_direction = "🟠 MODERATELY BEARISH"
            direction_color = "#FF6B35"
            direction_bg = "#FFE5D9"
            direction_emoji = "⚠️"
            direction_advice = "Downward bias - Cautious selling"
        else:
            overall_direction = "⚪ NEUTRAL"
            direction_color = "#757575"
            direction_bg = "#F5F5F5"
            direction_emoji = "➡️"
            direction_advice = "No clear direction - Wait for setup"
        
        # Display overall direction
        st.markdown(f"""
        <div style="
            background: {direction_bg};
            border: 2px solid {direction_color};
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            margin: 20px 0;
        ">
            <div style="font-size: 2em; margin-bottom: 10px;">{direction_emoji}</div>
            <h2 style="color: {direction_color}; margin: 0;">{overall_direction}</h2>
            <p style="margin: 10px 0; font-style: italic;">{direction_advice}</p>
            <div style="margin-top: 15px; font-size: 0.9em; opacity: 0.8;">
                <strong>Key Factors:</strong> {', '.join(direction_factors)}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 💡 Actionable Insights with Clear Direction
        st.markdown("### 💡 Trading Strategy & Direction")
        
        insights = []
        
        # Asset-category specific strategies
        if asset_category == "3x_ETFs":
            if direction_score >= 1:
                insights.extend([
                    "🚀 **3x ETF Bullish**: High volatility - Use tight stops (2-3%)",
                    "⚡ **Leverage Risk**: 3x exposure amplifies both gains AND losses",
                    "📈 **Entry Strategy**: Wait for volatility confirmation before adding"
                ])
            else:
                insights.extend([
                    "🛡️ **3x ETF Bearish**: High risk - Consider reducing exposure",
                    "⚠️ **Volatility Alert**: 3x ETFs decline 3x faster than market",
                    "💰 **Capital Protection**: Preserve capital for next opportunity"
                ])
        
        # Fear/Greed specific strategies
        if fear_greed_state in ["fear", "extreme_fear"] and direction_score >= 1:
            insights.append("🎯 **Fear Buying**: Accumulate positions in fear for mean reversion")
        elif fear_greed_state in ["greed", "extreme_greed"] and direction_score <= -1:
            insights.append("🚨 **Greed Selling**: Take profits in greed - corrections coming")
        
        # Display insights with priority
        for i, insight in enumerate(insights[:6]):
            if i < 2:  # Top 2 most important
                st.error(insight) if "🚨" in insight or "🔴" in insight else st.warning(insight) if "⚠️" in insight else st.success(insight)
            else:
                st.info(insight)
        
        # 📊 Technical Summary with Direction
        st.markdown("### 📊 Technical Analysis Summary")
        
        tech_col1, tech_col2, tech_col3 = st.columns(3)
        
        with tech_col1:
            st.metric("💰 Current Price", f"${market.get('price', 0):.2f}")
            st.metric("📊 SMA 20", f"${metadata.get('sma_20', 0):.2f}")
            
        with tech_col2:
            st.metric("📈 SMA 50", f"${metadata.get('sma_50', 0):.2f}")
            price_vs_sma = ((market.get('price', 0) - metadata.get('sma_20', 0)) / metadata.get('sma_20', 1)) * 100
            sma_trend = "🟢 Above" if price_vs_sma > 0 else "🔴 Below"
            st.metric(f"{sma_trend} SMA20", f"{price_vs_sma:.2f}%")
            
        with tech_col3:
            st.metric("📊 Volume", f"{market.get('volume', 0):,}")
            high_low = f"${market.get('low', 0):.2f} - ${market.get('high', 0):.2f}"
            st.metric("📈 Daily Range", high_low)

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
                max_value=datetime.now().date(),  # Allow current day, block future dates
                key="single_date"
            )
        elif backtest_mode == "Date Range":
            start_date = st.date_input(
                "Start Date:",
                datetime.now().date() - timedelta(days=30),
                max_value=datetime.now().date(),  # Allow current day, block future dates
                key="start_date"
            )
            end_date = st.date_input(
                "End Date:",
                datetime.now().date() - timedelta(days=1),
                max_value=datetime.now().date(),  # Allow current day, block future dates
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
