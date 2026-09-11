"""
Central configuration for the Twitter Content Agent.
Edit these values to customise behaviour.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── API ───────────────────────────────────────────────────
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "google/gemini-2.0-flash-exp:free")

# ── Topic discovery ───────────────────────────────────────
# Google News RSS — India Technology feed (search-based, more stable than topic IDs)
GOOGLE_NEWS_RSS: str = (
    "https://news.google.com/rss/search"
    "?q=AI+technology+India+startup&hl=en-IN&gl=IN&ceid=IN:en"
)

# How many topics to process per run
MAX_TOPICS: int = 3

# Optional hard-coded topic override (set via .env or edit here)
TOPICS_OVERRIDE: list[str] = [
    t.strip()
    for t in os.getenv("TOPICS_OVERRIDE", "").split(",")
    if t.strip()
]

# ── Scraping ──────────────────────────────────────────────
# Seconds to wait between Google search requests (be polite)
SEARCH_DELAY_SEC: float = 2.5

# Max tweets to collect per topic
MAX_TWEETS_PER_TOPIC: int = 6

# Rotate through these User-Agents to reduce block risk
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
]

# ── Storage ───────────────────────────────────────────────
DATA_DIR: str = os.getenv("DATA_DIR", "data")

# ── Dashboard ─────────────────────────────────────────────
DASHBOARD_HOST: str = "0.0.0.0"
# Render injects PORT; fall back to DASHBOARD_PORT for local dev
DASHBOARD_PORT: int = int(os.getenv("PORT", os.getenv("DASHBOARD_PORT", "8000")))
DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "")
