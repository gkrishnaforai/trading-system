"""
Fundamentals Analysis Page
Comprehensive fundamental analysis using Early Warning Flags Engine
"""

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json
import sys
import os

# Add the current directory to Python path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure page
st.set_page_config(
    page_title="Fundamentals Analysis",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Redirect notice - Fundamentals Analysis is now integrated into Enhanced Portfolio Analysis
st.warning("📄 **Page Moved**: Fundamentals Analysis is now integrated into the **Enhanced Portfolio Analysis** page for a better user experience.")
st.info("🔗 **Go to**: [Enhanced Portfolio Analysis](/Enhanced_Portfolio_Analysis) to access fundamentals analysis alongside your portfolio holdings.")

st.markdown("---")
st.markdown("# 💰 Fundamentals Analysis")
st.markdown("*This page has been moved to provide a more integrated experience*")

st.markdown("""
## 🎯 What's Available in Enhanced Portfolio Analysis

The fundamentals analysis is now available as a tab within the Enhanced Portfolio Analysis page, providing:

### 📊 **Integrated Analysis**
- **Technical Analysis** tab - Price trends, indicators, signals
- **Fundamentals Analysis** tab - Growth health, investment posture

### 🔍 **Portfolio Context**
- View fundamentals for your actual portfolio holdings
- Add stocks directly from the analysis
- Track performance alongside fundamentals

### 📈 **Enhanced Features**
- Institutional-grade growth health classification
- Clear investment guidance (BUY/HOLD/TRIM/EXIT)
- Forward return expectations
- Risk factors and opportunities

## 🚀 **How to Access**

1. Navigate to **Enhanced Portfolio Analysis**
2. Click on any stock symbol in your portfolio
3. Switch to the **"Fundamentals Analysis"** tab

This integration provides a more seamless experience for analyzing both technical and fundamental aspects of your portfolio holdings.
""")

st.markdown("---")
st.markdown("*For any questions, please use the Enhanced Portfolio Analysis page where all analysis features are now available.*")

# Custom CSS for professional styling
st.markdown("""
<style>
.metric-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 20px;
    border-radius: 10px;
    color: white;
    margin: 10px 0;
}
.risk-green { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
.risk-yellow { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
.risk-red { background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%); }
.analysis-card {
    background: #f8f9fa;
    padding: 20px;
    border-radius: 10px;
    border-left: 4px solid #667eea;
    margin: 10px 0;
}
</style>
""", unsafe_allow_html=True)


class FundamentalsAnalysisUI:
    """Professional fundamentals analysis dashboard"""
    
    def __init__(self):
        self.api_base_url = "http://python-worker:8001"
        
    def fetch_growth_quality_analysis(self, symbol: str) -> Dict[str, Any]:
        """Fetch growth quality analysis from API"""
        try:
            response = requests.get(f"{self.api_base_url}/api/v1/growth-quality/early-warning/{symbol}", timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                st.error(f"Failed to fetch analysis: {response.text}")
                return {}
        except Exception as e:
            st.error(f"Error connecting to API: {e}")
            return {}
    
    def fetch_risk_metrics(self, symbol: str) -> Dict[str, Any]:
        """Fetch detailed risk metrics from API"""
        try:
            response = requests.get(f"{self.api_base_url}/api/v1/growth-quality/risk-metrics/{symbol}", timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                return {}
        except Exception as e:
            return {}
    
    def fetch_portfolio_analysis(self, symbols: List[str]) -> Dict[str, Any]:
        """Fetch portfolio analysis from API"""
        try:
            response = requests.post(
                f"{self.api_base_url}/api/v1/growth-quality/portfolio-analysis",
                json={"symbols": symbols, "include_technical": False},
                timeout=30
            )
            if response.status_code == 200:
                return response.json()
            else:
                return {}
        except Exception as e:
            return {}
    
    def render_risk_overview(self, analysis_data: Dict[str, Any]):
        """Render risk overview with professional styling"""
        if not analysis_data:
            return
        
        overall_risk = analysis_data.get('overall_risk', 'GREEN')
        risk_colors = {
            'GREEN': 'risk-green',
            'YELLOW': 'risk-yellow', 
            'RED': 'risk-red'
        }
        
        risk_icons = {
            'GREEN': '✅',
            'YELLOW': '⚠️',
            'RED': '🚨'
        }
        
        risk_descriptions = {
            'GREEN': 'Low Risk - Healthy growth fundamentals',
            'YELLOW': 'Medium Risk - Early warning signs detected',
            'RED': 'High Risk - Structural breakdown detected'
        }
        
        # Main risk card
        st.markdown(f"""
        <div class="metric-card {risk_colors.get(overall_risk, '')}">
            <h2>{risk_icons.get(overall_risk, '')} Overall Risk: {overall_risk}</h2>
            <p>{risk_descriptions.get(overall_risk, '')}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Domain risks
        domain_risks = analysis_data.get('domain_risks', {})
        if domain_risks:
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 📊 Revenue Quality")
                revenue_risk = domain_risks.get('revenue_risk', 'NO_RISK')
                self._render_domain_risk_gauge(revenue_risk, "Revenue Quality")
                
                st.markdown("### 💰 Capital Efficiency")
                capital_risk = domain_risks.get('capital_risk', 'NO_RISK')
                self._render_domain_risk_gauge(capital_risk, "Capital Efficiency")
            
            with col2:
                st.markdown("### 📈 Margin Stress")
                margin_risk = domain_risks.get('margin_risk', 'NO_RISK')
                self._render_domain_risk_gauge(margin_risk, "Margin Stress")
                
                st.markdown("### 🎯 Management Signals")
                mgmt_risk = domain_risks.get('management_risk', 'NO_RISK')
                self._render_domain_risk_gauge(mgmt_risk, "Management Signals")
    
    def _render_domain_risk_gauge(self, risk_level: str, title: str):
        """Render individual domain risk gauge"""
        risk_values = {'NO_RISK': 0, 'EARLY_STRESS': 50, 'STRUCTURAL_BREAKDOWN': 100}
        risk_colors = {'NO_RISK': '#38ef7d', 'EARLY_STRESS': '#f5576c', 'STRUCTURAL_BREAKDOWN': '#eb3349'}
        
        fig = go.Figure(go.Indicator(
            mode = "gauge+number+delta",
            value = risk_values.get(risk_level, 0),
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': title},
            delta = {'reference': 0},
            gauge = {
                'axis': {'range': [None, 100]},
                'bar': {'color': risk_colors.get(risk_level, '#38ef7d')},
                'steps': [
                    {'range': [0, 33], 'color': "lightgray"},
                    {'range': [33, 66], 'color': "gray"},
                    {'range': [66, 100], 'color': "darkgray"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 80
                }
            }
        ))
        
        fig.update_layout(height=250, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)
    
    def render_detailed_flags(self, risk_metrics: Dict[str, Any]):
        """Render detailed flag analysis"""
        if not risk_metrics:
            return
        
        domain_risks = risk_metrics.get('domain_risks', {})
        
        for domain, data in domain_risks.items():
            domain_name = domain.replace('_', ' ').title()
            
            with st.expander(f"🔍 {domain_name} Analysis", expanded=True):
                flags = data.get('flags', {})
                
                for flag_name, flag_value in flags.items():
                    flag_display = flag_name.replace('_', ' ').title()
                    status_icon = "🔴" if flag_value else "✅"
                    status_color = "red" if flag_value else "green"
                    
                    st.markdown(f"""
                    <div class="analysis-card">
                        <h4 style="color: {status_color};">{status_icon} {flag_display}</h4>
                        <p>Flag is {'triggered' if flag_value else 'not triggered'}</p>
                    </div>
                    """, unsafe_allow_html=True)
    
    def render_warnings_insights(self, analysis_data: Dict[str, Any]):
        """Render warnings and insights"""
        if not analysis_data:
            return
        
        warnings = analysis_data.get('warnings', [])
        insights = analysis_data.get('insights', [])
        
        if warnings:
            st.markdown("### 🚨 Warnings")
            for warning in warnings:
                st.markdown(f"""
                <div class="analysis-card" style="border-left-color: #f45c43;">
                    <p>{warning}</p>
                </div>
                """, unsafe_allow_html=True)
        
        if insights:
            st.markdown("### 💡 Insights")
            for insight in insights:
                st.markdown(f"""
                <div class="analysis-card" style="border-left-color: #38ef7d;">
                    <p>{insight}</p>
                </div>
                """, unsafe_allow_html=True)
    
    def render_metrics_dashboard(self, analysis_data: Dict[str, Any]):
        """Render detailed metrics dashboard"""
        if not analysis_data:
            return
        
        metrics = analysis_data.get('metrics', {})
        
        if metrics:
            st.markdown("### 📊 Key Metrics")
            
            # Group metrics by category
            metric_categories = {
                'Revenue Metrics': ['receivables_vs_revenue_growth', 'margin_trend'],
                'Profitability Metrics': ['roe_trend', 'roic_trend'],
                'Efficiency Metrics': ['growth_vs_capital'],
                'Financial Health': ['debt_level']
            }
            
            for category, metric_keys in metric_categories.items():
                st.markdown(f"#### {category}")
                cols = st.columns(len(metric_keys))
                
                for i, key in enumerate(metric_keys):
                    if key in metrics:
                        value = metrics[key]
                        with cols[i]:
                            # Determine color based on value
                            color = "normal"
                            if "declining" in str(value).lower() or "inefficient" in str(value).lower():
                                color = "red"
                            elif "stable" in str(value).lower() or "moderate" in str(value).lower():
                                color = "green"
                            
                            metric_name = key.replace('_', ' ').title()
                            st.metric(metric_name, str(value).title())
    
    def render_portfolio_view(self):
        """Render portfolio analysis view"""
        st.markdown("## 📈 Portfolio Analysis")
        
        # Symbol selection
        available_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA"]
        selected_symbols = st.multiselect(
            "Select symbols for portfolio analysis",
            options=available_symbols,
            default=["AAPL", "MSFT", "GOOGL"],
            key="portfolio_symbols"
        )
        
        if st.button("Analyze Portfolio", key="analyze_portfolio"):
            if selected_symbols:
                with st.spinner("Analyzing portfolio..."):
                    portfolio_data = self.fetch_portfolio_analysis(selected_symbols)
                    
                    if portfolio_data:
                        self._render_portfolio_results(portfolio_data, selected_symbols)
                    else:
                        st.error("Failed to analyze portfolio")
            else:
                st.warning("Please select at least one symbol")
    
    def _render_portfolio_results(self, portfolio_data: Dict[str, Any], symbols: List[str]):
        """Render portfolio analysis results"""
        risk_distribution = portfolio_data.get('risk_distribution', {})
        recommendations = portfolio_data.get('recommendations', [])
        
        # Portfolio risk overview
        st.markdown("### Portfolio Risk Distribution")
        
        if risk_distribution:
            fig = go.Figure(data=[
                go.Bar(name=risk, x=[risk], y=[count], marker_color=['#38ef7d', '#f5576c', '#eb3349'][i])
                for i, (risk, count) in enumerate(risk_distribution.items())
            ])
            
            fig.update_layout(
                title="Risk Distribution Across Portfolio",
                xaxis_title="Risk Level",
                yaxis_title="Number of Stocks",
                height=400
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        # Recommendations
        if recommendations:
            st.markdown("### 📋 Portfolio Recommendations")
            for rec in recommendations:
                st.markdown(f"""
                <div class="analysis-card">
                    <p>{rec}</p>
                </div>
                """, unsafe_allow_html=True)
    
    def render_single_stock_analysis(self):
        """Render single stock analysis view"""
        st.markdown("## 📊 Single Stock Analysis")
        
        # Get symbol from URL parameters or input
        symbol_from_url = st.query_params.get("symbol", "").upper()
        
        # Symbol input
        symbol = st.text_input(
            "Enter Stock Symbol",
            value=symbol_from_url or "AAPL",
            key="analysis_symbol",
            help="Enter the stock ticker symbol for analysis"
        ).upper()
        
        if st.button("Analyze Stock", key="analyze_stock"):
            if symbol:
                with st.spinner(f"Analyzing {symbol}..."):
                    # Fetch analysis data
                    analysis_data = self.fetch_growth_quality_analysis(symbol)
                    risk_metrics = self.fetch_risk_metrics(symbol)
                    
                    if analysis_data:
                        # Display results
                        st.markdown(f"## 📈 {symbol} Growth Quality Analysis")
                        
                        # Risk overview
                        self.render_risk_overview(analysis_data)
                        
                        # Detailed metrics
                        self.render_metrics_dashboard(analysis_data)
                        
                        # Detailed flags
                        if risk_metrics:
                            self.render_detailed_flags(risk_metrics)
                        
                        # Warnings and insights
                        self.render_warnings_insights(analysis_data)
                        
                        # Analysis date
                        analysis_date = analysis_data.get('analysis_date', 'Unknown')
                        st.caption(f"Analysis as of: {analysis_date}")
                        
                    else:
                        st.error(f"Failed to analyze {symbol}")
            else:
                st.warning("Please enter a stock symbol")
    
    def render_data_status(self):
        """Render data loading status"""
        st.markdown("## 📥 Data Status")
        
        # Check API connectivity
        try:
            response = requests.get(f"{self.api_base_url}/health", timeout=5)
            if response.status_code == 200:
                st.success("✅ API Connection: Healthy")
            else:
                st.error("❌ API Connection: Unhealthy")
        except:
            st.error("❌ API Connection: Failed")
        
        # Data loading instructions
        st.markdown("""
        ### 📋 Data Loading Instructions
        
        To ensure comprehensive fundamentals analysis:
        
        1. **Load All Data**: Use the "Load All Data" button in the main dashboard
        2. **Required Data Types**:
           - Price Data (historical market data)
           - Technical Indicators (RSI, MACD, etc.)
           - Fundamentals (income statements, balance sheets, cash flow, ratios)
        
        3. **Data Sources**:
           - Yahoo Finance (historical price data)
           - Massive API (real-time data, fundamentals, indicators)
        
        4. **Verification**:
           - Check data availability in the main dashboard
           - Ensure fundamentals tables are populated
           - Verify recent data timestamps
        """)
    
    def run(self):
        """Main application runner"""
        st.title("💰 Fundamentals Analysis Dashboard")
        st.markdown("Comprehensive growth quality analysis using industry-standard metrics")
        
        # Sidebar navigation
        st.sidebar.title("Navigation")
        page = st.sidebar.selectbox(
            "Select Analysis View",
            ["Single Stock", "Portfolio", "Data Status"],
            key="analysis_page"
        )
        
        # Render selected page
        if page == "Single Stock":
            self.render_single_stock_analysis()
        elif page == "Portfolio":
            self.render_portfolio_view()
        else:
            self.render_data_status()
        
        # Footer
        st.markdown("---")
        st.markdown("💰 Fundamentals Analysis Dashboard | Growth Quality Engine")


def main():
    """Main entry point"""
    app = FundamentalsAnalysisUI()
    app.run()


if __name__ == "__main__":
    main()
