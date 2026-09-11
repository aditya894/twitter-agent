"""
scraper.py — Trending topic discovery + news article context.

  1. get_trending_topics()  → Google News RSS (feedparser)
  2. collect_content()      → Google News RSS per-topic search (feedparser)
                              (replaces unreliable Google→site:x.com scraping)
"""
import re
from urllib.parse import quote_plus

import feedparser
from bs4 import BeautifulSoup

from config import GOOGLE_NEWS_RSS, MAX_TWEETS_PER_TOPIC


# ─────────────────────────────────────────────────────────────────────
# Step 1 — Trending topics from Google News RSS
# ─────────────────────────────────────────────────────────────────────

def get_trending_topics(limit: int = 10) -> list[str]:
    """
    Parse Google News Tech RSS and return headline strings.
    Completely free, no auth, real-time.
    """
    feed = feedparser.parse(GOOGLE_NEWS_RSS)
    topics = []
    for entry in feed.entries[:limit]:
        # Strip source name appended by Google e.g. "... - TechCrunch"
        title = re.sub(r"\s*-\s*[^-]+$", "", entry.title).strip()
        if title:
            topics.append(title)
    return topics


# ─────────────────────────────────────────────────────────────────────
# Step 2 — Fetch news article context per topic via Google News RSS
# ─────────────────────────────────────────────────────────────────────

def _fetch_news_context(topic: str, limit: int = MAX_TWEETS_PER_TOPIC) -> list[dict]:
    """
    Search Google News RSS for recent articles about the topic.
    Returns list of {text, author, url} — same shape as old tweet results
    so the rest of the pipeline (writer, store, template) is unchanged.
    """
    query = quote_plus(topic)
    url = (
        f"https://news.google.com/rss/search"
        f"?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    )
    feed = feedparser.parse(url)
    articles = []
    for entry in feed.entries[:limit]:
        # Google News summaries contain HTML — strip it
        raw_summary = entry.get("summary", "") or entry.get("title", "")
        text = BeautifulSoup(raw_summary, "lxml").get_text(" ", strip=True)[:400]
        source = entry.get("source", {}).get("title", "Google News")
        link = entry.get("link", "")
        if text:
            articles.append({"text": text, "author": source, "url": link})
    return articles


async def collect_content(topics: list[str]) -> dict[str, list[dict]]:
    """
    For each topic, fetch Google News articles as research context.
    Returns mapping: topic → list of article dicts.
    """
    return {topic: _fetch_news_context(topic) for topic in topics}
