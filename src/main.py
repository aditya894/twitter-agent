"""Daily LinkedIn brief.

Researches the last 72 hours, scores stories against the ICP, drafts posts in
house style, and emails them. Publishes nothing. The human decides.
"""

import argparse
import json
import sys
import traceback
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import draft as drafter
import history
import mailer
import research

# The ICP now says to return the best available even on a thin day, because
# seeing a scored 5 and deciding yourself beats receiving nothing. Keep a floor
# only to drop genuinely unpostable items.
MIN_SCORE = 4


def run(dry_run: bool = False, save_json: bool = False) -> int:
    config.validate()

    exclusions = history.recent_topics()
    print(f"Excluding {len(exclusions)} recently offered topics.")

    candidates = research.gather(exclusions)
    print(f"Research returned {len(candidates)} candidates.")
    for c in candidates:
        print(f"  [{c.get('score','?')}] {c.get('headline','')[:90]}")

    if len(candidates) < 3:
        print(
            f"Note: only {len(candidates)} candidates came back. If a truncation "
            f"warning appeared above, raise MAX_SEARCHES headroom or lower "
            f"MAX_SEARCHES. If not, the feeds were simply thin today."
        )

    viable = [c for c in candidates if c.get("score", 0) >= MIN_SCORE]
    if not viable:
        print(f"Nothing scored {MIN_SCORE} or above. Sending a skip notice.")
    elif max(c.get("score", 0) for c in viable) < 6:
        print("Thin day. Best story scored under 6, drafting it anyway.")

    drafts = drafter.write(viable) if viable else []
    for d in drafts:
        if d.get("lint"):
            print(f"  Lint on '{d.get('topic')}': {', '.join(d['lint'])}")

    if save_json or dry_run:
        out = Path(config.DATA_DIR) / f"brief-{date.today().isoformat()}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {"candidates": candidates, "drafts": drafts}, indent=2, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        print(f"Wrote {out}")

    if dry_run:
        html_body, _ = mailer.render(drafts, len(candidates))
        preview = Path(config.DATA_DIR) / "preview.html"
        preview.write_text(html_body, encoding="utf-8")
        print(f"Dry run. Email preview at {preview}. Nothing sent, nothing recorded.")
        return 0

    mailer.send(drafts, len(candidates))
    print(f"Sent to {', '.join(config.EMAIL_TO)}.")

    if drafts:
        history.record([d.get("topic", "") for d in drafts if d.get("topic")])
        print("History updated.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the daily LinkedIn brief.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Research and draft, write an HTML preview, send no email.",
    )
    parser.add_argument(
        "--save-json", action="store_true", help="Write raw output to data/."
    )
    parser.add_argument(
        "--sources-only",
        action="store_true",
        help="Fetch HN and RSS and print what came back. No API calls, no cost.",
    )
    args = parser.parse_args()

    if args.sources_only:
        import sources

        items = sources.collect()
        for item in items:
            print(
                f"  [{item['source']}] {item['published']}  "
                f"{item['title'][:88]}  ({item.get('signal','')})"
            )
        if not items:
            print("Nothing came back. Check config/feeds.txt and your network.")
        return 0

    try:
        return run(dry_run=args.dry_run, save_json=args.save_json)
    except Exception:
        traceback.print_exc()
        # Non-zero exit makes GitHub Actions mark the run red and email you.
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
