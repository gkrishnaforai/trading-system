"""
Trading Cockpit — entrypoint.

Navigation is fully owned here via st.navigation sections; the pages/ directory
auto-sidebar is disabled. Retired/superseded pages live in pages_archive/ and are
not registered.
"""
import os
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
PYTHON_API_URL = os.getenv("PYTHON_API_URL", "http://localhost:8001")

pg = st.navigation(
    {
        # The cockpit — the 10 daily-driver pages, cross-linked by the
        # top nav strip in utils.render_top_nav(). Order mirrors the
        # day: brief → board → manage → strategy → find → research.
        "🎯 Cockpit": [
            st.Page("pages/0_Alerts_Briefing.py", title="Alerts & Briefing", icon="🔔", default=True),
            st.Page("pages/00_Daily_Board.py", title="Daily Board", icon="📋"),
            st.Page("pages/3_Portfolio_Manager.py", title="Portfolio Manager", icon="💼"),
            st.Page("pages/28_Portfolio_Strategy.py", title="Portfolio Strategy", icon="🧭"),
            st.Page("pages/1_Swing_Screener.py", title="Swing Screener", icon="🔍"),
            st.Page("pages/29_Hidden_Gems.py", title="Hidden Gems", icon="💎"),
            st.Page("pages/30_Conviction.py", title="Conviction List", icon="🏆"),
            st.Page("pages/31_Stock.py", title="Stock Health", icon="🩺"),
            st.Page("pages/32_Daily_Sheet.py", title="Daily Sheet", icon="📄"),
            st.Page("pages/33_Readiness.py", title="Readiness", icon="✅"),
            st.Page("pages/25_GARP_Screen.py", title="GARP Screen", icon="⚖️"),
            st.Page("pages/9_Options.py", title="Options", icon="🎲"),
            st.Page("pages/24_Agent_Workbench.py", title="Agent Workbench", icon="🤖"),
            st.Page("pages/27_Learning_Lab.py", title="Learning Lab", icon="🧠"),
        ],
        "Home": [
            st.Page("pages/1_Home.py", title="Home", icon="🏠"),
        ],
        "Portfolio": [
            st.Page("pages/4_Portfolio_Review.py", title="Portfolio Review", icon="💼"),
        ],
        "Swing": [
            st.Page("pages/6_Swing_Trading.py", title="Swing Trading", icon="📈"),
            st.Page("pages/19_Trading_Decision_V3_Portfolio.py", title="Trading Decision V3", icon="🎯"),
        ],
        "Research": [
            st.Page("pages/Stock_Overview_Pro.py", title="Stock Overview", icon="📈"),
            st.Page("pages/2_Stock_Analysis.py", title="Stock Analysis", icon="🔎"),
            st.Page("pages/21_Fundamentals_Screener.py", title="Fundamentals Screener", icon="🧮"),
            st.Page("pages/Fundamentals_Analysis.py", title="Fundamentals Analysis", icon="💰"),
            st.Page("pages/23_Company_Profile_Scores.py", title="Company Scores", icon="🏢"),
        ],
        "Market": [
            st.Page("pages/8_Market_Movers.py", title="Market Movers", icon="🌐"),
            st.Page("pages/22_Macro_Dashboard.py", title="Macro Dashboard", icon="🌍"),
            st.Page("pages/5_📄_Reports.py", title="Reports", icon="📄"),
        ],
        "Backtesting": [
            st.Page("pages/10_Universal_Backtest.py", title="Universal Backtest", icon="🔄"),
            st.Page("pages/13_Universal_Backtest_Advanced.py", title="Advanced Backtest", icon="⚙️"),
            st.Page("pages/11_3x_ETF_Backtest.py", title="3x ETF Backtest", icon="🚀"),
            st.Page("pages/12_Regular_ETF_Backtest.py", title="ETF Backtest", icon="📊"),
        ],
        "Admin": [
            st.Page("pages/17_Comprehensive_Admin_Dashboard.py", title="Admin Dashboard", icon="🛡️"),
            st.Page("pages/9_Trading_Dashboard.py", title="Trading Dashboard", icon="📊"),
            st.Page("pages/13_Data_Loading_Profiles.py", title="Data Profiles", icon="📥"),
            st.Page("pages/14_Database_Admin.py", title="Database Admin", icon="🗄️"),
            st.Page("pages/18_Data_Load_Run_Tester.py", title="Data Load Tester", icon="🧪"),
            st.Page("pages/16_Universal_Alert_System.py", title="Alert System", icon="🔔"),
            st.Page("pages/7_📝_Blog_Generation.py", title="Blog Generation", icon="📝"),
        ],
    },
    position="sidebar",
    expanded=True,
)

pg.run()
