"""
scraper.py — Trending topic discovery + tweet collection via Google.

No Twitter API or login required.
  1. get_trending_topics()  → Google News RSS (feedparser)
  2. search_tweets_via_google(topic) → Google search site:x.com (httpx + BS4)
"""
import asyncio
import random
import re
import time
from urllib.parse import quote_plus

import feedparser
import httpx
from bs4 import BeautifulSoup

from config import (
    GOOGLE_NEWS_RSS,
    MAX_TWEETS_PER_TOPIC,
    SEARCH_DELAY_SEC,
    USER_AGENTS,
)


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
        title = re.sub(r"\s*-\s*\S+$", "", entry.title).strip()
        if title:
            topics.append(title)
    return topics


# ─────────────────────────────────────────────────────────────────────
# Step 2 — Collect tweets via Google search (site:x.com)
# ─────────────────────────────────────────────────────────────────────

def _random_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.google.com/",
    }


def _parse_google_results(html: str) -> list[dict]:
    """
    Extract tweet snippets from a Google SERP page.
    Google shows tweet text, author and URL in search result cards.
    """
    soup = BeautifulSoup(html, "lxml")
    results = []

    # Each organic result is inside a <div class="g"> or similar container
    for div in soup.select("div.g, div[data-hveid]"):
        link_tag = div.find("a", href=True)
        snippet_tag = div.find("div", {"data-sncf": True}) or div.find("span")

        href = link_tag["href"] if link_tag else ""
        # Only keep actual x.com / twitter.com links
        if not any(d in href for d in ("x.com/", "twitter.com/")):
            continue

        text = snippet_tag.get_text(" ", strip=True) if snippet_tag else ""
        if not text or len(text) < 20:
            continue

        # Try to extract @handle from URL: x.com/handle/status/...
        author_match = re.search(r"(?:x|twitter)\.com/([^/]+)/status", href)
        author = author_match.group(1) if author_match else "unknown"

        results.append({"text": text, "author": f"@{author}", "url": href})

        if len(results) >= MAX_TWEETS_PER_TOPIC:
            break

    return results


async def search_tweets_via_google(topic: str) -> list[dict]:
    """
    Search Google for top Twitter/X posts about `topic`.
    Returns a list of dicts: {text, author, url}
    """
    query = quote_plus(f'site:x.com "{topic}"')
    url = f"https://www.google.com/search?q={query}&num=20&hl=en"

    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        try:
            resp = await client.get(url, headers=_random_headers())
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            print(f"  [scraper] Google request failed: {exc}")
            return []

    tweets = _parse_google_results(resp.text)

    # Polite delay before next request
    await asyncio.sleep(SEARCH_DELAY_SEC)
    return tweets


# ─────────────────────────────────────────────────────────────────────
# Convenience: collect all tweets for multiple topics
# ─────────────────────────────────────────────────────────────────────

async def collect_content(topics: list[str]) -> dict[str, list[dict]]:
    """
    For each topic, search Google and return mapping topic → tweets.
    Runs sequentially to respect rate limits.
    """
    results: dict[str, list[dict]] = {}
    for topic in topics:
        tweets = await search_tweets_via_google(topic)
        results[topic] = tweets
    return results
