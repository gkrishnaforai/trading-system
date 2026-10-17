"""
Blog Generation Page (Elite & Admin)
Post engine — deterministic insights published to /insights
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

st.title("📝 Insights / Blog Generation (Elite & Admin)")

# Sidebar
subscription_level = render_sidebar()

if subscription_level not in ["elite", "admin"]:
    st.warning("⚠️ Blog generation is available for Elite and Admin users only.")
    st.info("💡 Upgrade to Elite to access blog generation features.")
else:
    client = get_python_api_client()

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Generate")
        st.caption(
            "Posts are deterministic — built from journaled regime "
            "snapshots, graded board calls, and stock health cards. "
            "Idempotent by slug; re-running refreshes today's posts.")
        sym = st.text_input("Mover explainer for symbol (optional)",
                            key="post_sym").strip().upper()
        if st.button("Generate posts", type="primary",
                     key="gen_posts"):
            try:
                path = "api/v1/board/posts/generate"
                if sym:
                    path += f"?sym={sym}"
                res = client.post(path)
                st.session_state["post_gen"] = res
                st.success("✅ Posts generated")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Generation failed: {e}")
        if st.session_state.get("post_gen"):
            st.json(st.session_state["post_gen"].get("generated", {}))

    with col2:
        st.subheader("Published")
        kind = st.selectbox(
            "Kind",
            ["all", "daily_brief", "receipts", "mover",
             "event_verdict", "explainer"],
            key="post_kind")
        try:
            q = "api/v1/board/posts?limit=50"
            if kind != "all":
                q += f"&kind={kind}"
            data = client.get(q)
            posts = (data or {}).get("posts", [])
            if not posts:
                st.info("No posts yet — hit Generate posts.")
            for p in posts:
                with st.expander(
                        f"{p.get('as_of','')} · {p.get('kind','')} — "
                        f"{p.get('title','')}"):
                    st.caption(p.get("dek") or "")
                    try:
                        full = client.get(
                            f"api/v1/board/posts/{p['slug']}")
                        st.markdown(full.get("body_md", ""))
                    except Exception as e:
                        st.warning(f"couldn't load body: {e}")
        except Exception as e:
            st.error(f"❌ Failed to list posts: {e}")
