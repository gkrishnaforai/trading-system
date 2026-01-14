"""
Growth Quality Display Component

Streamlit component for displaying Early Warning Flags analysis
and Growth Quality signals with institutional-grade visualization.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from typing import Dict, Any, List, Optional
from datetime import date, datetime

from app.api_client import APIClient


def display_early_warning_analysis(symbol: str, analysis_data: Dict[str, Any]):
    """
    Display comprehensive Early Warning Flags analysis
    
    Shows:
    - Overall risk assessment
    - Domain-specific risks
    - Detailed warnings and insights
    - Risk metrics visualization
    """
    
    st.markdown(f"## 🚨 Early Warning Analysis - {symbol}")
    
    # Overall Risk Assessment
    overall_risk = analysis_data.get('overall_risk', 'UNKNOWN')
    domain_risks = analysis_data.get('domain_risks', {})
    
    # Risk level styling
    risk_config = {
        'GREEN': {'emoji': '🟢', 'color': '#22c55e', 'label': 'Growth Intact'},
        'YELLOW': {'emoji': '🟡', 'color': '#f59e0b', 'label': 'Early Stress'},
        'RED': {'emoji': '🔴', 'color': '#ef4444', 'label': 'Structural Breakdown'},
        'UNKNOWN': {'emoji': '⚪', 'color': '#6b7280', 'label': 'Unknown'}
    }
    
    config = risk_config.get(overall_risk, risk_config['UNKNOWN'])
    
    # Header with risk assessment
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {config['color']}22 0%, {config['color']}11 100%); 
                padding: 2rem; border-radius: 15px; border-left: 5px solid {config['color']}; 
                margin-bottom: 2rem;">
        <div style="display: flex; align-items: center; justify-content: space-between;">
            <div>
                <h2 style="margin: 0; color: {config['color']}; font-size: 2rem;">
                    {config['emoji']} {config['label']}
                </h2>
                <p style="margin: 0.5rem 0 0 0; color: #4b5563; font-size: 1.1rem;">
                    Overall Growth Risk Assessment
                </p>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 3rem;">{config['emoji']}</div>
                <div style="color: {config['color']}; font-weight: bold;">{overall_risk}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Domain Risk Breakdown
    st.markdown("### 📊 Domain Risk Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Domain risk cards
        domains = {
            'Revenue Quality': domain_risks.get('revenue_risk', 'NO_RISK'),
            'Margin Stress': domain_risks.get('margin_risk', 'NO_RISK'),
            'Capital Efficiency': domain_risks.get('capital_risk', 'NO_RISK'),
            'Management Signals': domain_risks.get('management_risk', 'NO_RISK')
        }
        
        for domain_name, risk_level in domains.items():
            domain_config = risk_config.get(risk_level, risk_config['UNKNOWN'])
            
            st.markdown(f"""
            <div style="background: white; padding: 1rem; border-radius: 10px; 
                        border-left: 4px solid {domain_config['color']}; margin-bottom: 0.5rem;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-weight: 600; color: #1f2937;">{domain_name}</div>
                        <div style="color: #6b7280; font-size: 0.9rem;">Risk Level</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 1.5rem;">{domain_config['emoji']}</div>
                        <div style="color: {domain_config['color']}; font-weight: 600; font-size: 0.9rem;">
                            {risk_level.replace('_', ' ')}
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    with col2:
        # Risk distribution chart
        risk_counts = {
            'GREEN': 0, 'YELLOW': 0, 'RED': 0, 'NO_RISK': 0
        }
        
        for risk_level in domains.values():
            if risk_level in risk_counts:
                risk_counts[risk_level] += 1
            elif risk_level == 'NO_RISK':
                risk_counts['NO_RISK'] += 1
        
        # Remove NO_RISK from chart (it's equivalent to GREEN)
        if risk_counts['NO_RISK'] > 0:
            risk_counts['GREEN'] += risk_counts['NO_RISK']
        del risk_counts['NO_RISK']
        
        if sum(risk_counts.values()) > 0:
            fig = go.Figure(data=[go.Pie(
                labels=list(risk_counts.keys()),
                values=list(risk_counts.values()),
                hole=0.6,
                marker_colors=[risk_config[k]['color'] for k in risk_counts.keys()],
                textinfo='label+percent',
                textfont_size=12
            )])
            
            fig.update_layout(
                title="Domain Risk Distribution",
                height=300,
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            
            st.plotly_chart(fig, use_container_width=True)
    
    # Warnings and Insights
    warnings = analysis_data.get('warnings', [])
    insights = analysis_data.get('insights', [])
    
    if warnings:
        st.markdown("### 🚨 Growth Quality Warnings")
        for warning in warnings:
            st.markdown(f"""
            <div style="background: #fef2f2; padding: 1rem; border-radius: 8px; 
                        border-left: 4px solid #ef4444; margin-bottom: 0.5rem;">
                <div style="color: #991b1b; font-weight: 500;">{warning}</div>
            </div>
            """, unsafe_allow_html=True)
    
    if insights:
        st.markdown("### 💡 Growth Quality Insights")
        for insight in insights:
            st.markdown(f"""
            <div style="background: #f0fdf4; padding: 1rem; border-radius: 8px; 
                        border-left: 4px solid #22c55e; margin-bottom: 0.5rem;">
                <div style="color: #166534; font-weight: 500;">{insight}</div>
            </div>
            """, unsafe_allow_html=True)
    
    # Detailed Metrics
    metrics = analysis_data.get('metrics', {})
    if metrics:
        st.markdown("### 📈 Detailed Risk Metrics")
        
        # Create metrics table
        metrics_data = []
        for key, value in metrics.items():
            if value is not None:
                metrics_data.append({
                    'Metric': key.replace('_', ' ').title(),
                    'Value': f"{value:.4f}" if isinstance(value, (int, float)) else str(value)
                })
        
        if metrics_data:
            df_metrics = pd.DataFrame(metrics_data)
            st.dataframe(df_metrics, use_container_width=True, hide_index=True)


def display_growth_quality_signal(symbol: str, signal_data: Dict[str, Any]):
    """
    Display integrated Growth Quality Signal
    
    Shows:
    - Final signal recommendation
    - Technical vs Growth integration
    - Position sizing guidance
    - Risk management notes
    """
    
    st.markdown(f"## 🎯 Growth Quality Signal - {symbol}")
    
    signal_type = signal_data.get('signal_type', 'HOLD')
    confidence = signal_data.get('confidence', 0.0)
    growth_risk = signal_data.get('growth_risk', 'YELLOW')
    position_adjustment = signal_data.get('position_sizing_adjustment', 1.0)
    
    # Signal configuration
    signal_config = {
        'BUY': {'emoji': '🟢', 'color': '#22c55e', 'action': 'BUY'},
        'ADD': {'emoji': '🟡', 'color': '#f59e0b', 'action': 'ADD'},
        'HOLD': {'emoji': '⚪', 'color': '#6b7280', 'action': 'HOLD'},
        'REDUCE': {'emoji': '🟠', 'color': '#f97316', 'action': 'REDUCE'},
        'SELL': {'emoji': '🔴', 'color': '#ef4444', 'action': 'SELL'}
    }
    
    config = signal_config.get(signal_type, signal_config['HOLD'])
    
    # Main signal display
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {config['color']}22 0%, {config['color']}11 100%); 
                padding: 2.5rem; border-radius: 15px; border-left: 5px solid {config['color']}; 
                margin-bottom: 2rem; text-align: center;">
        <div style="font-size: 4rem; margin-bottom: 1rem;">{config['emoji']}</div>
        <h1 style="margin: 0; color: {config['color']}; font-size: 2.5rem;">
            {config['action']} SIGNAL
        </h1>
        <div style="color: #4b5563; font-size: 1.2rem; margin-top: 0.5rem;">
            Growth Quality Integrated Analysis
        </div>
        <div style="margin-top: 1.5rem; display: flex; justify-content: center; gap: 2rem;">
            <div style="background: white; padding: 1rem 2rem; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="color: #6b7280; font-size: 0.9rem;">Confidence</div>
                <div style="color: {config['color']}; font-weight: bold; font-size: 1.5rem;">
                    {confidence:.1%}
                </div>
            </div>
            <div style="background: white; padding: 1rem 2rem; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="color: #6b7280; font-size: 0.9rem;">Growth Risk</div>
                <div style="color: #6b7280; font-weight: bold; font-size: 1.5rem;">
                    {growth_risk}
                </div>
            </div>
            <div style="background: white; padding: 1rem 2rem; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="color: #6b7280; font-size: 0.9rem;">Position Size</div>
                <div style="color: {config['color']}; font-weight: bold; font-size: 1.5rem;">
                    {position_adjustment:.0%}x
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Position Sizing Guidance
    st.markdown("### 📏 Position Sizing Guidance")
    
    if position_adjustment >= 1.0:
        guidance_color = "#22c55e"
        guidance_text = "Normal position size recommended"
    elif position_adjustment >= 0.5:
        guidance_color = "#f59e0b"
        guidance_text = "Reduce position size by 50%"
    else:
        guidance_color = "#ef4444"
        guidance_text = "Minimal position size - high risk"
    
    st.markdown(f"""
    <div style="background: {guidance_color}22; padding: 1.5rem; border-radius: 10px; 
                border-left: 4px solid {guidance_color};">
        <div style="display: flex; align-items: center; gap: 1rem;">
            <div style="font-size: 2rem;">📏</div>
            <div>
                <div style="font-weight: 600; color: #1f2937; font-size: 1.2rem;">
                    {guidance_text}
                </div>
                <div style="color: #6b7280; margin-top: 0.25rem;">
                    Position adjustment factor: {position_adjustment:.1%}x
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Reasoning sections
    integrated_reasoning = signal_data.get('integrated_reasoning', [])
    technical_reasoning = signal_data.get('technical_reasoning', [])
    growth_reasoning = signal_data.get('growth_reasoning', [])
    
    col1, col2 = st.columns(2)
    
    with col1:
        if technical_reasoning:
            st.markdown("#### 📊 Technical Analysis")
            for reason in technical_reasoning[:5]:  # Top 5 reasons
                st.markdown(f"• {reason}")
    
    with col2:
        if growth_reasoning:
            st.markdown("#### 🚨 Growth Quality Analysis")
            for reason in growth_reasoning[:5]:  # Top 5 reasons
                st.markdown(f"• {reason}")
    
    if integrated_reasoning:
        st.markdown("### 🎯 Integrated Analysis Reasoning")
        for reason in integrated_reasoning[:8]:  # Top 8 reasons
            st.markdown(f"• {reason}")
    
    # Risk Management Notes
    risk_notes = signal_data.get('risk_management_notes', [])
    if risk_notes:
        st.markdown("### ⚠️ Risk Management Notes")
        for note in risk_notes:
            st.markdown(f"""
            <div style="background: #fef3c7; padding: 1rem; border-radius: 8px; 
                        border-left: 4px solid #f59e0b; margin-bottom: 0.5rem;">
                <div style="color: #92400e; font-weight: 500;">{note}</div>
            </div>
            """, unsafe_allow_html=True)


def display_portfolio_growth_analysis(portfolio_data: Dict[str, Any]):
    """
    Display portfolio-wide growth quality analysis
    
    Shows:
    - Portfolio risk distribution
    - Individual symbol analysis
    - Portfolio-level recommendations
    """
    
    st.markdown("## 📊 Portfolio Growth Quality Analysis")
    
    analysis_date = portfolio_data.get('analysis_date', date.today())
    total_symbols = portfolio_data.get('total_symbols', 0)
    successful_analyses = portfolio_data.get('successful_analyses', 0)
    risk_distribution = portfolio_data.get('risk_distribution', {})
    signals = portfolio_data.get('signals', [])
    portfolio_risk = portfolio_data.get('portfolio_risk_assessment', 'UNKNOWN')
    recommendations = portfolio_data.get('recommendations', [])
    
    # Portfolio Overview
    st.markdown(f"### Portfolio Overview - {analysis_date}")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Symbols", total_symbols)
    
    with col2:
        st.metric("Successful Analyses", successful_analyses)
    
    with col3:
        success_rate = (successful_analyses / total_symbols * 100) if total_symbols > 0 else 0
        st.metric("Success Rate", f"{success_rate:.1f}%")
    
    with col4:
        st.metric("Portfolio Risk", portfolio_risk.replace('_', ' '))
    
    # Risk Distribution
    if risk_distribution:
        st.markdown("### 🎯 Risk Distribution")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Risk distribution bar chart
            risk_data = {
                'Risk Level': list(risk_distribution.keys()),
                'Count': list(risk_distribution.values())
            }
            
            df_risk = pd.DataFrame(risk_data)
            
            fig = px.bar(df_risk, x='Risk Level', y='Count', 
                        color='Risk Level',
                        color_discrete_map={
                            'GREEN': '#22c55e',
                            'YELLOW': '#f59e0b', 
                            'RED': '#ef4444'
                        })
            
            fig.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Risk summary cards
            total_analyzed = sum(risk_distribution.values())
            
            for risk_level, count in risk_distribution.items():
                percentage = (count / total_analyzed * 100) if total_analyzed > 0 else 0
                
                risk_config = {
                    'GREEN': {'emoji': '🟢', 'color': '#22c55e'},
                    'YELLOW': {'emoji': '🟡', 'color': '#f59e0b'},
                    'RED': {'emoji': '🔴', 'color': '#ef4444'}
                }
                
                config = risk_config.get(risk_level, {'emoji': '⚪', 'color': '#6b7280'})
                
                st.markdown(f"""
                <div style="background: {config['color']}22; padding: 1rem; border-radius: 8px; 
                            margin-bottom: 0.5rem; text-align: center;">
                    <div style="font-size: 1.5rem;">{config['emoji']}</div>
                    <div style="font-weight: 600; color: {config['color']};">
                        {risk_level}
                    </div>
                    <div style="color: #6b7280; font-size: 0.9rem;">
                        {count} symbols ({percentage:.1f}%)
                    </div>
                </div>
                """, unsafe_allow_html=True)
    
    # Individual Signals
    if signals:
        st.markdown("### 📈 Individual Symbol Analysis")
        
        # Create signals table
        signals_data = []
        for signal in signals:
            signals_data.append({
                'Symbol': signal['symbol'],
                'Signal': signal['signal_type'],
                'Growth Risk': signal['growth_risk'],
                'Confidence': f"{signal['confidence']:.1%}",
                'Position Size': f"{signal['position_sizing_adjustment']:.0%}x"
            })
        
        df_signals = pd.DataFrame(signals_data)
        
        # Color code signals
        def style_signal(val):
            if val == 'BUY':
                return 'background-color: #dcfce7; color: #166534'
            elif val == 'ADD':
                return 'background-color: #fef3c7; color: #92400e'
            elif val == 'SELL':
                return 'background-color: #fef2f2; color: #dc2626'
            elif val == 'REDUCE':
                return 'background-color: #fed7aa; color: #9a3412'
            else:
                return 'background-color: #f3f4f6; color: #374151'
        
        def style_risk(val):
            if val == 'GREEN':
                return 'background-color: #dcfce7; color: #166534'
            elif val == 'YELLOW':
                return 'background-color: #fef3c7; color: #92400e'
            elif val == 'RED':
                return 'background-color: #fef2f2; color: #dc2626'
            else:
                return 'background-color: #f3f4f6; color: #374151'
        
        styled_df = df_signals.style.applymap(style_signal, subset=['Signal']) \
                                .applymap(style_risk, subset=['Growth Risk'])
        
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
    
    # Portfolio Recommendations
    if recommendations:
        st.markdown("### 💡 Portfolio Recommendations")
        for rec in recommendations:
            st.markdown(f"""
            <div style="background: #f0fdf4; padding: 1.5rem; border-radius: 10px; 
                        border-left: 4px solid #22c55e; margin-bottom: 1rem;">
                <div style="color: #166534; font-weight: 500; font-size: 1.1rem;">{rec}</div>
            </div>
            """, unsafe_allow_html=True)
