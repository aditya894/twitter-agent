"""Central configuration. Everything tunable lives here or in .env."""

import os
import re
import ssl
from pathlib import Path

# macOS Python installed from python.org ships without root certificates, and
# every HTTPS call fails with CERTIFICATE_VERIFY_FAILED until you run its
# Install Certificates.command. Using certifi's bundle directly sidesteps the
# whole problem and behaves identically on Linux and in CI.
try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
HISTORY_FILE = DATA_DIR / "history.json"

# Load .env for local runs. On GitHub Actions there is no .env and the
# variables come from repo secrets, so this is a no-op there.
#
# .env is authoritative: it overrides anything already exported in the shell,
# and a later line overrides an earlier one. Using setdefault here would mean
# a stale duplicate near the top of the file silently beats the value you just
# edited at the bottom, which is a miserable thing to debug.
_ENV_FILE = ROOT / ".env"
if _ENV_FILE.exists():
    _seen: dict[str, int] = {}
    for _n, _line in enumerate(
        _ENV_FILE.read_text(encoding="utf-8").splitlines(), start=1
    ):
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _value = _line.split("=", 1)
        _key = _key.strip()
        # Strip an inline comment, but only when it follows whitespace, so a
        # value containing a hash is left alone.
        _value = re.split(r"\s+#", _value.strip(), maxsplit=1)[0]
        if _key in _seen:
            print(
                f"Warning: .env sets {_key} twice, on lines {_seen[_key]} and "
                f"{_n}. Line {_n} wins. Delete the other one."
            )
        _seen[_key] = _n
        os.environ[_key] = _value.strip().strip("\"'")

# --- Anthropic ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Research runs many searches, so a cheaper model is fine.
# Drafting is where quality shows, so it gets the stronger model.
RESEARCH_MODEL = os.environ.get("RESEARCH_MODEL", "claude-sonnet-4-6")
DRAFT_MODEL = os.environ.get("DRAFT_MODEL", "claude-sonnet-4-6")

# web_search_20250305 is the widely supported baseline.
# web_search_20260318 adds dynamic filtering on newer models.
WEB_SEARCH_TOOL_VERSION = os.environ.get(
    "WEB_SEARCH_TOOL_VERSION", "web_search_20250305"
)
MAX_SEARCHES = int(os.environ.get("MAX_SEARCHES", "12"))

# --- Brief settings ---
NUM_OPTIONS = int(os.environ.get("NUM_OPTIONS", "3"))
# A topic offered within this window will not be offered again.
DEDUPE_WINDOW_DAYS = int(os.environ.get("DEDUPE_WINDOW_DAYS", "21"))
# Reject anything older than this. Stale news reads badly on LinkedIn.
MAX_STORY_AGE_HOURS = int(os.environ.get("MAX_STORY_AGE_HOURS", "72"))

# --- Source collection (Hacker News, RSS, and Twitter/X) ---
# Set USE_SOURCE_FEEDS=false to fall back to pure model-driven search.
USE_SOURCE_FEEDS = os.environ.get("USE_SOURCE_FEEDS", "true").lower() == "true"
# Below this, an HN story has not been read by enough people to be a signal.
HN_MIN_POINTS = int(os.environ.get("HN_MIN_POINTS", "15"))
MAX_ITEMS_PER_SOURCE = int(os.environ.get("MAX_ITEMS_PER_SOURCE", "4"))
# Hard cap on what gets sent to the model, to keep the prompt affordable.
MAX_POOL_ITEMS = int(os.environ.get("MAX_POOL_ITEMS", "60"))

# --- Twitter/X source (Google site:x.com search, no API key needed) ---
# Set USE_TWITTER_SOURCE=false to disable entirely.
USE_TWITTER_SOURCE = os.environ.get("USE_TWITTER_SOURCE", "true").lower() == "true"
# Results per query. Google returns ~10 snippets; we take the best ones.
MAX_TWEETS_PER_TOPIC = int(os.environ.get("MAX_TWEETS_PER_TOPIC", "5"))
# Polite delay (seconds) between Google search requests.
SEARCH_DELAY_SEC = float(os.environ.get("SEARCH_DELAY_SEC", "2.5"))

# --- Email ---
# "resend" (HTTP API, recommended) or "smtp" (fallback).
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "resend").lower()

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

# Must be an address on a domain you have verified in Resend. Before you have
# verified one, "onboarding@resend.dev" works but only delivers to the address
# you signed up with.
EMAIL_FROM = os.environ.get("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_TO = [a.strip() for a in os.environ.get("EMAIL_TO", "").split(",") if a.strip()]

# SMTP fallback. Only read when EMAIL_PROVIDER=smtp.
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")


def load_prompt(name: str) -> str:
    """Read a markdown config file from config/."""
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    return path.read_text(encoding="utf-8")


def load_lines(name: str) -> list[str]:
    """Read a config list file, dropping blanks and # comments.

    A missing file returns an empty list rather than raising, so removing
    feeds.txt cleanly disables RSS without editing any Python.
    """
    path = CONFIG_DIR / name
    if not path.exists():
        return []
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def validate() -> None:
    """Fail loudly at startup rather than silently mid-run."""
    missing = []
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not EMAIL_TO:
        missing.append("EMAIL_TO")

    if EMAIL_PROVIDER == "resend":
        if not RESEND_API_KEY:
            missing.append("RESEND_API_KEY")
    elif EMAIL_PROVIDER == "smtp":
        if not SMTP_USER:
            missing.append("SMTP_USER")
        if not SMTP_PASSWORD:
            missing.append("SMTP_PASSWORD")
    else:
        raise RuntimeError(
            f"EMAIL_PROVIDER must be 'resend' or 'smtp', got '{EMAIL_PROVIDER}'"
        )

    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"EMAIL_PROVIDER is currently '{EMAIL_PROVIDER}'. "
            f"To use Resend, set EMAIL_PROVIDER=resend in your .env.\n"
            f"Reading .env from: {_ENV_FILE}"
        )
