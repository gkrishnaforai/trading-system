"""
Signal Analysis Display Component
Shows detailed signal analysis with market context and confidence metrics
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any, Optional

def safe_float(value, default=0):
    """Safely convert value to float, handling percentage strings"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove percentage signs and other non-numeric characters
        cleaned = value.replace('%', '').replace('$', '').replace(',', '').strip()
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

def display_signal_analysis(symbol: str, signal_data: Dict[str, Any], show_header: bool = True, show_debug: bool = False):
    """
    Display comprehensive signal analysis in a reusable format
    
    Args:
        symbol: Stock symbol being analyzed
        signal_data: Complete signal data from API
        show_header: Whether to show the main header
        show_debug: Whether to show debug information
    """
    
    if not signal_data or signal_data.get('error'):
        st.error(f"No analysis data available for {symbol}")
        if signal_data and signal_data.get('error'):
            st.error(f"Error: {signal_data['error']}")
        return
    
    # Extract signal components
    signal = signal_data.get("signal", {})
    
    # Handle case where signal might be a string instead of dict
    if isinstance(signal, str):
        st.error(f"Signal data format error: Expected dict, got string")
        st.error(f"Signal value: {signal}")
        st.error(f"Signal data keys: {list(signal_data.keys())}")
        st.error(f"Full signal_data structure:")
        st.json(signal_data)
        return
    market_data = signal_data.get("market_data", {})
    analysis = signal_data.get("analysis", {})
    engine = signal_data.get("engine", {})
    
    # 🎨 Enhanced Signal Display with Direction - FIXED
    signal_value = signal.get("signal", "hold").upper()
    confidence = signal.get("confidence", 0.0)
    
    # Get actual trend direction from metadata
    metadata = signal.get('metadata', {})
    actual_trend = metadata.get('trend_direction', 'unknown')
    
    # Direction-based color mapping - UPDATED WITH NEW SIGNAL TYPES
    signal_config = {
        "BUY": {
            "emoji": "🟢",
            "color": "#00C851",
            "bg_color": "#E8F5E8",
            "direction": "BULLISH 📈",  # Buy signals are inherently bullish
            "action": "BUY OPPORTUNITY",
            "trend_arrow": "↗️",
            "description": "Stock poised for upward movement"
        },
        "ADD": {
            "emoji": "🟢📈",
            "color": "#00C851",
            "bg_color": "#E8F5E8",
            "direction": "STRONG BULLISH 🚀",  # Add to existing position
            "action": "ADD TO POSITION",
            "trend_arrow": "📈",
            "description": "Scale into winning position (trend continuation)"
        },
        "SELL": {
            "emoji": "🔴",
            "color": "#FF4444",
            "bg_color": "#FFEBEE",
            "direction": f"{actual_trend.upper()} 📈" if actual_trend == "bullish" else "BEARISH 📉" if actual_trend == "bearish" else "NEUTRAL ➡️",
            "action": "RISK MANAGEMENT",
            "trend_arrow": "📉",
            "description": "Risk reduction in bullish trend (profit taking)" if actual_trend == "bullish" else "Stock showing downward pressure (trend reversal)" if actual_trend == "bearish" else "Risk reduction or exit signal"
        },
        "REDUCE": {
            "emoji": "🟡",
            "color": "#FF8800",
            "bg_color": "#FFF3E0",
            "direction": f"{actual_trend.upper()} 📈" if actual_trend == "bullish" else "BEARISH 📉" if actual_trend == "bearish" else "NEUTRAL ➡️",
            "action": "REDUCE POSITION",
            "trend_arrow": "📉",
            "description": "Take profits in bullish trend (overbought)" if actual_trend == "bullish" else "Reduce exposure in bearish trend (risk management)" if actual_trend == "bearish" else "Take profits or reduce exposure"
        },
        "EXIT": {
            "emoji": "🔴",
            "color": "#CC0000",
            "bg_color": "#FFCCCC",
            "direction": f"{actual_trend.upper()} 📈" if actual_trend == "bullish" else "BEARISH 📉" if actual_trend == "bearish" else "NEUTRAL ➡️",
            "action": "EXIT POSITION",
            "trend_arrow": "📉",
            "description": "Exit bullish position (high volatility risk)" if actual_trend == "bullish" else "Exit bearish position (trend reversal confirmed)" if actual_trend == "bearish" else "Exit due to high risk conditions"
        },
        "HOLD": {
            "emoji": "🟡" if actual_trend == "neutral" else "🟡🟢" if actual_trend == "bullish" else "🟡🔴",
            "color": "#FF8800" if actual_trend == "neutral" else "#FFA500" if actual_trend == "bullish" else "#FF6B35",
            "bg_color": "#FFF3E0" if actual_trend == "neutral" else "#FFF8E1" if actual_trend == "bullish" else "#FFEBEE",
            "direction": f"{actual_trend.upper()} 📈" if actual_trend == "bullish" else "BEARISH 📉" if actual_trend == "bearish" else "NEUTRAL ➡️",
            "action": "WAIT & WATCH",
            "trend_arrow": "➡️",
            "description": "No clear directional bias" if actual_trend == "neutral" else "Hold bullish position (monitor for exit)" if actual_trend == "bullish" else "Hold in bearish trend (cautious stance)"
        }
    }
    
    config = signal_config.get(signal_value, {
        "emoji": "⚪", "color": "#999", "bg_color": "#F5F5F5",
        "direction": "UNKNOWN ❓", "action": "ANALYZING",
        "trend_arrow": "❓", "description": "Signal unclear"
    })
    
    # 🎨 Main Signal Card
    if show_header:
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
            <h1 style="color: {config['color']}; margin: 0; font-size: 2.5em;">{signal_value}</h1>
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
    
    # Quick metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        price = safe_float(market_data.get('price', 0))
        recent_change = safe_float(analysis.get('recent_change', 0))
        st.metric(
            "💰 Current Price",
            f"${price:.2f}",
            delta=f"{recent_change:.2f}%" if analysis.get('recent_change') else None
        )
    
    with col2:
        st.metric(
            "📊 RSI",
            f"{safe_float(market_data.get('rsi', 0)):.1f}",
            delta="Overbought" if safe_float(market_data.get('rsi', 0)) > 70 else "Oversold" if safe_float(market_data.get('rsi', 0)) < 30 else "Neutral"
        )
    
    with col3:
        st.metric(
            "📈 Volume",
            f"{safe_float(market_data.get('volume', 0)):,.0f}",
            delta="High" if safe_float(market_data.get('volume', 0)) > 1000000 else "Normal"
        )
    
    with col4:
        st.metric(
            "⚡ EMA Slope",
            f"{safe_float(analysis.get('ema_slope', 0)):.4f}",
            delta="Bullish" if safe_float(analysis.get('ema_slope', 0)) > 0 else "Bearish"
        )
    
    # NEW: Trend Direction and Risk State Display
    metadata = signal.get('metadata', {})
    trend_direction = metadata.get('trend_direction', 'unknown')
    risk_state = metadata.get('risk_state', 'unknown')
    
    # Trend direction styling
    trend_config = {
        "bullish": {"emoji": "🟢", "color": "#00C851", "label": "BULLISH"},
        "bearish": {"emoji": "🔴", "color": "#FF4444", "label": "BEARISH"},
        "neutral": {"emoji": "🟡", "color": "#FF8800", "label": "NEUTRAL"},
        "unknown": {"emoji": "⚪", "color": "#999", "label": "UNKNOWN"}
    }
    
    # Risk state styling
    risk_config = {
        "high": {"emoji": "🔴", "color": "#FF4444", "label": "HIGH RISK"},
        "elevated": {"emoji": "🟡", "color": "#FF8800", "label": "ELEVATED RISK"},
        "low": {"emoji": "🟢", "color": "#00C851", "label": "LOW RISK"},
        "unknown": {"emoji": "⚪", "color": "#999", "label": "UNKNOWN"}
    }
    
    trend_cfg = trend_config.get(trend_direction, trend_config["unknown"])
    risk_cfg = risk_config.get(risk_state, risk_config["unknown"])
    
    # Display trend and risk info
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div style="
            background: rgba(0, 200, 81, 0.1);
            border: 1px solid {trend_cfg['color']};
            border-radius: 10px;
            padding: 15px;
            text-align: center;
        ">
            <div style="font-size: 1.5em; margin-bottom: 5px;">{trend_cfg['emoji']}</div>
            <div style="color: {trend_cfg['color']}; font-weight: bold;">TREND DIRECTION</div>
            <div style="font-size: 1.2em;">{trend_cfg['label']}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div style="
            background: rgba(255, 136, 0, 0.1);
            border: 1px solid {risk_cfg['color']};
            border-radius: 10px;
            padding: 15px;
            text-align: center;
        ">
            <div style="font-size: 1.5em; margin-bottom: 5px;">{risk_cfg['emoji']}</div>
            <div style="color: {risk_cfg['color']}; font-weight: bold;">RISK STATE</div>
            <div style="font-size: 1.2em;">{risk_cfg['label']}</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.subheader("🎯 Enhanced Signal Analysis")
    
    # Technical Indicators Section
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📊 Technical Indicators")
        
        # Create technical indicators dataframe with interpretations
        # Calculate liquidity metrics
        current_volume = safe_float(market_data.get('volume', 0))
        avg_volume_20d = safe_float(market_data.get('avg_volume_20d', current_volume))
        volume_ratio = current_volume / avg_volume_20d if avg_volume_20d > 0 else 1.0
        
        # Determine liquidity state
        if volume_ratio > 1.5:
            liquidity_state = "STRONG"
            liquidity_emoji = "🟢"
        elif volume_ratio > 0.8:
            liquidity_state = "NORMAL"
            liquidity_emoji = "🟡"
        else:
            liquidity_state = "THIN"
            liquidity_emoji = "🔴"
        
        tech_data = {
            'Indicator': ['RSI', 'MACD', 'MACD Signal', 'MACD Crossover', 'SMA 20', 'SMA 50', 'EMA 20', 'Volume', 'Liquidity'],
            'Value': [
                f"{market_data.get('rsi', 0):.2f}",
                f"{market_data.get('macd', 0):.4f}",
                f"{market_data.get('macd_signal', 0):.4f}",
                f"{'Accelerating 🚀' if safe_float(market_data.get('macd', 0)) > safe_float(market_data.get('macd_signal', 0)) else 'Decelerating 📉'}",
                f"${market_data.get('sma_20', 0):.2f}",
                f"${market_data.get('sma_50', 0):.2f}",
                f"${market_data.get('ema_20', 0):.2f}",
                f"{market_data.get('volume', 0):,}",
                f"{liquidity_emoji} {liquidity_state} ({volume_ratio:.1f}x)"
            ],
            'Status': [
                "🔴 Overbought" if safe_float(market_data.get('rsi', 0)) > 70 else "🟢 Oversold" if safe_float(market_data.get('rsi', 0)) < 30 else "🟡 Neutral",
                "🟢 Bullish" if safe_float(market_data.get('macd', 0)) > 0 else "🔴 Bearish",  
                "🟢 Bullish" if safe_float(market_data.get('macd_signal', 0)) > 0 else "🔴 Bearish",  
                "🟢 Bullish" if safe_float(market_data.get('macd', 0)) > safe_float(market_data.get('macd_signal', 0)) else "🔴 Bearish",
                "🟢 Above" if safe_float(market_data.get('price', 0)) > safe_float(market_data.get('sma_20', 0)) else "🔴 Below",
                "🟢 Above" if safe_float(market_data.get('price', 0)) > safe_float(market_data.get('sma_50', 0)) else "🔴 Below",
                "🟢 Above" if safe_float(market_data.get('price', 0)) > safe_float(market_data.get('ema_20', 0)) else "🔴 Below",
                "🟢 High" if safe_float(market_data.get('volume', 0)) > 1000000 else "🟡 Normal",
                f"{liquidity_emoji} {liquidity_state}"
            ],
            'Meaning': [
                # RSI interpretation
                ("profit-taking signal" if safe_float(market_data.get('rsi', 0)) > 70 else 
                 "buying opportunity" if safe_float(market_data.get('rsi', 0)) < 30 else 
                 "neutral momentum"),
                
                # MACD interpretation
                "positive momentum" if safe_float(market_data.get('macd', 0)) > 0 else "negative momentum",
                
                # MACD Signal interpretation
                "positive momentum" if safe_float(market_data.get('macd_signal', 0)) > 0 else "negative momentum",
                
                # MACD Crossover interpretation
                ("momentum strengthening 🚀" if safe_float(market_data.get('macd', 0)) > safe_float(market_data.get('macd_signal', 0)) else 
                 "momentum weakening 📉"),
                
                # SMA 20 interpretation
                (f"above SMA20 (${market_data.get('sma_20', 0):.2f})" if safe_float(market_data.get('price', 0)) > safe_float(market_data.get('sma_20', 0)) else 
                 f"below SMA20 (${market_data.get('sma_20', 0):.2f})"),
                
                # SMA 50 interpretation
                (f"above SMA50 (${market_data.get('sma_50', 0):.2f})" if safe_float(market_data.get('price', 0)) > safe_float(market_data.get('sma_50', 0)) else 
                 f"below SMA50 (${market_data.get('sma_50', 0):.2f})"),
                
                # EMA 20 interpretation
                (f"above EMA20 (${market_data.get('ema_20', 0):.2f})" if safe_float(market_data.get('price', 0)) > safe_float(market_data.get('ema_20', 0)) else 
                 f"below EMA20 (${market_data.get('ema_20', 0):.2f})"),
                
                # Volume interpretation
                ("high conviction" if safe_float(market_data.get('volume', 0)) > 1000000 else "normal volume"),
                
                # Liquidity interpretation
                (f"high conviction trading" if liquidity_state == "STRONG" else 
                 f"normal liquidity" if liquidity_state == "NORMAL" else 
                 f"low liquidity - avoid noise")
            ]
        }
        
        df_tech = pd.DataFrame(tech_data)
        st.dataframe(df_tech, use_container_width=True, hide_index=True)
        
        # Add comprehensive trend summary
        st.markdown("#### 📈 Overall Trend Assessment")
        
        # Calculate overall trend score
        price = safe_float(market_data.get('price', 0))
        sma20 = safe_float(market_data.get('sma_20', 0))
        sma50 = safe_float(market_data.get('sma_50', 0))
        ema20 = safe_float(market_data.get('ema_20', 0))
        rsi = safe_float(market_data.get('rsi', 0))
        macd = safe_float(market_data.get('macd', 0))
        macd_signal = safe_float(market_data.get('macd_signal', 0))
        volume = safe_float(market_data.get('volume', 0))
        
        # Trend components
        trend_signals = []
        
        # Price vs MAs
        if price > sma20 and price > sma50 and price > ema20:
            trend_signals.append("🟢 Price above all MAs (strong uptrend)")
        elif price > sma50:
            trend_signals.append("🟡 Price above SMA50 (moderate uptrend)")
        else:
            trend_signals.append("🔴 Price below key MAs (downtrend)")
        
        # RSI condition
        if rsi > 70:
            trend_signals.append("🔴 Overbought (profit-taking zone)")
        elif rsi < 30:
            trend_signals.append("🟢 Oversold (buying opportunity)")
        else:
            trend_signals.append("🟡 RSI neutral (balanced momentum)")
        
        # MACD condition
        if macd > macd_signal and macd > 0:
            trend_signals.append("🟢 MACD bullish acceleration 🚀")
        elif macd > 0:
            trend_signals.append("🟡 MACD positive but weakening")
        else:
            trend_signals.append("🔴 MACD bearish momentum")
        
        # Volume condition
        if volume > 1000000:
            trend_signals.append("🟢 High volume conviction")
        else:
            trend_signals.append("🟡 Normal volume")
        
        # Liquidity condition (NEW)
        if liquidity_state == "STRONG":
            trend_signals.append(f"🟢 Strong liquidity (high conviction trading)")
        elif liquidity_state == "NORMAL":
            trend_signals.append(f"🟡 Normal liquidity (adequate trading)")
        else:
            trend_signals.append(f"🔴 Thin liquidity (avoid noise - high risk)")
        
        # Display trend summary
        for trend_signal in trend_signals:
            st.markdown(f"• {trend_signal}")
        
        # Overall recommendation
        st.markdown("**Overall Assessment:**")
        bullish_count = sum(1 for s in trend_signals if "🟢" in s)
        bearish_count = sum(1 for s in trend_signals if "🔴" in s)
        
        # Liquidity impact on overall assessment
        if liquidity_state == "THIN":
            st.markdown("🔴 **CAUTION** - Thin liquidity increases risk")
        elif liquidity_state == "STRONG":
            st.markdown("🟢 **HIGH CONVICTION** - Strong liquidity supports signals")
        
        if bullish_count >= bearish_count + 2:
            st.markdown("🟢 **STRONG BULLISH** - Multiple confirming signals")
        elif bullish_count > bearish_count:
            st.markdown("🟡 **MODERATELY BULLISH** - Slight bullish bias")
        elif bearish_count > bullish_count + 1:
            st.markdown("🔴 **BEARISH** - Risk management advised")
        else:
            st.markdown("🟡 **NEUTRAL** - Mixed signals, wait for clarity")
    
    with col2:
        st.markdown("#### 🧠 Signal Reasoning")
        
        reasoning = signal.get('reasoning', [])
        if reasoning:
            for i, reason in enumerate(reasoning, 1):
                st.write(f"**{i}.** {reason}")
        else:
            st.write("No detailed reasoning available")
        
        # Signal metadata
        st.markdown("#### 📋 Signal Metadata")
        metadata = signal.get('metadata', {})
        
        metadata_items = [
            ("Engine Type", engine.get('engine_type', 'Unknown')),
            ("Strategy", engine.get('engine_type', 'Unknown')),
            ("Data Source", signal.get('data_source', 'Unknown')),
            ("Fear/Greed State", metadata.get('fear_greed_state', 'Unknown')),
            ("Recovery Detected", "✅ Yes" if metadata.get('recovery_detected') else "❌ No"),
            ("VIX Level", f"{safe_float(analysis.get('vix_level', 0)):.2f}" if analysis.get('vix_level') else "Unknown")
        ]
        
        for label, value in metadata_items:
            st.write(f"**{label}:** {value}")
    
    # Market Context Section
    st.markdown("---")
    st.subheader("🌍 Market Context")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### 📈 Price Action")
        price_data = {
            'Metric': ['Current Price', 'Recent Change', 'Volatility', 'EMA Slope'],
            'Value': [
                f"${safe_float(market_data.get('price', 0)):.2f}",
                f"{safe_float(analysis.get('recent_change', 0)):.2f}%",
                f"{safe_float(analysis.get('real_volatility', 0)):.2f}%" if analysis.get('real_volatility') else "N/A",
                f"{safe_float(analysis.get('ema_slope', 0)):.4f}"
            ],
            'Interpretation': [
                "Current market price",
                "Recent price movement",
                "Market volatility",
                "Trend direction strength"
            ]
        }
        df_price = pd.DataFrame(price_data)
        st.dataframe(df_price, use_container_width=True, hide_index=True)
    
    with col2:
        st.markdown("#### 🎯 Signal Strength")
        
        # DEBUG: Show what's in signal metadata
        metadata = signal.get('metadata', {})
        st.write(f"DEBUG: Technical Score = {metadata.get('technical_score', 'NOT_FOUND')}")
        st.write(f"DEBUG: Context Score = {metadata.get('context_score', 'NOT_FOUND')}")
        st.write(f"DEBUG: Confidence = {confidence}")
        
        strength_data = {
            'Component': ['Signal Confidence', 'Technical Alignment', 'Market Context', 'Overall Strength'],
            'Score': [
                f"{confidence:.1%}",
                f"{signal.get('metadata', {}).get('technical_score', 0):.1%}" if signal.get('metadata', {}).get('technical_score') is not None else "N/A",
                f"{signal.get('metadata', {}).get('context_score', 0):.1%}" if signal.get('metadata', {}).get('context_score') is not None else "N/A",
                f"{confidence:.1%}"
            ],
            'Status': [
                "🟢 Strong" if confidence > 0.7 else "🟡 Moderate" if confidence > 0.4 else "🔴 Weak",
                "🟢 Aligned" if safe_float(signal.get('metadata', {}).get('technical_score', 0)) > 0.6 else "🟡 Mixed" if safe_float(signal.get('metadata', {}).get('technical_score', 0)) > 0.3 else "🔴 Misaligned",
                "🟢 Favorable" if safe_float(signal.get('metadata', {}).get('context_score', 0)) > 0.6 else "🟡 Neutral" if safe_float(signal.get('metadata', {}).get('context_score', 0)) > 0.3 else "🔴 Unfavorable",
                "🟢 Strong" if confidence > 0.7 else "🟡 Moderate" if confidence > 0.4 else "🔴 Weak"
            ]
        }
        df_strength = pd.DataFrame(strength_data)
        st.dataframe(df_strength, use_container_width=True, hide_index=True)
    
    with col3:
        st.markdown("#### ⚠️ Risk Assessment")
        risk_data = {
            'Risk Factor': ['Volatility Risk', 'Trend Risk', 'Volume Risk', 'Overall Risk'],
            'Level': [
                "🟡 Medium" if safe_float(analysis.get('real_volatility', 0)) > 0.02 else "🟢 Low",
                "🟢 Low" if safe_float(analysis.get('ema_slope', 0)) > 0 else "🔴 High",
                "🟢 Low" if safe_float(market_data.get('volume', 0)) > 500000 else "🔴 High",
                "🟡 Medium"  # Overall assessment
            ],
            'Description': [
                "Based on current volatility",
                "Based on trend direction",
                "Based on liquidity",
                "Combined risk assessment"
            ]
        }
        df_risk = pd.DataFrame(risk_data)
        st.dataframe(df_risk, use_container_width=True, hide_index=True)
    
    # Debug Information (optional)
    if show_debug:
        st.markdown("---")
        st.subheader("🔍 Debug Information")
        
        with st.expander("🔍 Debug: Available Analysis Data"):
            st.write("**Analysis Fields Available:**")
            for key, value in analysis.items():
                st.write(f"• {key}: {value}")
            
            st.write("**Signal Fields Available:**")
            for key, value in signal.items():
                st.write(f"• {key}: {value}")
            
            st.write("**Market Data Fields Available:**")
            for key, value in market_data.items():
                st.write(f"• {key}: {value}")
            
            st.write("**Engine Fields Available:**")
            for key, value in engine.items():
                st.write(f"• {key}: {value}")
        
        # Additional debug info
        with st.expander("🔍 Debug: Data Sources"):
            st.write(f"• Signal data_source: {signal.get('data_source')}")
            st.write(f"• Market data_source: {market_data.get('data_source')}")
            st.write(f"• Analysis data_source: {analysis.get('data_source')}")
            
            # Check volume data
            current_volume = market_data.get('volume', 0)
            st.write(f"• Current volume: {current_volume:,}")
            st.write(f"• Volume data quality: {'Good' if current_volume > 0 else 'Missing'}")
    
    # Action Buttons
    st.markdown("---")
    st.subheader("🚀 Action Center")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("📊 View Chart", type="primary", use_container_width=True):
            st.session_state.show_chart = True
    
    with col2:
        if st.button("🔄 Refresh Analysis", use_container_width=True):
            st.session_state.refresh_analysis = True
    
    with col3:
        if st.button("📋 Export Data", use_container_width=True):
            st.session_state.export_data = True
    
    with col4:
        if st.button("⚙️ Settings", use_container_width=True):
            st.session_state.show_settings = True

def display_no_data_message(symbol: str, error_message: Optional[str] = None):
    """
    Display a standardized 'no data' message
    
    Args:
        symbol: Stock symbol
        error_message: Optional error message to display
    """
    
    st.error(f"No analysis data available for {symbol}")
    
    if error_message:
        st.error(f"Error: {error_message}")
    
    st.info("👆 Try running analysis first to generate signal data")
    
    # Suggested actions
    st.markdown("#### 💡 Suggested Actions:")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Run Analysis", type="primary", use_container_width=True, key=f"run_analysis_{symbol}_{st.session_state.get('page_id', 'default')}"):
            st.session_state.run_analysis = True
    
    with col2:
        if st.button("📊 Load Data", use_container_width=True, key=f"load_data_{symbol}_{st.session_state.get('page_id', 'default')}"):
            st.session_state.load_data = True

def display_analysis_chart(symbol: str, signal_data: Dict[str, Any]):
    """
    Display price chart with technical indicators
    
    Args:
        symbol: Stock symbol
        signal_data: Signal data containing price information
    """
    
    market_data = signal_data.get("market_data", {})
    analysis = signal_data.get("analysis", {})
    
    # Create sample price data for visualization (in real implementation, this would come from API)
    current_price = market_data.get('price', 100)
    sma_20 = market_data.get('sma_20', current_price)
    sma_50 = market_data.get('sma_50', current_price)
    ema_20 = market_data.get('ema_20', current_price)
    
    # Generate sample price series
    dates = pd.date_range(end=datetime.now(), periods=60, freq='D')
    base_price = current_price * 0.95  # Start slightly below current price
    
    # Create realistic price movement
    price_series = []
    for i in range(60):
        noise = (i - 30) * 0.001 * current_price  # Trend
        random_walk = sum([0.01 * current_price * (j % 2 - 0.5) for j in range(i)])  # Random walk
        price = base_price + noise + random_walk
        price_series.append(price)
    
    # Calculate moving averages for the series
    price_df = pd.DataFrame({
        'date': dates,
        'price': price_series
    })
    price_df['sma_20'] = price_df['price'].rolling(window=20, min_periods=1).mean()
    price_df['sma_50'] = price_df['price'].rolling(window=50, min_periods=1).mean()
    price_df['ema_20'] = price_df['price'].ewm(span=20, adjust=False).mean()
    
    # Create the chart
    fig = go.Figure()
    
    # Price line
    fig.add_trace(go.Scatter(
        x=price_df['date'],
        y=price_df['price'],
        mode='lines',
        name='Price',
        line=dict(color='#1f77b4', width=2)
    ))
    
    # SMA 20
    fig.add_trace(go.Scatter(
        x=price_df['date'],
        y=price_df['sma_20'],
        mode='lines',
        name='SMA 20',
        line=dict(color='#ff7f0e', width=1, dash='dash')
    ))
    
    # SMA 50
    fig.add_trace(go.Scatter(
        x=price_df['date'],
        y=price_df['sma_50'],
        mode='lines',
        name='SMA 50',
        line=dict(color='#2ca02c', width=1, dash='dash')
    ))
    
    # EMA 20
    fig.add_trace(go.Scatter(
        x=price_df['date'],
        y=price_df['ema_20'],
        mode='lines',
        name='EMA 20',
        line=dict(color='#d62728', width=1, dash='dot')
    ))
    
    # Update layout
    fig.update_layout(
        title=f'📊 {symbol} Price Chart with Technical Indicators',
        xaxis_title='Date',
        yaxis_title='Price ($)',
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Volume chart (if available)
    if market_data.get('volume', 0) > 0:
        st.markdown("#### 📊 Volume Analysis")
        
        # Generate sample volume data
        volume_data = [market_data.get('volume', 1000000) * (0.5 + (i % 10) / 10) for i in range(60)]
        
        fig_volume = go.Figure()
        fig_volume.add_trace(go.Bar(
            x=price_df['date'],
            y=volume_data,
            name='Volume',
            marker_color='rgba(158,158,158,0.5)'
        ))
        
        fig_volume.update_layout(
            title=f'📊 {symbol} Volume Chart',
            xaxis_title='Date',
            yaxis_title='Volume',
            showlegend=False
        )
        
        st.plotly_chart(fig_volume, use_container_width=True)
