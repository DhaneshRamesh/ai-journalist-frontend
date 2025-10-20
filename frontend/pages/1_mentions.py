"""📰 Mentions Dashboard - Clickable Headlines + Sources + Analytics"""
import streamlit as st
import requests
import pandas as pd
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

# ─────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────

@st.cache_data(ttl=60)  # Cache 60 seconds
def fetch_mentions(limit=50):
    """Fetch mentions from backend API"""
    try:
        resp = requests.get(
            f"{BACKEND}/api/mentions?limit={limit}",
            timeout=15,
            headers={"User-Agent": "Streamlit/1.0"}
        )
        resp.raise_for_status()
        data = resp.json()
        return data
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Failed to fetch mentions: {e}")
        return []
    except Exception as e:
        st.error(f"❌ Unexpected error: {e}")
        return []

def domain_from_url(url: str | None) -> str:
    """Extract clean domain from URL (fallback for missing source)"""
    if not url:
        return "unknown"
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except:
        return "unknown"

def format_risk(risk: float | int | None) -> str:
    """Format risk score with color"""
    if risk is None:
        return "N/A"
    return f"{risk:.1f}"

# ─────────────────────────────
# MAIN UI
# ─────────────────────────────

st.title("📰 News Mentions Monitor")
st.markdown("**Real-time news tracking with AI sentiment & risk analysis**")

# ─────────────────────────────
# SIDEBAR: FILTERS & CONTROLS
# ─────────────────────────────

st.sidebar.header("🔍 Filters")
limit = st.sidebar.slider("Items to show", 10, 100, 25)
sources = st.sidebar.multiselect(
    "Filter sources",
    options=["reuters.com", "cnn.com", "bbc.com", "nytimes.com", "foxnews.com", "apnews.com", "theguardian.com"],
    default=[]
)
sentiment_filter = st.sidebar.selectbox(
    "Sentiment",
    options=["All", "positive", "negative", "neutral"],
    index=0
)

# Refresh button
if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# Ingest buttons (quick actions)
st.sidebar.markdown("---")
st.sidebar.subheader("🚀 Quick Actions")

if st.sidebar.button("🎭 Ingest Demo Data", use_container_width=True):
    try:
        resp = requests.post(
            f"{BACKEND}/api/ingest",
            json={"source": "demo", "limit": 5},
            timeout=30
        )
        if resp.status_code == 200:
            st.sidebar.success("✅ Demo data loaded!")
            st.cache_data.clear()
            st.rerun()
        else:
            st.sidebar.error(f"❌ Ingest failed: {resp.status_code}")
    except Exception as e:
        st.sidebar.error(f"❌ Request failed: {e}")

if st.sidebar.button("🌐 Ingest Google News", use_container_width=True):
    try:
        resp = requests.post(
            f"{BACKEND}/api/ingest",
            json={
                "source": "google",
                "keywords": ["AI", "journalism", "technology"],
                "limit": 20,
                "per_keyword_limit": 5
            },
            timeout=90
        )
        if resp.status_code == 200:
            result = resp.json()
            st.sidebar.success(f"✅ Ingested {result.get('inserted', 0)} articles!")
            st.cache_data.clear()
            st.rerun()
        else:
            st.sidebar.error(f"❌ Ingest failed: {resp.status_code}")
    except Exception as e:
        st.sidebar.error(f"❌ Request failed: {e}")

# Backend status
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
    mentions = fetch_mentions(limit)

# Handle empty state
if not mentions:
    st.warning("📭 **No mentions found**")
    st.info("""
    **Quick start:**
    1. Click **"🚀 Ingest Demo Data"** in sidebar (1 second)
    2. OR **"🌐 Ingest Google News"** (30-60 seconds)
    3. Refresh page → **See headlines appear!**
    """)
    st.stop()

# Apply filters
filtered_mentions = mentions.copy()

if sources:
    filtered_mentions = [
        m for m in filtered_mentions 
        if m.get("article", {}).get("source") in sources
    ]

if sentiment_filter != "All":
    filtered_mentions = [
        m for m in filtered_mentions 
        if m.get("sentiment") == sentiment_filter
    ]

# ─────────────────────────────
# METRICS DASHBOARD
# ─────────────────────────────

col1, col2, col3, col4, col5 = st.columns(5)
total_mentions = len(filtered_mentions)
unique_sources = len({m.get("article", {}).get("source") for m in filtered_mentions})
positive_count = sum(1 for m in filtered_mentions if m.get("sentiment") == "positive")
negative_count = sum(1 for m in filtered_mentions if m.get("sentiment") == "negative")
avg_risk = sum(m.get("risk_score", 0) for m in filtered_mentions) / max(total_mentions, 1)

with col1:
    st.metric("📊 Total Mentions", total_mentions)
with col2:
    st.metric("📰 Unique Sources", unique_sources)
with col3:
    st.metric("🟢 Positive", positive_count)
with col4:
    st.metric("🔴 Negative", negative_count)
with col5:
    st.metric("⚠️ Avg Risk", f"{avg_risk:.1f}")

st.markdown("---")

# ─────────────────────────────
# MENTIONS LIST - MAIN CONTENT
# ─────────────────────────────

st.subheader(f"🗞️ Latest Mentions ({len(filtered_mentions)} shown)")

for i, mention in enumerate(filtered_mentions):
    article = mention.get("article", {}) or {}
    title = article.get("title") or "(untitled)"
    link = article.get("link")
    source = article.get("source") or domain_from_url(link)
    summary = mention.get("summary", "")
    sentiment = mention.get("sentiment", "neutral")
    risk_score = mention.get("risk_score", 0)
    created_at = mention.get("created_at")
    
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
        
        # Summary (expandable)
        if summary:
            with st.expander("📝 Summary", expanded=False):
                st.write(summary)
        
        # Metrics row
        metric_col1, metric_col2, metric_col3 = st.columns([4, 2, 2])
        
        with metric_col1:
            st.markdown(f"{sentiment_emoji} **{sentiment.upper()}**")
            if created_at:
                st.caption(f"*{datetime.fromisoformat(created_at.replace('Z', '+00:00')):%H:%M}*")
        
        with metric_col2:
            st.metric("Risk Score", format_risk(risk_score))
        
        with metric_col3:
            entities = mention.get("named_entities", "")
            if entities:
                st.caption(f"👥 {entities[:50]}...")
        
        st.markdown("---")

# ─────────────────────────────
# ANALYTICS CHARTS
# ─────────────────────────────

st.markdown("---")
st.subheader("📈 Analytics")

# Source distribution
source_counts = {}
for m in filtered_mentions:
    src = m.get("article", {}).get("source", "unknown")
    source_counts[src] = source_counts.get(src, 0) + 1

if source_counts:
    source_df = pd.DataFrame([
        {"source": src, "count": count}
        for src, count in source_counts.items()
    ]).sort_values("count", ascending=False).head(10)
    
    col1, col2 = st.columns(2)
    
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
    
    with col2:
        # Sentiment pie
        sentiment_counts = {}
        for m in filtered_mentions:
            sent = m.get("sentiment", "unknown")
            sentiment_counts[sent] = sentiment_counts.get(sent, 0) + 1
        
        sentiment_df = pd.DataFrame([
            {"sentiment": sent, "count": count}
            for sent, count in sentiment_counts.items()
        ])
        
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
risk_scores = [m.get("risk_score", 0) for m in filtered_mentions if m.get("risk_score")]
if risk_scores:
    fig_hist = px.histogram(
        x=risk_scores,
        nbins=20,
        title="⚠️ Risk Score Distribution",
        labels={"x": "Risk Score"},
        color_discrete_sequence=["#3B82F6"]
    )
    st.plotly_chart(fig_hist, use_container_width=True)

# Footer
st.markdown("---")
st.markdown(
    """
    *Powered by [AI Journalist](https://github.com/DhaneshRamesh/ai-journalist)*  
    *Last updated: ~60s ago | 🔄 [Refresh](#)*
    """,
    unsafe_allow_html=True
)
