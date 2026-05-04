"""
Data Loading Profiles Viewer
Comprehensive view of all data loading profiles and what data they collect
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any
import json

# Configure page
st.set_page_config(
    page_title="Data Loading Profiles",
    page_icon="📊",
    layout="wide"
)

# API base URL
API_BASE = "http://localhost:8001"

# Data type descriptions and categories
DATA_TYPE_INFO = {
    # Core Market Data
    "price_historical": {
        "category": "Market Data",
        "description": "Historical daily price data (OHLCV)",
        "table": "raw_market_data_daily",
        "fields": ["open", "high", "low", "close", "volume", "trade_date"]
    },
    "price_current": {
        "category": "Market Data", 
        "description": "Current/latest price information",
        "table": "fundamentals_snapshots",
        "fields": ["current_price", "price_change", "price_change_pct"]
    },
    "price_intraday_5m": {
        "category": "Market Data",
        "description": "5-minute intraday price data",
        "table": "raw_market_data_intraday", 
        "fields": ["open", "high", "low", "close", "volume", "ts"]
    },
    
    # Fundamental Data
    "fundamentals": {
        "category": "Fundamentals",
        "description": "Core company fundamentals (P/E, EPS, etc)",
        "table": "fundamentals_snapshots",
        "fields": ["pe_ratio", "eps", "market_cap", "dividend_yield", "book_value"]
    },
    "key_metrics_ttm": {
        "category": "Fundamentals",
        "description": "Trailing Twelve Months key metrics",
        "table": "stock_insights_snapshots",
        "fields": ["marketCap", "peRatioTTM", "pbRatioTTM", "roeTTM", "debtToEquityTTM"]
    },
    
    # Financial Statements
    "income_statements": {
        "category": "Financial Statements",
        "description": "Income statement data (revenue, expenses, profit)",
        "table": "financial_statements",
        "fields": ["revenue", "netIncome", "operatingIncome", "grossProfit", "eps"]
    },
    "balance_sheets": {
        "category": "Financial Statements", 
        "description": "Balance sheet data (assets, liabilities, equity)",
        "table": "financial_statements",
        "fields": ["totalAssets", "totalLiabilities", "totalStockholdersEquity", "cash", "debt"]
    },
    "cash_flow_statements": {
        "category": "Financial Statements",
        "description": "Cash flow statement data",
        "table": "financial_statements", 
        "fields": ["operatingCashFlow", "investingCashFlow", "financingCashFlow", "freeCashFlow"]
    },
    
    # Financial Metrics & Ratios
    "financial_ratios": {
        "category": "Financial Metrics",
        "description": "Financial ratios and margins",
        "table": "financial_ratios",
        "fields": ["roe", "roa", "roic", "debt_to_equity", "gross_profit_margin", "operating_margin"]
    },
    "financial_growth": {
        "category": "Financial Metrics",
        "description": "Financial growth rates",
        "table": "stock_insights_snapshots",
        "fields": ["revenueGrowth", "earningsGrowth", "epsGrowth"]
    },
    "financial_scores": {
        "category": "Financial Metrics",
        "description": "Financial health scores",
        "table": "stock_insights_snapshots",
        "fields": ["financialScore", "bankruptcyScore", "growthScore"]
    },
    
    # Growth Metrics
    "income_statement_growth": {
        "category": "Growth Metrics",
        "description": "Income statement growth analysis",
        "table": "stock_insights_snapshots",
        "fields": ["growthRevenue", "growthNetIncome", "growthEPS"]
    },
    "balance_sheet_growth": {
        "category": "Growth Metrics",
        "description": "Balance sheet growth trends",
        "table": "stock_insights_snapshots",
        "fields": ["growthAssets", "growthDebt", "growthEquity"]
    },
    "cash_flow_growth": {
        "category": "Growth Metrics", 
        "description": "Cash flow growth analysis",
        "table": "stock_insights_snapshots",
        "fields": ["growthOperatingCF", "growthFreeCF", "growthCapex"]
    },
    
    # Analyst & Grading Data
    "stock_grades": {
        "category": "Analyst Data",
        "description": "Stock grades and ratings",
        "table": "stock_insights_snapshots",
        "fields": ["grade", "rating", "score", "recommendation"]
    },
    "analyst_ratings": {
        "category": "Analyst Data",
        "description": "Analyst buy/sell/hold ratings",
        "table": "stock_insights_snapshots",
        "fields": ["strongBuy", "buy", "hold", "sell", "strongSell"]
    },
    "price_targets": {
        "category": "Analyst Data",
        "description": "Analyst price targets",
        "table": "stock_insights_snapshots",
        "fields": ["targetPrice", "priceTargetHigh", "priceTargetLow", "priceTargetMean"]
    },
    "consensus_data": {
        "category": "Analyst Data",
        "description": "Consensus estimates and forecasts",
        "table": "stock_insights_snapshots",
        "fields": ["epsConsensus", "revenueConsensus", "growthConsensus"]
    },
    
    # Market Intelligence
    "institutional_buying": {
        "category": "Market Intelligence",
        "description": "Institutional ownership and buying activity",
        "table": "stock_insights_snapshots",
        "fields": ["institutionalOwnership", "institutionalBuys", "institutionalSells"]
    },
    "earnings_transcripts": {
        "category": "Market Intelligence",
        "description": "Earnings call transcripts",
        "table": "stock_insights_snapshots",
        "fields": ["transcriptText", "sentiment", "keyTopics"]
    },
    
    # Other Data Types
    "indicators": {
        "category": "Technical Analysis",
        "description": "Technical indicators",
        "table": "indicators_daily",
        "fields": ["rsi", "macd", "bollinger_upper", "bollinger_lower", "sma_50", "sma_200"]
    },
    "news": {
        "category": "News & Events",
        "description": "Stock news and articles",
        "table": "stock_news",
        "fields": ["title", "content", "sentiment", "source", "published_at"]
    },
    "earnings": {
        "category": "News & Events",
        "description": "Earnings data and calendar",
        "table": "earnings_data",
        "fields": ["earnings_date", "eps_actual", "eps_estimate", "surprise"]
    },
    "short_interest": {
        "category": "Market Intelligence",
        "description": "Short interest data",
        "table": "short_interest",
        "fields": ["short_interest", "short_ratio", "days_to_cover"]
    }
}

# Profile definitions (from ingestion profiles)
PROFILES = {
    "prices_live_v1": {
        "description": "Live intraday price data collection",
        "window_days": 1,
        "data_types": ["price_intraday_5m"],
        "schedule": "Every 5 minutes during market hours"
    },
    "daily_news_grades_v1": {
        "description": "Daily news and stock grades collection",
        "window_days": 7,
        "data_types": ["news", "stock_grades"],
        "schedule": "Daily at 6 AM EST"
    },
    "enhanced_fundamentals_v1": {
        "description": "Enhanced fundamentals with growth metrics",
        "window_days": 30,
        "data_types": [
            "fundamentals", "key_metrics_ttm", "income_statement_growth",
            "balance_sheet_growth", "cash_flow_growth", "financial_growth",
            "financial_ratios", "stock_grades", "analyst_ratings"
        ],
        "schedule": "Weekly on Sundays"
    },
    "weekly_fundamentals_enhanced": {
        "description": "Comprehensive weekly fundamentals collection",
        "window_days": 7,
        "data_types": [
            "fundamentals", "key_metrics_ttm", "income_statements", "balance_sheets",
            "cash_flow_statements", "financial_ratios", "financial_growth", "financial_scores",
            "income_statement_growth", "balance_sheet_growth", "cash_flow_growth",
            "stock_grades", "analyst_ratings", "price_targets", "consensus_data",
            "institutional_buying", "earnings_transcripts"
        ],
        "schedule": "Daily at 10 AM and 6 PM EST"
    }
}

def get_scheduler_status() -> Dict[str, Any]:
    """Get fundamentals scheduler status"""
    try:
        response = requests.get(f"{API_BASE}/api/v1/fundamentals-scheduler/status")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Error getting scheduler status: {e}")
    return {"running": False, "jobs": []}

def get_table_record_count(table_name: str) -> int:
    """Get record count for a specific table"""
    try:
        response = requests.get(f"{API_BASE}/api/v1/db-stats/table-stats")
        if response.status_code == 200:
            data = response.json()
            if table_name in data.get("tables", {}):
                return data["tables"][table_name]["record_count"]
    except Exception as e:
        st.error(f"Error getting table stats: {e}")
    return 0

def get_profile_stats(profile_name: str) -> Dict[str, Any]:
    """Get statistics for a specific profile"""
    try:
        response = requests.get(f"{API_BASE}/api/v1/db-stats/profile-stats/{profile_name}")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Error getting profile stats: {e}")
    return {"profile": {"total_records": 0, "data_types": {}}}

def trigger_profile_execution(profile_name: str, symbols: List[str]) -> Dict[str, Any]:
    """Trigger manual execution of a profile"""
    try:
        payload = {
            "profile_name": profile_name,
            "symbols": symbols,
            "run_id": f"manual-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        }
        response = requests.post(f"{API_BASE}/api/v1/data/execute-profile", json=payload)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Error triggering profile execution: {e}")
    return {"success": False, "message": str(e)}

def main():
    st.title("📊 Data Loading Profiles")
    st.markdown("Comprehensive view of all data loading profiles and collected data types")
    
    # Get scheduler status
    scheduler_status = get_scheduler_status()
    
    # Sidebar with scheduler info
    with st.sidebar:
        st.header("🕐 Scheduler Status")
        
        if scheduler_status.get("running"):
            st.success("✅ Fundamentals Scheduler Running")
            st.write(f"**Timezone:** {scheduler_status.get('timezone', 'Unknown')}")
            st.write(f"**Active Jobs:** {len(scheduler_status.get('jobs', []))}")
            
            for job in scheduler_status.get('jobs', []):
                st.write(f"• {job.get('name', 'Unknown')}")
                if job.get('next_run'):
                    next_run = job['next_run'].replace('T', ' ').replace('-05:00', ' EST')
                    st.write(f"  Next: {next_run}")
        else:
            st.error("❌ Scheduler Not Running")
            
        st.divider()
        
        # Profile selector
        st.header("🔍 Profile Selection")
        selected_profile = st.selectbox(
            "Select Profile to View:",
            options=list(PROFILES.keys()),
            key="profile_selector"
        )
    
    # Main content area
    if selected_profile:
        profile = PROFILES[selected_profile]
        
        # Get real profile statistics
        profile_stats = get_profile_stats(selected_profile)
        
        # Profile header
        st.header(f"📋 {selected_profile}")
        st.markdown(f"**Description:** {profile['description']}")
        st.markdown(f"**Schedule:** {profile['schedule']}")
        st.markdown(f"**Data Window:** {profile['window_days']} days")
        
        # Profile statistics
        if profile_stats.get("success"):
            stats = profile_stats["profile"]
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Data Types", stats["data_types_count"])
            with col2:
                st.metric("Total Records", f"{stats.get('total_records', 0):,}")
            with col3:
                st.metric("Window Days", stats["window_days"])
        
        # Manual execution controls
        st.subheader("🚀 Manual Execution")
        col1, col2 = st.columns([2, 1])
        
        with col1:
            symbols_input = st.text_input(
                "Enter symbols (comma-separated):",
                value="COIN,AAPL,MSFT,GOOGL",
                key="symbols_input"
            )
            symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]
        
        with col2:
            st.markdown("**Actions:**")
            if st.button(f"▶️ Execute {selected_profile}", key="execute_profile"):
                with st.spinner(f"Executing {selected_profile}..."):
                    result = trigger_profile_execution(selected_profile, symbols)
                    if result.get("success"):
                        st.success(f"✅ Profile execution started!")
                        st.json(result)
                    else:
                        st.error(f"❌ Execution failed: {result.get('message')}")
        
        # Data types overview
        st.subheader("📊 Data Types Collected")
        
        # Group data types by category
        categorized_types = {}
        for data_type in profile['data_types']:
            if data_type in DATA_TYPE_INFO:
                category = DATA_TYPE_INFO[data_type]['category']
                if category not in categorized_types:
                    categorized_types[category] = []
                categorized_types[category].append(data_type)
        
        # Display by category with real stats
        for category, data_types in categorized_types.items():
            with st.expander(f"📂 {category} ({len(data_types)} types)", expanded=True):
                for data_type in data_types:
                    info = DATA_TYPE_INFO[data_type]
                    
                    # Get real stats for this data type
                    record_count = 0
                    latest_date = None
                    if profile_stats.get("success"):
                        data_type_stats = profile_stats["profile"]["data_types"].get(data_type, {})
                        record_count = data_type_stats.get("record_count", 0)
                        latest_date = data_type_stats.get("latest_date")
                    
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    
                    with col1:
                        st.markdown(f"**{data_type}**")
                        st.markdown(f"{info['description']}")
                        if latest_date:
                            st.markdown(f"*Latest: {latest_date[:10]}*")
                    
                    with col2:
                        st.markdown(f"**Table:** `{info['table']}`")
                    
                    with col3:
                        st.metric("Records", f"{record_count:,}")
                    
                    with col4:
                        if st.button(f"📋 Fields", key=f"fields_{data_type}"):
                            st.json(info['fields'])
        
        # Profile execution details
        st.subheader("⚙️ Execution Details")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Data Flow:**")
            st.markdown("1. Scheduler triggers profile execution")
            st.markdown("2. Profile calls DataRefreshManager")
            st.markdown("3. Each data type is refreshed")
            st.markdown("4. Results stored in respective tables")
            st.markdown("5. Events emitted to universal_events")
        
        with col2:
            st.markdown("**Data Sources:**")
            st.markdown("• Financial Modeling Prep (FMP)")
            st.markdown("• Alpha Vantage")
            st.markdown("• Yahoo Finance")
            st.markdown("• Massive API")
            st.markdown("• Internal calculations")
        
        # Missing data types
        st.subheader("⚠️ Missing Data Types")
        
        all_data_types = set(DATA_TYPE_INFO.keys())
        profile_data_types = set(profile['data_types'])
        missing_types = all_data_types - profile_data_types
        
        if missing_types:
            st.write(f"This profile doesn't collect {len(missing_types)} available data types:")
            
            missing_by_category = {}
            for data_type in missing_types:
                category = DATA_TYPE_INFO[data_type]['category']
                if category not in missing_by_category:
                    missing_by_category[category] = []
                missing_by_category[category].append(data_type)
            
            for category, types in missing_by_category.items():
                with st.expander(f"Missing {category} ({len(types)} types)"):
                    for data_type in types:
                        info = DATA_TYPE_INFO[data_type]
                        st.markdown(f"• **{data_type}**: {info['description']}")
        else:
            st.success("✅ This profile collects all available data types!")
    
    # Bottom section with all profiles overview
    st.divider()
    st.header("📈 All Profiles Overview")
    
    # Create summary table
    profile_summary = []
    for profile_name, profile_data in PROFILES.items():
        profile_summary.append({
            "Profile": profile_name,
            "Description": profile_data['description'],
            "Data Types": len(profile_data['data_types']),
            "Window (days)": profile_data['window_days'],
            "Schedule": profile_data['schedule']
        })
    
    df_summary = pd.DataFrame(profile_summary)
    st.dataframe(df_summary, use_container_width=True)
    
    # Data type coverage matrix
    st.subheader("🔍 Data Type Coverage Matrix")
    
    # Create matrix
    all_types = sorted(list(DATA_TYPE_INFO.keys()))
    matrix_data = []
    
    for profile_name, profile_data in PROFILES.items():
        row = {"Profile": profile_name}
        for data_type in all_types:
            row[data_type] = "✅" if data_type in profile_data['data_types'] else "❌"
        matrix_data.append(row)
    
    df_matrix = pd.DataFrame(matrix_data)
    
    # Style the matrix for better readability
    styled_matrix = df_matrix.style.applymap(
        lambda x: 'background-color: #d4edda' if x == '✅' else 'background-color: #f8d7da'
    )
    
    st.dataframe(styled_matrix, use_container_width=True)

if __name__ == "__main__":
    main()
