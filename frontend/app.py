import streamlit as st
import requests
import pandas as pd
import os
import time
from typing import List, Dict, Any

# --- Fixed backend target (Azure) ---
API_BASE = "https://ai-journalist-backend-gnaygteve4g8bxft.australiaeast-01.azurewebsites.net/api"
ADMIN_TOKEN = os.environ.get("ADMIN_API_TOKEN", "1")

# Normalize API_BASE
def _normalize_base(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not url.rstrip("/").endswith("/api"):
        url = url.rstrip("/") + "/api"
    return url.rstrip("/")
API_BASE = _normalize_base(API_BASE)

st.set_page_config(page_title="AI Journalist — Dashboard", layout="wide")
st.title("📰 AI Journalist")

# Sidebar: Connection & Status
st.sidebar.header("📊 Status")
try:
    health = requests.get(f"{API_BASE}/health", timeout=5).json()
    st.sidebar.markdown(f"**Backend:** {'🟢 Healthy' if health['status'] == 'ok' else '🔴 Down'}")
except Exception as e:
    st.sidebar.markdown(f"**Backend:** 🔴 Down ({str(e)})")

# Optional admin token
admin_token_input = st.sidebar.text_input("Admin token (optional)", value=ADMIN_TOKEN, type="password")
if admin_token_input:
    ADMIN_TOKEN = admin_token_input
st.sidebar.code(API_BASE, language="text")

# --- Helpers ---
@st.cache_data(ttl=60)
def fetch_mentions(limit: int = 50, source: str = None, sentiment: str = None, flagged: bool = None) -> List[Dict[str, Any]]:
    """
    Fetch mentions from backend with filters. Cached for 60s.
    """
    url = f"{API_BASE}/mentions"
    params = {"limit": limit}
    if source:
        params["source"] = source
    if sentiment and sentiment != "All":
        params["sentiment"] = sentiment.lower()
    if flagged is not None:
        params["flagged"] = flagged
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        # Ensure keys expected by UI exist (handle nested article structure)
        for d in data:
            # Extract from nested article structure
            article = d.get("article", {})
            d["title"] = article.get("title", "(untitled)")
            d["url"] = article.get("link", "")
            d["source"] = article.get("source", "Unknown")
            d["summary"] = d.get("summary", "")
            d["sentiment"] = d.get("sentiment", "neutral")
            d["risk_score"] = d.get("risk_score", 0.0)
            d["id"] = d.get("id", 0)
            d["article_id"] = d.get("article_id", 0)
        return data
    except Exception as e:
        st.session_state.setdefault("_fetch_error", str(e))
        return []

def try_toast(msg: str):
    try:
        st.toast(msg)
    except Exception:
        st.info(msg)

# Tabs
tab = st.sidebar.selectbox("View", ["Mentions", "Operations"])

# --- Mentions tab ---
if tab == "Mentions":
    # Clear previous error
    st.session_state.pop("_fetch_error", None)
    
    # Dynamic Keyword Search (NEW!)
    st.subheader("🔍 Dynamic Keyword Search")
    keywords_input = st.text_area(
        "Keywords (one per line)", 
        placeholder="India\nOpenAI\nxAI", 
        height=100
    )
    articles_per_keyword = st.slider(
        "Articles per keyword", 
        min_value=1, 
        max_value=20, 
        value=5,
        help="Balance speed vs coverage"
    )
    
    # FETCH BY KEYWORDS BUTTON
    if st.button("🚀 FETCH BY KEYWORDS", type="primary"):
        keywords = [kw.strip() for kw in keywords_input.split("\n") if kw.strip()]
        if keywords:
            with st.spinner(f"Fetching articles for {len(keywords)} keywords..."):
                try:
                    params = [
                        ("keywords", kw) for kw in keywords
                    ] + [
                        ("per_keyword_limit", articles_per_keyword),
                        ("limit", 50)
                    ]
                    headers = {"x-admin-token": ADMIN_TOKEN}
                    r = requests.post(
                        f"{API_BASE}/ingest",
                        params=params,
                        headers=headers,
                        timeout=60
                    )
                    r.raise_for_status()
                    outcome = r.json()
                    
                    if outcome.get("status") == "success":
                        st.success(f"✅ Fetched **{outcome['inserted']}** articles from **{len(keywords)}** keywords!")
                        fetch_mentions.clear()
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(f"❌ Ingest failed: {outcome.get('message', 'Unknown error')}")
                except requests.exceptions.Timeout:
                    st.error("❌ Request timed out. Try fewer keywords or lower limit.")
                except Exception as e:
                    st.error(f"❌ Fetch failed: {str(e)}")
        else:
            st.error("⚠️ Please enter at least one keyword!")
    
    # Fetch mentions
    mentions = fetch_mentions(limit=50)
    fetch_error = st.session_state.pop("_fetch_error", None)
    if fetch_error:
        st.error(f"Failed to fetch mentions: {fetch_error}")
    if not mentions:
        st.info("No mentions found. Try the 'Dynamic Keyword Search' above!")
        st.stop()
    
    df = pd.DataFrame(mentions)
    
    # Sidebar filters for Mentions view
    st.sidebar.header("Mentions Filters")
    sentiment_options = sorted([s for s in df['sentiment'].dropna().unique() if s != ""])
    sentiment = st.sidebar.multiselect("Sentiment", options=sentiment_options, default=sentiment_options)
    source_q = st.sidebar.text_input("Source contains (substring)", "")
    query = st.sidebar.text_input("Search title/summary", "")
    
    # Apply filters
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
    
    st.subheader(f"🗞️ Mentions ({len(filtered)})")
    
    # Pagination controls
    per_page = st.selectbox("Per page", [5, 10, 20], index=1)
    max_page = max(1, (len(filtered) - 1) // per_page + 1)
    page = st.number_input("Page", min_value=1, max_value=max_page, value=1, step=1)
    start = (page - 1) * per_page
    end = start + per_page
    page_df = filtered.iloc[start:end]
    
    # Display mentions
    for _, row in page_df.iterrows():
        st.markdown("---")
        
        # Title with source (FIXED - handles nested article structure)
        title = row.get("title", "")
        article_url = row.get("url", "")
        source = row.get("source", "Unknown")
        
        if article_url and title:
            # Clean up the Google News RSS link (extract actual article URL)
            clean_title = title[:100] + "..." if len(title) > 100 else title
            st.markdown(f"### [{clean_title}]({article_url})")
            st.caption(f"*{source}*", help=article_url)
        else:
            st.markdown(f"### {title or '(untitled)'}")
            st.caption(f"*{source}*")
        
        # Summary
        summary = row.get("summary", "")
        if summary:
            st.write(f"📝 *{summary[:200]}...*")
        
        # Metrics
        sentiment = row.get('sentiment', 'neutral')
        risk_score = row.get('risk_score', 0.0)
        article_id = row.get('article_id', '')
        
        st.write(f"**Sentiment:** {sentiment.upper()} • **Risk:** {risk_score:.1f} • **Source:** {source}")
        
        # Action buttons
        cols = st.columns([1, 1, 6])
        with cols[0]:
            # 🔥 REAL FLAG BUTTON
            if st.button("🚩 Flag", key=f"flag-{row['id']}"):
                try:
                    headers = {"x-admin-token": ADMIN_TOKEN}
                    r = requests.post(
                        f"{API_BASE}/flag",
                        params={"article_id": article_id, "reason": "urgent"},
                        headers=headers,
                        timeout=10
                    )
                    if r.status_code == 200:
                        try_toast(f"✅ Flagged: {r.json().get('reason', 'urgent')}")
                        fetch_mentions.clear()
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        try_toast(f"❌ Flag failed: {r.status_code}")
                except Exception as e:
                    try_toast(f"❌ Flag error: {str(e)}")
        
        with cols[1]:
            # 🔥 REAL SUGGEST JOURNALIST BUTTON
            if st.button("🎯 Suggest journalist", key=f"suggest-{row['id']}"):
                try:
                    headers = {}
                    search_text = f"{title} {summary}".strip()[:500]
                    r = requests.get(
                        f"{API_BASE}/match",
                        params={"text": search_text, "top_k": 3},
                        timeout=10
                    )
                    if r.status_code == 200:
                        matches = r.json()
                        if matches:
                            with st.expander(f"🎯 Top {len(matches)} Journalist Matches", expanded=True):
                                for i, m in enumerate(matches, 1):
                                    score = m.get('score', 0)
                                    st.write(f"{i}. **{m.get('name', 'Unknown')}** ({m.get('outlet', 'Unknown')})")
                                    st.caption(f"Score: {score:.2f} | Topics: {m.get('topics', 'N/A')}")
                        else:
                            try_toast("No journalists found in database")
                    else:
                        try_toast(f"❌ Suggestion failed: {r.status_code}")
                except Exception as e:
                    try_toast(f"❌ Suggestion error: {str(e)}")
        
        with cols[2]:
            st.write(f"ID: {row.get('id')} • Article ID: {article_id}")
    
    st.markdown("---")
    st.caption("Azure demo — powered by AI Journalist API")

# --- Operations tab ---
elif tab == "Operations":
    st.header("⚙️ Operations")
    # Token is optional (backend doesn't enforce it)
    if not ADMIN_TOKEN:
        st.info("Admin token not set — proceeding (backend does not enforce it).")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Fetch new articles (ingest)"):
            try:
                headers = {
                    "Content-Type": "application/json",
                    **({"x-admin-token": ADMIN_TOKEN} if ADMIN_TOKEN else {}),
                }
                r = requests.post(
                    f"{API_BASE}/ingest",
                    headers=headers,
                    json={"source": "google", "limit": 10, "backfill_days": 2, "dry_run": False},
                    timeout=30,
                )
                r.raise_for_status()
                st.success("Ingest completed.")
                try:
                    fetch_mentions.clear()
                except Exception:
                    pass
                time.sleep(0.3)
                try:
                    st.rerun()
                except Exception:
                    raise
            except Exception as e:
                st.error(f"Ingest request failed: {e}")
    
    with col2:
        # Until a real /process route exists, reuse /ops/ingest so this button performs an action.
        if st.button("📝 Process mentions (temporary: re-run ingest)"):
            try:
                headers = {
                    "Content-Type": "application/json",
                    **({"x-admin-token": ADMIN_TOKEN} if ADMIN_TOKEN else {}),
                }
                r = requests.post(
                    f"{API_BASE}/ops/ingest",
                    headers=headers,
                    json={"source": "google", "limit": 10, "backfill_days": 2, "dry_run": False},
                    timeout=30,
                )
                r.raise_for_status()
                st.success("Re-ingest completed.")
                try:
                    fetch_mentions.clear()
                except Exception:
                    pass
                time.sleep(0.3)
                try:
                    st.rerun()
                except Exception:
                    raise
            except Exception as e:
                st.error(f"Process (alias) request failed: {e}")
    
    st.markdown("### Quick workflow")
    st.write("""
    1. Click **Fetch new articles (ingest)** to create/update demo data.
    2. The **Process** button re-runs ingest until a real `/process` API exists.
    3. Switch to **Mentions** to see results.
    """)
