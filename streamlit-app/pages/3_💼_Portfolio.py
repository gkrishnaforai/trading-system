"""
Portfolio Management Page
Full CRUD operations for portfolios and holdings
"""
import streamlit as st
import sys
import os
import pandas as pd
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar
from shared_functions import get_portfolio_data
from api_client import get_go_api_client, APIError

setup_page_config("Portfolio Management", "💼")

st.title("💼 Portfolio Management")

# Sidebar
subscription_level = render_sidebar()

# Tabs for different operations
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 View", "➕ Create", "✏️ Update", "🗑️ Delete", "📊 Analytics"])

with tab1:
    st.subheader("View Portfolio")
    user_id = st.text_input("User ID", value="user1", key="view_user")
    portfolio_id = st.text_input("Portfolio ID", value="portfolio1", key="view_portfolio")
    
    if st.button("Load Portfolio", key="load_portfolio"):
        if user_id and portfolio_id:
            with st.spinner("Loading portfolio..."):
                try:
                    portfolio_data = get_portfolio_data(user_id, portfolio_id, subscription_level)
                    if portfolio_data:
                        portfolio = portfolio_data.get("portfolio") or {}
                        holdings = portfolio_data.get("holdings") or []
                        signals = portfolio_data.get("signals") or []
                        
                        st.success(f"✅ Portfolio loaded: {portfolio.get('portfolio_name', 'N/A')}")
                        
                        # Portfolio info
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Holdings", len(holdings))
                        with col2:
                            st.metric("Total Value", f"${portfolio.get('total_value', 0):,.2f}" if portfolio.get('total_value') else "N/A")
                        with col3:
                            st.metric("Signals", len(signals))
                        
                        # Holdings table
                        if holdings:
                            st.subheader("Holdings")
                            df_holdings = pd.DataFrame(holdings)
                            st.dataframe(df_holdings, use_container_width=True)
                        
                        # Signals
                        if signals and subscription_level in ["pro", "elite"]:
                            st.subheader("Trading Signals")
                            df_signals = pd.DataFrame(signals)
                            st.dataframe(df_signals, use_container_width=True)
                except APIError as e:
                    st.error(f"❌ Error: {e}")

with tab2:
    st.subheader("Create Portfolio")
    user_id = st.text_input("User ID", value="user1", key="create_user")
    portfolio_name = st.text_input("Portfolio Name", key="create_name")
    portfolio_type = st.selectbox("Type", ["long_term", "swing", "options"], key="create_type")
    
    if st.button("Create Portfolio", key="create_portfolio"):
        # Validate inputs
        user_id = user_id.strip() if user_id else ""
        portfolio_name = portfolio_name.strip() if portfolio_name else ""
        
        if not user_id:
            st.error("❌ User ID is required")
        elif not portfolio_name:
            st.error("❌ Portfolio Name is required")
        else:
            try:
                client = get_go_api_client()
                # user_id must be in URL path, not in JSON body
                # Route: POST /api/v1/portfolio/:user_id
                endpoint = f"api/v1/portfolio/{user_id}"
                response = client.post(
                    endpoint,
                    json_data={
                        "portfolio_name": portfolio_name
                    }
                )
                st.success(f"✅ Portfolio created: {response.get('portfolio_id')}")
                st.json(response)
            except APIError as e:
                st.error(f"❌ API Error: {e}")
                st.info(f"💡 Endpoint called: POST {endpoint}")
                st.info(f"💡 User ID: '{user_id}', Portfolio Name: '{portfolio_name}'")
            except Exception as e:
                st.error(f"❌ Error: {e}")

with tab3:
    st.subheader("Update Portfolio")
    user_id = st.text_input("User ID", value="user1", key="update_user")
    portfolio_id = st.text_input("Portfolio ID", key="update_id")
    new_name = st.text_input("New Name", key="update_name")
    notes = st.text_area("Notes", key="update_notes")
    
    if st.button("Update Portfolio", key="update_portfolio"):
        try:
            client = get_go_api_client()
            # user_id must be in URL path
            response = client.put(
                f"api/v1/portfolio/{user_id}/{portfolio_id}",
                json_data={"portfolio_name": new_name, "notes": notes}
            )
            st.success("✅ Portfolio updated")
            st.json(response)
        except Exception as e:
            st.error(f"❌ Error: {e}")

with tab4:
    st.subheader("Delete Portfolio")
    user_id = st.text_input("User ID", value="user1", key="delete_user")
    portfolio_id = st.text_input("Portfolio ID", key="delete_id")
    
    if st.button("Delete Portfolio", key="delete_portfolio", type="primary"):
        try:
            client = get_go_api_client()
            # user_id must be in URL path
            response = client.delete(f"api/v1/portfolio/{user_id}/{portfolio_id}")
            st.success("✅ Portfolio deleted")
            st.json(response)
        except Exception as e:
            st.error(f"❌ Error: {e}")

with tab5:
    st.subheader("Portfolio Analytics")
    st.info("📊 Portfolio analytics and performance metrics (Pro/Elite feature)")

