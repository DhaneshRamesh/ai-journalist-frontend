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
st.sidebar.code(API_BASE, language="text")
admin_token_input = st.sidebar.text_input("Admin token (optional)", value=ADMIN_TOKEN, type="password")
if admin_token_input:
    ADMIN_TOKEN = admin_token_input

# Helpers
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
        # Handle nested article structure
        for d in data:
            article = d.get("article", {})
            d["title"] = article.get("title", "(untitled)")
            d["url"] = article.get("link", "")
            d["source"] = article.get("source", "Unknown")
            d["summary"] = d.get("summary", "")
            d["sentiment"] = d.get("sentiment", "neutral")
            d["risk_score"] = d.get("risk_score", 0.0)
            d["id"] = d.get("id", 0)
            d["article_id"] = d.get("article_id", 0)
            d["flagged"] = d.get("flagged", False)
            d["flag_reason"] = d.get("flag_reason", "")
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

# --- Mentions Tab ---
if tab == "Mentions":
    st.header("Mentions")
    # Dynamic Keyword Search
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
    if st.button("🚀 FETCH BY KEYWORDS", type="primary"):
        keywords = [kw.strip() for kw in keywords_input.split("\n") if kw.strip()]
        if keywords:
            with st.spinner(f"Fetching articles for {len(keywords)} keywords..."):
                try:
                    params = [("keywords", kw) for kw in keywords] + [("per_keyword_limit", articles_per_keyword), ("limit", 50)]
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

    # Filters
    st.subheader("🔍 Filters")
    limit = st.number_input("Items to show", min_value=10, max_value=100, value=25)
    source_filter = st.multiselect("Filter sources", options=["nytimes.com", "reuters.com", "bloomberg.com", "inquirer.com", "fastcompany.com"], default=[])
    sentiment_filter = st.selectbox("Sentiment", options=["All", "positive", "negative", "neutral"], index=0)
    flagged_filter = st.checkbox("Show flagged articles only")

    # Fetch Mentions
    mentions = fetch_mentions(
        limit=limit,
        source=",".join(source_filter) if source_filter else None,
        sentiment=sentiment_filter,
        flagged=flagged_filter or None
    )
    fetch_error = st.session_state.pop("_fetch_error", None)
    if fetch_error:
        st.error(f"Failed to fetch mentions: {fetch_error}")
    if not mentions:
        st.info("No mentions found. Try the 'Dynamic Keyword Search' above!")
        st.stop()

    # Stats
    try:
        stats = requests.get(f"{API_BASE}/stats", timeout=5).json()
        st.subheader(f"🗞️ Latest Mentions ({len(mentions)} shown)")
        st.markdown(f"**Total Mentions:** {stats['total_mentions']}")
        st.markdown(f"**Unique Sources:** {len(set(m['source'] for m in mentions))}")
        st.markdown(f"**Positive:** {stats['sentiment_distribution'].get('positive', 0)}")
        st.markdown(f"**Negative:** {stats['sentiment_distribution'].get('negative', 0)}")
        st.markdown(f"**Avg Risk:** {sum(m['risk_score'] for m in mentions) / len(mentions) if mentions else 0:.1f}")
    except Exception as e:
        st.error(f"Failed to fetch stats: {str(e)}")

    # Mentions Table
    df = pd.DataFrame(mentions)
    per_page = st.selectbox("Per page", [5, 10, 20], index=1)
    max_page = max(1, (len(df) - 1) // per_page + 1)
    page = st.number_input("Page", min_value=1, max_value=max_page, value=1, step=1)
    start = (page - 1) * per_page
    end = start + per_page
    page_df = df.iloc[start:end]

    for _, row in page_df.iterrows():
        st.markdown("---")
        title = row["title"]
        url = row["url"]
        source = row["source"]
        if url and title:
            clean_title = title[:100] + "..." if len(title) > 100 else title
            st.markdown(f"[{clean_title}]({url})  <font color='#6f6f6f'>{source}</font>", unsafe_allow_html=True)
        else:
            st.markdown(f"{title or '(untitled)'}  <font color='#6f6f6f'>{source}</font>", unsafe_allow_html=True)
        st.write(f"📝 Summary: {row['summary'][:100]}...")
        st.write(f"**Sentiment:** {row['sentiment'].upper()} • **Risk:** {row['risk_score']:.1f} • **Source:** {source}")
        if row.get("flagged", False):
            st.markdown(f"🚩 **Flagged: {row.get('flag_reason', 'urgent')}**")
        cols = st.columns([1, 1, 6])
        with cols[0]:
            # 🔥 REAL FLAG BUTTON
            if st.button("🚩 Flag", key=f"flag-{row['id']}", disabled=row.get("flagged", False)):
                try:
                    r = requests.post(
                        f"{API_BASE}/flag",
                        params={"article_id": row['article_id'], "reason": "urgent"},
                        headers={"x-admin-token": ADMIN_TOKEN},
                        timeout=10
                    )
                    r.raise_for_status()
                    try_toast(f"✅ Flagged: {r.json()['reason']}")
                    fetch_mentions.clear()
                    time.sleep(0.3)
                    st.rerun()
                except Exception as e:
                    try_toast(f"Flag failed: {str(e)}")
        with cols[1]:
            # 🔥 REAL SUGGEST JOURNALIST BUTTON
            if st.button("🎯 Suggest journalist", key=f"suggest-{row['id']}"):
                try:
                    r = requests.get(
                        f"{API_BASE}/match",
                        params={"text": row['title'] + " " + row['summary'], "top_k": 3},
                        timeout=10
                    )
                    r.raise_for_status()
                    matches = r.json()
                    if matches:
                        with st.expander(f"🎯 Top {len(matches)} Journalist Matches", expanded=True):
                            for i, m in enumerate(matches, 1):
                                score = m.get('score', 0)
                                st.write(f"{i}. **{m.get('name', 'Unknown')}** ({m.get('outlet', 'Unknown')})")
                                st.caption(f"Score: {score:.2f} | Topics: {m.get('topics', 'N/A')}")
                    else:
                        try_toast("No journalists found in database")
                except Exception as e:
                    try_toast(f"Suggestion failed: {str(e)}")
        with cols[2]:
            st.write(f"ID: {row['id']} • Article ID: {row['article_id']}")
    st.markdown("---")
    st.caption("Azure demo — powered by AI Journalist API")

# --- Operations Tab ---
elif tab == "Operations":
    st.header("⚙️ Operations")
    if not ADMIN_TOKEN:
        st.info("Admin token not set — proceeding (backend does not enforce it).")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Fetch new articles (ingest)"):
            try:
                r = requests.post(
                    f"{API_BASE}/ingest",
                    headers={
                        "Content-Type": "application/json",
                        **({"x-admin-token": ADMIN_TOKEN} if ADMIN_TOKEN else {}),
                    },
                    json={"source": "google", "limit": 10, "backfill_days": 2, "dry_run": False},
                    timeout=30,
                )
                r.raise_for_status()
                st.success("Ingest completed.")
                fetch_mentions.clear()
                time.sleep(0.3)
                st.rerun()
            except Exception as e:
                st.error(f"Ingest failed: {str(e)}")
    with col2:
        if st.button("📝 Process mentions (temporary: re-run ingest)"):
            try:
                r = requests.post(
                    f"{API_BASE}/ops/ingest",
                    headers={
                        "Content-Type": "application/json",
                        **({"x-admin-token": ADMIN_TOKEN} if ADMIN_TOKEN else {}),
                    },
                    json={"source": "google", "limit": 10, "backfill_days": 2, "dry_run": False},
                    timeout=30,
                )
                r.raise_for_status()
                st.success("Re-ingest completed.")
                fetch_mentions.clear()
                time.sleep(0.3)
                st.rerun()
            except Exception as e:
                st.error(f"Process (alias) failed: {str(e)}")
    st.markdown("### Quick workflow")
    st.write("""
    1. Click **Fetch new articles (ingest)** to create/update demo data.
    2. The **Process** button re-runs ingest until a real `/process` API exists.
    3. Switch to **Mentions** to see results.
    """)
