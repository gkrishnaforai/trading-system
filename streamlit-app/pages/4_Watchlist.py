"""
Watchlist Management Page
Full CRUD operations for watchlists and watchlist items
"""
import streamlit as st
import sys
import os
import pandas as pd
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar
from api_client import get_go_api_client, APIError

setup_page_config("Watchlist Management", "📋")

st.title("📋 Watchlist Management")

# Sidebar
subscription_level = render_sidebar()

# Tabs for different operations
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 View", "➕ Create", "✏️ Update", "🗑️ Delete", "📊 Analytics"])

with tab1:
    st.subheader("View Watchlists")
    user_id = st.text_input("User ID", value="user1", key="view_watchlist_user")
    
    if st.button("Load Watchlists", key="load_watchlists"):
        if user_id:
            with st.spinner("Loading watchlists..."):
                try:
                    client = get_go_api_client()
                    response = client.get(f"api/v1/watchlists/user/{user_id}")
                    if response:
                        watchlists = response.get('watchlists', [])
                        st.success(f"✅ Found {len(watchlists)} watchlists")
                        
                        for watchlist in watchlists:
                            with st.expander(f"📋 {watchlist.get('watchlist_name', 'N/A')}"):
                                st.json(watchlist)
                except APIError as e:
                    st.error(f"❌ Error: {e}")

with tab2:
    st.subheader("Create Watchlist")
    user_id = st.text_input("User ID", value="user1", key="create_watchlist_user")
    watchlist_name = st.text_input("Watchlist Name", key="create_watchlist_name")
    watchlist_type = st.selectbox("Type", ["simple", "advanced", "smart"], key="create_watchlist_type")
    
    # Map watchlist type to subscription level
    # simple -> basic, advanced -> pro, smart -> elite
    subscription_level_map = {
        "simple": "basic",
        "advanced": "pro",
        "smart": "elite"
    }
    subscription_level_required = subscription_level_map.get(watchlist_type, "basic")
    
    if st.button("Create Watchlist", key="create_watchlist"):
        try:
            client = get_go_api_client()
            # user_id must be sent as query parameter, not in JSON body
            response = client.post(
                "api/v1/watchlists",
                params={"user_id": user_id},
                json_data={
                    "watchlist_name": watchlist_name,
                    "subscription_level_required": subscription_level_required
                }
            )
            st.success(f"✅ Watchlist created: {response.get('watchlist_id')}")
            st.json(response)
        except Exception as e:
            st.error(f"❌ Error: {e}")

with tab3:
    st.subheader("Update Watchlist")
    watchlist_id = st.text_input("Watchlist ID", key="update_watchlist_id")
    new_name = st.text_input("New Name", key="update_watchlist_name")
    
    if st.button("Update Watchlist", key="update_watchlist"):
        try:
            client = get_go_api_client()
            response = client.put(
                f"api/v1/watchlists/{watchlist_id}",
                json_data={"watchlist_name": new_name}
            )
            st.success("✅ Watchlist updated")
            st.json(response)
        except Exception as e:
            st.error(f"❌ Error: {e}")

with tab4:
    st.subheader("Delete Watchlist")
    watchlist_id = st.text_input("Watchlist ID", key="delete_watchlist_id")
    
    if st.button("Delete Watchlist", key="delete_watchlist", type="primary"):
        try:
            client = get_go_api_client()
            response = client.delete(f"api/v1/watchlists/{watchlist_id}")
            st.success("✅ Watchlist deleted")
            st.json(response)
        except Exception as e:
            st.error(f"❌ Error: {e}")

with tab5:
    st.subheader("Watchlist Analytics")
    st.info("📊 Watchlist analytics and performance metrics (Pro/Elite feature)")

