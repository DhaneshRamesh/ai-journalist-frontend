import streamlit as st
import requests
import pandas as pd
import os
from urllib.parse import urlparse
import plotly.express as px
from datetime import datetime, timedelta
import time

# Page config
st.set_page_config(page_title="📰 Mentions", layout="wide")

# Backend URL from session state (set in app.py sidebar)
BACKEND = st.session_state.get(
    "backend_url",
    "https://ai-journalist-backend-gnaygteve4g8bxft.australiaeast-01.azurewebsites.net"
)
ADMIN_TOKEN = st.session_state.get("admin_token", os.environ.get("ADMIN_API_TOKEN", "1"))

# ─────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────
@st.cache_data(ttl=60)  # Cache 60 seconds
def fetch_mentions(limit=50, sources=None, sentiment=None, flagged=None):
    """Fetch mentions from backend API with filters."""
    try:
        params = {"limit": limit}
        if sources:
            params["source"] = ",".join(sources)
        if sentiment and sentiment != "All":
            params["sentiment"] = sentiment.lower()
        if flagged is not None:
            params["flagged"] = flagged
        resp = requests.get(
            f"{BACKEND}/api/mentions",
            params=params,
            headers={"User-Agent": "Streamlit/1.0"},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        # Normalize data
        for m in data:
            article = m.get("article", {})
            m["title"] = article.get("title", "(untitled)")
            m["link"] = article.get("link", "")
            m["source"] = article.get("source") or domain_from_url(m["link"])
            raw_summary = m.get("summary", "")
            # Check if summary is a URL
            m["summary"] = "(No summary available)" if raw_summary.startswith(("http://", "https://")) else raw_summary
            m["raw_summary"] = raw_summary  # Debug field
            m["sentiment"] = m.get("sentiment", "neutral")
            m["sentiment_confidence"] = m.get("sentiment_confidence", 0.0)
            m["risk_score"] = m.get("risk_score", 0.0)
            m["id"] = m.get("id", 0)
            m["article_id"] = m.get("article_id", 0)
            m["flagged"] = m.get("flagged", False)
            m["flag_reason"] = m.get("flag_reason", "")
            m["flagged_at"] = m.get("flagged_at", None)
        return data
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Failed to fetch mentions: {e}")
        return []
    except Exception as e:
        st.error(f"❌ Unexpected error: {e}")
        return []

def ingest_by_keywords(keywords, per_keyword_limit=5):
    """Dynamic ingestion by user keywords (QUERY PARAMS)."""
    try:
        params = [("keywords", kw) for kw in keywords] + [("per_keyword_limit", per_keyword_limit)]
        headers = {"x-admin-token": ADMIN_TOKEN}
        resp = requests.post(
            f"{BACKEND}/api/ingest",
            params=params,
            headers=headers,
            timeout=120
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"❌ Keyword ingest failed: {e}")
        return None

def domain_from_url(url: str | None) -> str:
    """Extract clean domain from URL."""
    if not url:
        return "unknown"
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except:
        return "unknown"

def format_risk(risk: float | int | None) -> str:
    """Format risk score with color-coded emoji."""
    if risk is None:
        return "N/A"
    color = "🟥" if risk >= 0.7 else "🟧" if risk >= 0.4 else "🟩"
    return f"{color} {risk:.2f}"

# ─────────────────────────────
# MAIN UI
# ─────────────────────────────
st.title("📰 News Mentions Monitor")
st.markdown("**Real-time news tracking with AI sentiment & risk analysis**")

# Debug: Show raw summary for first mention
if st.checkbox("Show raw summary (debug)"):
    mentions_debug = fetch_mentions(limit=1)
    if mentions_debug:
        st.write("Raw summary (first mention):", mentions_debug[0].get("raw_summary", "N/A"))

# ─────────────────────────────
# SIDEBAR: FILTERS & CONTROLS
# ─────────────────────────────
st.sidebar.header("🔍 Dynamic Keyword Search")
st.sidebar.markdown("**Type keywords → Fetch fresh Google News!**")
keywords_input = st.sidebar.text_area(
    "Keywords (one per line):",
    value="AI\njournalism\nstartups\nclimate change\nOpenAI",
    height=100,
    help="Enter keywords or phrases (e.g., 'climate change'). Click FETCH to get Google News RSS!"
)
articles_per_keyword = st.sidebar.slider(
    "Articles per keyword:",
    min_value=1,
    max_value=20,
    value=5,
    help="5-10 recommended for speed"
)
if st.sidebar.button("🚀 FETCH BY KEYWORDS", type="primary", use_container_width=True):
    keywords = [kw.strip() for kw in keywords_input.split("\n") if kw.strip()]
    if keywords:
        with st.spinner(f"🔍 Fetching {len(keywords)} keywords from Google News..."):
            result = ingest_by_keywords(keywords, articles_per_keyword)
            if result and result.get("status") == "success":
                inserted = result.get("inserted", 0)
                st.sidebar.success(f"✅ Fetched **{inserted}** articles from **{len(keywords)}** keywords!")
                st.session_state.last_keywords = keywords
                st.cache_data.clear()
                st.rerun()
            else:
                st.sidebar.error("❌ Fetch failed!")
    else:
        st.sidebar.error("⚠️ Enter at least one keyword!")

st.sidebar.markdown("---")
st.sidebar.header("🔍 Filters")
limit = st.sidebar.slider("Items to show", 10, 100, 25)
# Dynamically fetch sources
mentions = fetch_mentions(limit=100)  # Fetch more to get unique sources
unique_sources = sorted({m["source"] for m in mentions if m["source"] != "unknown"})
sources = st.sidebar.multiselect("Filter sources", options=unique_sources, default=[])
sentiment_filter = st.sidebar.selectbox(
    "Sentiment",
    options=["All", "Positive", "Negative", "Neutral"],
    index=0
)
flagged_filter = st.sidebar.checkbox("Show flagged articles only")
if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🚀 Quick Actions")
if st.sidebar.button("🎭 Ingest Demo Data", use_container_width=True):
    try:
        resp = requests.post(
            f"{BACKEND}/api/ingest",
            json={"source": "demo", "limit": 5},
            headers={"x-admin-token": ADMIN_TOKEN},
            timeout=30
        )
        resp.raise_for_status()
        st.sidebar.success("✅ Demo data loaded!")
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"❌ Ingest failed: {e}")

if st.sidebar.button("🌐 Legacy Google News", use_container_width=True):
    try:
        resp = requests.post(
            f"{BACKEND}/api/ingest",
            json={
                "source": "google",
                "keywords": ["AI", "journalism", "technology"],
                "limit": 20,
                "per_keyword_limit": 5
            },
            headers={"x-admin-token": ADMIN_TOKEN},
            timeout=90
        )
        resp.raise_for_status()
        result = resp.json()
        st.sidebar.success(f"✅ Legacy ingest: {result.get('inserted', 0)} articles!")
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"❌ Legacy ingest failed: {e}")

st.sidebar.markdown("---")
st.sidebar.subheader("📊 Status")
try:
    health_resp = requests.get(f"{BACKEND}/api/health", timeout=5)
    if health_resp.status_code == 200:
        st.sidebar.success("🟢 Backend: Healthy")
    else:
        st.sidebar.error("🔴 Backend: Unhealthy")
except:
    st.sidebar.error("🔴 Backend: Unreachable")

# ─────────────────────────────
# DATA FETCHING & PROCESSING
# ─────────────────────────────
with st.spinner("Loading latest mentions..."):
    mentions = fetch_mentions(limit=limit, sources=sources, sentiment=sentiment_filter, flagged=flagged_filter)

if not mentions:
    st.warning("📭 **No mentions found**")
    st.info("""
    **🚀 Quick start:**
    1. **Type keywords** in sidebar: `OpenAI` / `climate change` / `xAI`
    2. **Adjust slider**: 5-10 articles per keyword
    3. **Click 🚀 FETCH BY KEYWORDS** (30-60 seconds)
    4. **OR** click **"Ingest Demo Data"** (1 second)
    """)
    st.stop()

# Apply filters
filtered_mentions = mentions.copy()

# ─────────────────────────────
# METRICS DASHBOARD
# ─────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)
total_mentions = len(filtered_mentions)
unique_sources = len({m["source"] for m in filtered_mentions if m["source"] != "unknown"})
positive_count = sum(1 for m in filtered_mentions if m["sentiment"] == "positive")
negative_count = sum(1 for m in filtered_mentions if m["sentiment"] == "negative")
avg_risk = sum(m["risk_score"] for m in filtered_mentions) / max(total_mentions, 1)
with col1:
    st.metric("📊 Total Mentions", total_mentions)
with col2:
    st.metric("📰 Unique Sources", unique_sources)
with col3:
    st.metric("🟢 Positive", positive_count)
with col4:
    st.metric("🔴 Negative", negative_count)
with col5:
    st.metric("⚠️ Avg Risk", f"{avg_risk:.2f}")

if 'last_keywords' in st.session_state:
    st.info(f"🔍 **Last search:** {', '.join(st.session_state.last_keywords)}")
st.markdown("---")

# ─────────────────────────────
# MENTIONS LIST - MAIN CONTENT
# ─────────────────────────────
st.subheader(f"🗞️ Latest Mentions ({len(filtered_mentions)} shown)")
for i, mention in enumerate(filtered_mentions):
    article = mention.get("article", {}) or {}
    title = mention.get("title", "(untitled)")
    link = mention.get("link")
    source = mention.get("source", "unknown")
    summary = mention.get("summary", "")
    sentiment = mention.get("sentiment", "neutral")
    sentiment_confidence = mention.get("sentiment_confidence", 0.0)
    risk_score = mention.get("risk_score", 0)
    created_at = mention.get("created_at")
    flagged = mention.get("flagged", False)
    flag_reason = mention.get("flag_reason", "")

    # Truncate long summaries
    if summary and len(summary) > 200:
        summary = summary[:200] + "..."

    # Sentiment styling
    sentiment_colors = {
        "positive": "🟢",
        "negative": "🔴",
        "neutral": "⚪"
    }
    sentiment_emoji = sentiment_colors.get(sentiment, "⚪")

    # Container for each mention
    with st.container():
        # Headline + Source
        headline_col1, headline_col2 = st.columns([1, 6])
        with headline_col1:
            st.markdown(f"**{i+1}.**")
        with headline_col2:
            if link:
                st.markdown(f"**🔗 [{title}]({link})**")
                st.caption(f"*{source}*", help=link)
            else:
                st.markdown(f"**📄 {title}**")
                st.caption(f"*{source}*")

        # Summary
        if summary and summary != "(No summary available)":
            with st.expander("📝 Summary", expanded=False):
                st.markdown(summary, unsafe_allow_html=True)
        else:
            st.write("📝 No summary available")

        # Metrics and Actions
        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns([4, 2, 2, 2])
        with metric_col1:
            st.markdown(f"{sentiment_emoji} **{sentiment.upper()} ({sentiment_confidence:.2f})**")
            if created_at:
                st.caption(f"*{datetime.fromisoformat(created_at.replace('Z', '+00:00')):%H:%M}*")
        with metric_col2:
            st.markdown(f"**{format_risk(risk_score)}**")
        with metric_col3:
            if flagged:
                st.markdown(f"🚩 **Flagged: {flag_reason}**")
            elif st.button("🚩 Flag", key=f"flag-{mention['id']}"):
                try:
                    resp = requests.post(
                        f"{BACKEND}/api/flag",
                        params={"article_id": mention['article_id'], "reason": "urgent"},
                        headers={"x-admin-token": ADMIN_TOKEN},
                        timeout=10
                    )
                    resp.raise_for_status()
                    st.success(f"✅ Flagged: {resp.json()['reason']}")
                    st.cache_data.clear()
                    time.sleep(0.3)
                    st.rerun()
                except Exception as e:
                    st.error(f"Flag failed: {e}")
        with metric_col4:
            if st.button("🎯 Suggest Journalist", key=f"suggest-{mention['id']}"):
                try:
                    resp = requests.get(
                        f"{BACKEND}/api/match",
                        params={"text": title + " " + summary, "top_k": 3},
                        timeout=10
                    )
                    resp.raise_for_status()
                    matches = resp.json()
                    if matches:
                        with st.expander(f"🎯 Top {len(matches)} Journalist Matches", expanded=True):
                            for j, m in enumerate(matches, 1):
                                st.write(f"{j}. **{m.get('name', 'Unknown')}** ({m.get('outlet', 'Unknown')})")
                                st.caption(f"Score: {m.get('score', 0):.2f} | Topics: {m.get('topics', 'N/A')}")
                    else:
                        st.info("No journalists found in database")
                except Exception as e:
                    st.error(f"Suggestion failed: {e}")
        st.markdown("---")

# ─────────────────────────────
# ANALYTICS CHARTS
# ─────────────────────────────
st.markdown("---")
st.subheader("📈 Analytics")
col1, col2 = st.columns(2)

# Source distribution
source_counts = {}
for m in filtered_mentions:
    src = m.get("source", "unknown")
    source_counts[src] = source_counts.get(src, 0) + 1
if source_counts:
    source_df = pd.DataFrame([
        {"source": src, "count": count}
        for src, count in source_counts.items()
    ]).sort_values("count", ascending=False).head(10)
    with col1:
        fig_bar = px.bar(
            source_df,
            x="count",
            y="source",
            orientation="h",
            title="🗞️ Top Sources",
            color="count",
            color_continuous_scale="Viridis",
            height=400
        )
        fig_bar.update_layout(margin={"t": 40, "b": 20, "l": 0, "r": 0})
        st.plotly_chart(fig_bar, use_container_width=True)

# Sentiment pie
sentiment_counts = {}
for m in filtered_mentions:
    sent = m.get("sentiment", "unknown")
    sentiment_counts[sent] = sentiment_counts.get(sent, 0) + 1
if sentiment_counts:
    sentiment_df = pd.DataFrame([
        {"sentiment": sent, "count": count}
        for sent, count in sentiment_counts.items()
    ])
    with col2:
        fig_pie = px.pie(
            sentiment_df,
            values="count",
            names="sentiment",
            title="😊 Sentiment Distribution",
            color_discrete_map={
                "positive": "#10B981",
                "negative": "#EF4444",
                "neutral": "#6B7280",
                "unknown": "#9CA3AF"
            }
        )
        st.plotly_chart(fig_pie, use_container_width=True)

# Risk distribution histogram
risk_scores = [m.get("risk_score", 0) for m in filtered_mentions if m.get("risk_score") is not None]
if risk_scores:
    risk_df = pd.DataFrame({"risk_score": risk_scores})
    fig_hist = px.histogram(
        risk_df,
        x="risk_score",
        nbins=20,
        title="⚠️ Risk Score Distribution",
        labels={"risk_score": "Risk Score"},
        color_discrete_sequence=["#3B82F6"],
        color="risk_score",
        color_continuous_scale=["#10B981", "#F59E0B", "#EF4444"]  # Green to red
    )
    st.plotly_chart(fig_hist, use_container_width=True)

# Footer
st.markdown("---")
st.markdown(
    """
    *Powered by [AI Journalist](https://github.com/DhaneshRamesh/ai-journalist)*
    *Dynamic Google News RSS + FastAPI 🚀*
    *Last updated: ~60s ago | 🔄 [Refresh](#)*
    """,
    unsafe_allow_html=True
)
