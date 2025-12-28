"""
Blog Generation Page (Elite & Admin)
AI-powered blog generation for market insights
"""
import streamlit as st
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import setup_page_config, render_sidebar
from api_client import get_python_api_client, APIError

setup_page_config("Blog Generation", "📝")

st.title("📝 Blog Generation (Elite & Admin)")

# Sidebar
subscription_level = render_sidebar()

if subscription_level not in ["elite", "admin"]:
    st.warning("⚠️ Blog Generation is available for Elite and Admin users only.")
    st.info("💡 Upgrade to Elite to access blog generation features.")
else:
    col1, col2 = st.columns([1, 1])
    
    with col1:
        user_id = st.text_input("User ID", value="user1", key="blog_user")
        symbol = st.text_input("Symbol (optional)", key="blog_symbol")
        topic_type = st.selectbox("Topic Type", ["signal_change", "trend_breakout", "earnings_alert"], key="blog_topic")
        
        if st.button("Generate Blog", key="generate_blog", type="primary"):
            try:
                client = get_python_api_client()
                payload = {
                    "user_id": user_id,
                    "topic_type": topic_type
                }
                if symbol:
                    payload["symbol"] = symbol
                
                with st.spinner("Generating blog... This may take 30-60 seconds."):
                    response = client.post("api/v1/blog/generate", json=payload)
                    if response:
                        st.session_state["blog_result"] = response
                        st.success("✅ Blog generated!")
                        st.rerun()
            except Exception as e:
                st.error(f"❌ Error: {e}")
    
    with col2:
        if "blog_result" in st.session_state:
            st.subheader("Generated Blog")
            result = st.session_state["blog_result"]
            if result.get('draft'):
                draft = result['draft']
                st.write(f"**Title:** {draft.get('title', 'N/A')}")
                st.write(f"**Slug:** {draft.get('slug', 'N/A')}")
                st.markdown(f"**Content:**\n\n{draft.get('content', 'N/A')}")
                st.write(f"**Tags:** {', '.join(draft.get('tags', []))}")
            else:
                st.json(result)

