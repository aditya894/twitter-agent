"""Track what has already been offered so the brief does not repeat itself.

This is the difference between a useful daily brief and one that sends the same
post about pilot failure rates every Tuesday.
"""

import json
from datetime import date, datetime, timedelta

from config import DEDUPE_WINDOW_DAYS, HISTORY_FILE


def _load() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # A corrupt history file should not stop today's brief.
        return []


def recent_topics() -> list[str]:
    """Topic labels offered inside the dedupe window."""
    cutoff = date.today() - timedelta(days=DEDUPE_WINDOW_DAYS)
    out = []
    for entry in _load():
        try:
            when = datetime.fromisoformat(entry["date"]).date()
        except (KeyError, ValueError):
            continue
        if when >= cutoff:
            out.extend(entry.get("topics", []))
    return out


def record(topics: list[str]) -> None:
    """Append today's offered topics, then prune anything long expired."""
    entries = _load()
    entries.append({"date": date.today().isoformat(), "topics": topics})

    # Keep double the window so the file stays useful but does not grow forever.
    cutoff = date.today() - timedelta(days=DEDUPE_WINDOW_DAYS * 2)
    kept = []
    for entry in entries:
        try:
            when = datetime.fromisoformat(entry["date"]).date()
        except (KeyError, ValueError):
            continue
        if when >= cutoff:
            kept.append(entry)

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(kept, indent=2, ensure_ascii=False), encoding="utf-8"
    )
