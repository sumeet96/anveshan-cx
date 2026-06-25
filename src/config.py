"""Central configuration: paths, provenance constants, SKU map, taxonomy.

Single source of truth for the snapshot date and product mapping so nothing
downstream hardcodes "live" data or re-derives the SKU table.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- paths ------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_RAW = BASE_DIR / "data" / "raw"
DATA_PROCESSED = BASE_DIR / "data" / "processed"
PROMPTS_DIR = BASE_DIR / "prompts"

RAW_SNAPSHOT = DATA_RAW / "amazon_reviews_snapshot_2026-06-24.txt"
REVIEWS_CSV = DATA_PROCESSED / "reviews.csv"
REVIEWS_ENRICHED_CSV = DATA_PROCESSED / "reviews_enriched.csv"
ENRICH_CACHE = DATA_PROCESSED / "enrich_cache.json"
TRENDS_CSV = DATA_PROCESSED / "trends.csv"
ALERTS_JSON = DATA_PROCESSED / "alerts.json"
BRIEF_MD = DATA_PROCESSED / "brief.md"
BRIEF_JSON = DATA_PROCESSED / "brief.json"
STATS_JSON = DATA_PROCESSED / "stats.json"
PARSE_FAILURES_LOG = DATA_PROCESSED / "parse_failures.log"

# --- provenance (single source of truth) ------------------------------------
SNAPSHOT_DATE = "2026-06-24"            # date the public reviews were collected
COLLECTED_ON = SNAPSHOT_DATE
SOURCE_NAME = RAW_SNAPSHOT.name          # stamped on every row
PROTOTYPE_BANNER = (
    "PROTOTYPE — dated snapshot of public Amazon reviews collected on "
    f"{SNAPSHOT_DATE}. Not live or real-time."
)

# --- product / SKU map (Anveshan A2 Cow Ghee size variants) -----------------
PRODUCT_NAME = "Anveshan A2 Cow Ghee"
DEFAULT_ASIN = "B08KJG9VLJ"              # 1L; fallback when a row's size is unknown
SKU_MAP = {
    "0.15L": {"asin": "B0D7VJ8R8W", "product_name": "Anveshan A2 Ghee",          "net_ml": 150},
    "0.5L":  {"asin": "B07TMKSC3S", "product_name": "Anveshan A2 Cow Ghee",      "net_ml": 500},
    "1L":    {"asin": "B08KJG9VLJ", "product_name": "Anveshan A2 Cow Ghee",      "net_ml": 1000},
    "2.5L":  {"asin": "B0FW5H42TN", "product_name": "Anveshan A2 Desi Cow Ghee", "net_ml": 2500},
    "5L":    {"asin": "B0DY813WTD", "product_name": "Anveshan A2 Desi Cow Ghee", "net_ml": 5000},
}

# --- LLM models (small/cheap is enough) -------------------------------------
OPENAI_INGEST_MODEL = os.getenv("OPENAI_INGEST_MODEL", "gpt-4o-mini")
OPENAI_ENRICH_MODEL = os.getenv("OPENAI_ENRICH_MODEL", "gpt-4o-mini")
OPENAI_BRIEF_MODEL = os.getenv("OPENAI_BRIEF_MODEL", "gpt-4o-mini")

# --- enrich taxonomy (used in Phase 2) --------------------------------------
# Theme taxonomy — labels must match prompts/enrich_prompt.txt exactly.
THEMES = [
    "taste_quality", "packaging_leakage", "delivery_logistics", "price_value",
    "authenticity_traceability", "customer_service", "other",
]
SENTIMENTS = ["negative", "neutral", "positive"]

# --- trend / alert params (used in Phase 3) ---------------------------------
TREND_FREQ = "M"            # monthly buckets for the long-range trend
ALERT_BASELINE_MONTHS = 3   # trailing complete months used as the spike baseline
ALERT_MIN_VOLUME = 3        # suppress small-N false spikes
ALERT_THRESHOLD = 0.5       # relative increase vs trailing baseline to flag
# The month-over-month comparison and alerts use the last COMPLETE calendar month;
# the partial snapshot month is shown in the trend chart but excluded from deltas,
# so a partial month is never compared against a full one (weekly buckets were too
# sparse on this snapshot to give a meaningful spike signal).
