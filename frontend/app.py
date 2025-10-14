# frontend/app.py
import streamlit as st
import requests
import pandas as pd
import os
import time
from typing import List, Dict, Any, Optional

# --- Config ---
API_BASE_DEFAULT = "http://127.0.0.1:8000/api"
API_BASE = os.environ.get("API_BASE", API_BASE_DEFAULT)
ADMIN_TOKEN = os.environ.get("ADMIN_API_TOKEN", "")

st.set_page_config(page_title="AI Journalist — Dashboard", layout="wide")
st.title("📰 AI Journalist")

tab = st.sidebar.selectbox("View", ["Mentions", "Operations"])

st.sidebar.markdown("### Connection")
api_base_input = st.sidebar.text_input("API base URL", value=API_BASE)
API_BASE = api_base_input.rstrip("/")
admin_token_input = st.sidebar.text_input("Admin token (optional)", value=ADMIN_TOKEN, type="password")
if admin_token_input:
    ADMIN_TOKEN = admin_token_input

# --- Helpers ---
@st.cache_data(ttl=60)
def fetch_mentions() -> List[Dict[str, Any]]:
    """
    Fetch mentions from backend. Cached for a short TTL to avoid spamming the API.
    Use fetch_mentions.clear() when you want to force a refresh (ingest/process).
    """
    url = f"{API_BASE}/mentions"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        # Ensure keys expected by UI exist
        for d in data:
            d.setdefault("title", "")
            d.setdefault("summary", "")
            d.setdefault("sentiment", "")
            d.setdefault("risk_score", None)
            d.setdefault("source", "")
            d.setdefault("url", "")
        return data
    except Exception as e:
        st.session_state.setdefault("_fetch_error", str(e))
        return []

def try_toast(msg: str):
    # streamlit.toast is available in some versions; fallback to info
    try:
        st.toast(msg)
    except Exception:
        st.info(msg)

# --- Mentions tab ---
if tab == "Mentions":
    # clear previous error
    st.session_state.pop("_fetch_error", None)
    mentions = fetch_mentions()
    fetch_error = st.session_state.pop("_fetch_error", None)

    if fetch_error:
        st.error(f"Failed to fetch mentions: {fetch_error}")
    if not mentions:
        st.info("No mentions found.")
        st.stop()

    df = pd.DataFrame(mentions)

    # Sidebar filters for Mentions view
    st.sidebar.header("Mentions Filters")
    sentiment_options = sorted(df['sentiment'].dropna().unique())
    sentiment = st.sidebar.multiselect("Sentiment", options=sentiment_options, default=sentiment_options)
    source_q = st.sidebar.text_input("Source contains (substring)", "")
    query = st.sidebar.text_input("Search title/summary", "")

    filtered = df.copy()
    if sentiment:
        filtered = filtered[filtered['sentiment'].isin(sentiment)]
    if source_q:
        filtered = filtered[filtered['source'].str.contains(source_q, case=False, na=False)]
    if query:
        filtered = filtered[
            filtered['title'].str.contains(query, case=False, na=False) |
            filtered['summary'].str.contains(query, case=False, na=False)
        ]

    st.subheader(f"Mentions ({len(filtered)})")

    # Pagination controls
    per_page = st.selectbox("Per page", [5, 10, 20], index=1)
    max_page = max(1, (len(filtered) - 1) // per_page + 1)
    page = st.number_input("Page", min_value=1, max_value=max_page, value=1, step=1)
    start = (page - 1) * per_page
    end = start + per_page
    page_df = filtered.iloc[start:end]

    for _, row in page_df.iterrows():
        st.markdown("---")
        title = row.get("title", "")
        url = row.get("url", "")
        if url:
            st.markdown(f"### [{title}]({url})")
        else:
            st.markdown(f"### {title}")
        st.write(row.get("summary", ""))
        st.write(f"**Sentiment:** {row.get('sentiment')}  •  **Risk:** {row.get('risk_score')}  •  **Source:** {row.get('source')}")
        cols = st.columns([1, 1, 6])
        with cols[0]:
            if st.button("Flag", key=f"flag-{row['id']}"):
                try_toast("Flagged (demo)")
        with cols[1]:
            if st.button("Suggest journalist", key=f"suggest-{row['id']}"):
                try_toast("Suggestion (demo)")
        with cols[2]:
            st.write(f"ID: {row.get('id')} • Article ID: {row.get('article_id')}")

    st.markdown("---")
    st.caption("Local demo — powered by AI Journalist API")

# --- Operations tab ---
elif tab == "Operations":
    st.header("⚙️ Operations")

    if not ADMIN_TOKEN:
        st.sidebar.markdown("#### Admin token (local dev)")
        ui_token = st.sidebar.text_input("Paste admin token here", type="password")
        if ui_token:
            ADMIN_TOKEN = ui_token

    if not ADMIN_TOKEN:
        st.warning("ADMIN API token not provided — operations disabled. Paste token in sidebar or set ADMIN_API_TOKEN env var.")
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Fetch new articles (ingest)"):
            try:
                r = requests.post(f"{API_BASE}/ingest", headers={"X-ADMIN-TOKEN": ADMIN_TOKEN}, timeout=15)
                if r.status_code == 200:
                    st.success("Ingest started (background).")
                    # clear cached mentions and rerun so Mentions tab shows new data immediately
                    try:
                        fetch_mentions.clear()
                    except Exception:
                        pass
                    # short pause to allow backend to update in-memory store
                    time.sleep(0.3)
                    # use the correct rerun API depending on streamlit version
                    try:
                        st.rerun()
                    except Exception:
                        # fallback: raise an exception to force reload in older versions
                        raise
                else:
                    st.error(f"Ingest API error: {r.status_code} {r.text}")
            except Exception as e:
                st.error(f"Ingest request failed: {e}")

    with col2:
        if st.button("📝 Process mentions (summarize)"):
            try:
                r = requests.post(f"{API_BASE}/process", headers={"X-ADMIN-TOKEN": ADMIN_TOKEN}, timeout=15)
                if r.status_code == 200:
                    st.success("Processing started (background).")
                    try:
                        fetch_mentions.clear()
                    except Exception:
                        pass
                    time.sleep(0.3)
                    try:
                        st.rerun()
                    except Exception:
                        raise
                else:
                    st.error(f"Process API error: {r.status_code} {r.text}")
            except Exception as e:
                st.error(f"Process request failed: {e}")

    st.markdown("### Quick workflow")
    st.write("""
    1. Click **Fetch new articles (ingest)** to pull the latest feeds.  
    2. Click **Process mentions (summarize)** to create/refresh mentions.  
    3. Switch to **Mentions** tab (or the UI will auto-switch) and refresh to see new results.
    """)
