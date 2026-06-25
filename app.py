"""
app.py — Streamlit dashboard for the Anveshan Review & CX Intelligence prototype.

Reads ONLY pre-computed artifacts in data/processed/ (no scraping, no live LLM calls).
The founder brief and alerts are computed on the full snapshot; the "Explore" charts
respond to the sidebar filters.

Run:  streamlit run app.py
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src import config

st.set_page_config(page_title="Anveshan Review & CX Intelligence", layout="wide")


@st.cache_data
def load_enriched():
    df = pd.read_csv(config.REVIEWS_ENRICHED_CSV)
    df["date"] = pd.to_datetime(df["review_date"], errors="coerce")
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["themes_list"] = df["themes"].apply(
        lambda s: json.loads(s) if isinstance(s, str) and s.strip() else [])
    return df


@st.cache_data
def load_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_text(path):
    return path.read_text(encoding="utf-8") if path.exists() else None


# --- guard: artifacts must exist --------------------------------------------
if not config.REVIEWS_ENRICHED_CSV.exists():
    st.title("Anveshan Review & CX Intelligence")
    st.error("No processed data found. Run the pipeline first:  `python -m src.pipeline`")
    st.stop()

df = load_enriched()
stats = load_json(config.STATS_JSON) or {}
alerts = load_json(config.ALERTS_JSON) or []
brief_md = load_text(config.BRIEF_MD)

# --- header + provenance banner ---------------------------------------------
st.title("🛒 Anveshan Review & CX Intelligence")
st.warning("⚠️ " + config.PROTOTYPE_BANNER)

# --- sidebar filters --------------------------------------------------------
st.sidebar.header("Filters")
sizes = sorted(df["size"].dropna().unique())
pick_sizes = st.sidebar.multiselect("Size variant (SKU)", sizes, default=sizes)
sentiments = sorted(df["sentiment"].dropna().unique())
pick_sent = st.sidebar.multiselect("Sentiment", sentiments, default=sentiments)
min_d, max_d = df["date"].min().date(), df["date"].max().date()
date_range = st.sidebar.date_input("Review date range", value=(min_d, max_d),
                                   min_value=min_d, max_value=max_d)

f = df[df["size"].isin(pick_sizes) & df["sentiment"].isin(pick_sent)].copy()
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    f = f[(f["date"] >= pd.Timestamp(date_range[0])) & (f["date"] <= pd.Timestamp(date_range[1]))]

# --- KPIs (filtered) --------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Reviews (filtered)", len(f))
c2.metric("Avg rating", round(float(f["rating"].mean()), 2) if len(f) else "—")
c3.metric("% negative", f"{round(100 * (f['sentiment'] == 'negative').mean(), 1)}%" if len(f) else "—")
c4.metric("Active alerts", len(alerts))

# --- alerts panel (full snapshot) -------------------------------------------
st.subheader("🚨 Alerts — monthly negative-theme spikes (full snapshot)")
if alerts:
    for a in alerts:
        st.error(f"**{a['theme']}** complaints spiked to **{a['current']}** in {a['month']} "
                 f"(baseline {a['baseline']}/mo, Δ{a['delta']}).")
else:
    st.success("No negative-theme spikes over threshold in the recent window.")

# --- founder brief (full snapshot) ------------------------------------------
st.subheader("📝 Founder brief")
st.markdown(brief_md or "_No brief generated yet._")

st.divider()
st.subheader("🔎 Explore (responds to filters)")
if f.empty:
    st.info("No reviews match the current filters.")
    st.stop()

dated = f.dropna(subset=["date"])
st.markdown("**Average rating by month**")
st.line_chart(dated.groupby("month")["rating"].mean().round(2))

colA, colB = st.columns(2)
with colA:
    st.markdown("**Review volume by month**")
    st.bar_chart(dated.groupby("month").size().rename("reviews"))
with colB:
    st.markdown("**Sentiment over time**")
    st.bar_chart(dated.pivot_table(index="month", columns="sentiment",
                                   values="review_id", aggfunc="count").fillna(0))

colC, colD = st.columns(2)
with colC:
    st.markdown("**Theme breakdown**")
    st.bar_chart(f.explode("themes_list")["themes_list"].dropna().value_counts())
with colD:
    st.markdown("**Reviews by size variant**")
    st.bar_chart(f["size"].value_counts())

st.markdown("**Sample reviews** (evidence is a verbatim phrase from the body)")
st.dataframe(
    f[["review_date", "size", "rating", "sentiment", "themes", "evidence", "title", "body"]]
    .sort_values("review_date", ascending=False),
    width="stretch", hide_index=True,
)

# --- footer -----------------------------------------------------------------
st.divider()
st.caption(
    f"Source: {config.SOURCE_NAME} · collected {config.SNAPSHOT_DATE} · "
    f"{stats.get('total_reviews', '?')} public Amazon reviews (manual snapshot, not live). "
    "LLM tags & summarises existing rows only; pandas computes all metrics. "
    "No product purity / quality / health claims."
)
