"""Collect a candidate pool from Hacker News, RSS, and Twitter/X before the model searches.

Giving the research call a curated pool to score beats making it discover
everything from cold searches. All sources here are free, unauthenticated,
and have no rate limits worth worrying about at this volume.

Every fetch is wrapped so that one dead feed cannot kill the morning brief.
"""

import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from config import (
    HN_MIN_POINTS,
    MAX_ITEMS_PER_SOURCE,
    MAX_STORY_AGE_HOURS,
    MAX_TWEETS_PER_TOPIC,
    SEARCH_DELAY_SEC,
    SSL_CONTEXT,
    USE_TWITTER_SOURCE,
    load_lines,
)

HN_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"

# Several publishers return 403 to unrecognised clients. This is a normal
# browser string: we are reading a public RSS feed the way any feed reader
# would, not evading anything.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
ACCEPT = "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"
TIMEOUT = 30


def _fetch_bytes(url: str) -> bytes:
    def _get(headers: dict) -> bytes:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=SSL_CONTEXT) as r:
            return r.read()

    try:
        return _get({"User-Agent": USER_AGENT, "Accept": ACCEPT})
    except urllib.error.HTTPError as exc:
        # Some servers reject the Accept header outright rather than ignoring
        # it. Retry bare before giving up.
        if exc.code in (406, 415):
            return _get({"User-Agent": USER_AGENT})
        raise


def _get_json(url: str) -> dict:
    import json

    return json.loads(_fetch_bytes(url).decode("utf-8", errors="replace"))


def _cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=MAX_STORY_AGE_HOURS)


# --------------------------------------------------------------------------
# Hacker News
# --------------------------------------------------------------------------


def _hn_query(query: str) -> list[dict]:
    """Search HN for recent stories matching one query.

    Uses the Algolia search API, which is free and needs no key. Comment count
    matters as much as points here: a story with 80 comments is contested, and
    a contested story is one where there is an argument worth making.
    """
    since = int(_cutoff().timestamp())
    params = urllib.parse.urlencode(
        {
            "query": query,
            "tags": "story",
            "numericFilters": f"created_at_i>{since},points>={HN_MIN_POINTS}",
            "hitsPerPage": MAX_ITEMS_PER_SOURCE,
        }
    )
    data = _get_json(f"{HN_SEARCH}?{params}")

    items = []
    for hit in data.get("hits", []):
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
        items.append(
            {
                "title": hit.get("title", "").strip(),
                "url": url,
                "source": "Hacker News",
                "published": hit.get("created_at", "")[:10],
                "signal": (
                    f"{hit.get('points', 0)} points, "
                    f"{hit.get('num_comments', 0)} comments"
                ),
                "discussion": f"https://news.ycombinator.com/item?id={hit['objectID']}",
                "matched": query,
            }
        )
    return items


def fetch_hn() -> list[dict]:
    queries = load_lines("hn_queries.txt")
    if not queries:
        return []

    items = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_hn_query, q): q for q in queries}
        for future in as_completed(futures):
            try:
                items.extend(future.result())
            except Exception as exc:
                print(f"  HN query '{futures[future]}' failed: {exc}")
    return items


# --------------------------------------------------------------------------
# RSS
# --------------------------------------------------------------------------


def _load_blocklist() -> list["re.Pattern"]:
    """Terms that disqualify an RSS item even when it matches a keyword.

    keywords.txt is a pass list, so an item only needs one AI-ish word to get
    in. That lets webinar listings, podcast episodes and award roundups
    through, because they mention AI while containing no story to post about.
    """
    return [
        re.compile(rf"\b{re.escape(t.strip())}", re.IGNORECASE)
        for t in load_lines("blocklist.txt")
    ]


def _load_keywords() -> list["re.Pattern"]:
    """Compile keyword matchers for RSS items.

    Vertical trade press is the whole point of feeds.txt, but most of what it
    publishes is claims, catastrophes and market news rather than technology.
    Without this filter, one insurance feed will happily fill the pool with
    shipping disruptions and dam litigation. An empty keywords file disables
    the filter entirely.

    Short terms are matched as whole words, because a plain substring test on
    "AI" also matches "Airlines", "Bahrain" and "campaign". Longer terms match
    as prefixes so that "agent" catches "agents" and "agentic", and
    "hallucinat" catches both the noun and the verb.
    """
    patterns = []
    for keyword in load_lines("keywords.txt"):
        escaped = re.escape(keyword.strip())
        if len(keyword.strip()) <= 4:
            patterns.append(re.compile(rf"\b{escaped}\b", re.IGNORECASE))
        else:
            patterns.append(re.compile(rf"\b{escaped}", re.IGNORECASE))
    return patterns


def _rss_feed(label: str, url: str) -> list[dict]:
    import feedparser

    # feedparser would fetch this itself, but then it uses its own SSL context
    # and hits the same macOS certificate problem. Fetching the bytes here and
    # handing them over keeps every request on one verified context.
    parsed = feedparser.parse(_fetch_bytes(url))
    cutoff = _cutoff()
    keywords = _load_keywords()
    blocked = _load_blocklist()

    items = []
    skipped = 0
    for entry in parsed.entries[: MAX_ITEMS_PER_SOURCE * 6]:
        title = entry.get("title", "").strip()
        summary = (entry.get("summary", "") or "")[:400]

        haystack = f"{title} {summary}"
        if keywords and not any(p.search(haystack) for p in keywords):
            skipped += 1
            continue
        if blocked and any(p.search(title) for p in blocked):
            skipped += 1
            continue

        struct = entry.get("published_parsed") or entry.get("updated_parsed")
        if struct:
            published = datetime.fromtimestamp(time.mktime(struct), tz=timezone.utc)
            if published < cutoff:
                continue
            published_str = published.date().isoformat()
        else:
            # No date means we cannot verify freshness. Keep it but flag it,
            # and let the model decide whether to trust it.
            published_str = "unknown"

        items.append(
            {
                "title": title,
                "url": entry.get("link", ""),
                "source": label,
                "published": published_str,
                "signal": "RSS",
                "summary": summary,
            }
        )
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break

    if skipped and not items:
        print(f"  Feed '{label}': {skipped} items, none matched keywords.txt")
    return items


def fetch_rss() -> list[dict]:
    feeds = []
    for line in load_lines("feeds.txt"):
        if "|" not in line:
            continue
        label, url = line.split("|", 1)
        feeds.append((label.strip(), url.strip()))

    if not feeds:
        return []

    items = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_rss_feed, label, url): label for label, url in feeds}
        for future in as_completed(futures):
            try:
                items.extend(future.result())
            except Exception as exc:
                print(f"  Feed '{futures[future]}' failed: {exc}")
    return items


# --------------------------------------------------------------------------
# Twitter / X (via Google site:x.com search — no API key required)
# --------------------------------------------------------------------------

_GOOGLE_SEARCH = "https://www.google.com/search"

# Rotate user agents so we don't get blocked on rapid sequential requests.
_TWITTER_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]
_ua_index = 0


def _next_ua() -> str:
    global _ua_index
    ua = _TWITTER_USER_AGENTS[_ua_index % len(_TWITTER_USER_AGENTS)]
    _ua_index += 1
    return ua


def _google_twitter_search(query: str) -> list[dict]:
    """Search Google for site:x.com content matching *query*.

    Google returns tweet preview snippets in search results without requiring
    any Twitter API key or login. We parse the result divs with BeautifulSoup
    and extract the text and author handle.

    Returns at most MAX_TWEETS_PER_TOPIC items in pool format.
    """
    from bs4 import BeautifulSoup

    params = urllib.parse.urlencode({
        "q": f'site:x.com "{query}"',
        "num": 10,
        "hl": "en",
    })
    url = f"{_GOOGLE_SEARCH}?{params}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _next_ua(),
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=SSL_CONTEXT) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception:
        return []

    soup = BeautifulSoup(html, "lxml")
    items = []

    for result in soup.select("div.g"):
        link_tag = result.select_one("a[href]")
        if not link_tag:
            continue
        href = link_tag["href"]
        if "x.com" not in href and "twitter.com" not in href:
            continue

        # Extract display text from the snippet div.
        snippet_div = result.select_one("div.VwiC3b") or result.select_one("span.aCOpRe")
        if not snippet_div:
            continue
        text = snippet_div.get_text(" ", strip=True)
        if len(text) < 30:
            continue

        # Best-effort author extraction from the URL path: x.com/handle/status/id
        author = ""
        parts = href.replace("https://x.com/", "").replace("https://twitter.com/", "").split("/")
        if parts:
            author = f"@{parts[0]}"

        items.append({
            "title": text[:120],
            "url": href,
            "source": "Twitter/X",
            "published": datetime.now(timezone.utc).date().isoformat(),
            "signal": author or "Twitter/X",
            "summary": text,
            "author": author,
        })

        if len(items) >= MAX_TWEETS_PER_TOPIC:
            break

    return items


def fetch_twitter() -> list[dict]:
    """Search Twitter/X via Google for each query in config/twitter_queries.txt.

    A missing or empty twitter_queries.txt silently returns nothing, so
    disabling this source is as simple as clearing or removing that file.
    Delays between requests keep this polite.
    """
    if not USE_TWITTER_SOURCE:
        return []

    queries = load_lines("twitter_queries.txt")
    if not queries:
        return []

    items = []
    for i, query in enumerate(queries):
        if i > 0:
            time.sleep(SEARCH_DELAY_SEC)
        try:
            found = _google_twitter_search(query)
            items.extend(found)
            if found:
                print(f"  Twitter query '{query[:40]}': {len(found)} result(s)")
        except Exception as exc:
            print(f"  Twitter query '{query[:40]}' failed: {exc}")

    return items


# --------------------------------------------------------------------------


def collect() -> list[dict]:
    """Fetch everything, dedupe on URL, return the pool."""
    twitter_items = fetch_twitter()
    items = fetch_hn() + fetch_rss() + twitter_items

    seen = set()
    unique = []
    for item in items:
        if not item.get("title") or not item.get("url"):
            continue
        key = item["url"].split("?")[0].rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    sources = "HN, RSS" + (", Twitter/X" if twitter_items else "")
    print(f"Collected {len(unique)} unique items from {sources}.")
    return unique
