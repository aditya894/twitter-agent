"""
agent.py — Main entry point for the Twitter Content Agent.

Usage:
    python agent.py                         # auto-discover trending topics
    python agent.py --topics "AI India" "EV India"   # manual topics
    python agent.py --dry-run              # discover topics only, no post generation
"""
import argparse
import asyncio
import sys

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

import store
from config import MAX_TOPICS, OPENROUTER_API_KEY, TOPICS_OVERRIDE
from scraper import collect_content, get_trending_topics
from writer import generate_post, pick_best_topics

console = Console()


# ─────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────

def _check_env():
    if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.startswith("sk-or-"):
        console.print(
            "[bold red]ERROR:[/] OPENROUTER_API_KEY not set or invalid.\n"
            "Copy [bold].env.example[/] → [bold].env[/] and add your key."
        )
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────
# Core pipeline
# ─────────────────────────────────────────────────────────────────────

async def run(manual_topics: list[str] | None = None, dry_run: bool = False):
    _check_env()

    console.print(Panel.fit(
        "[bold cyan]🤖 Twitter Content Agent[/]\n"
        "[dim]Finds trending topics → collects tweets → generates posts[/]",
        border_style="cyan",
    ))

    # ── Step 1: Get topics ──────────────────────────────────────────
    if manual_topics:
        topics_raw = manual_topics
        console.print(f"\n[bold]Topics (manual):[/] {', '.join(topics_raw)}")
    elif TOPICS_OVERRIDE:
        topics_raw = TOPICS_OVERRIDE
        console.print(f"\n[bold]Topics (env override):[/] {', '.join(topics_raw)}")
    else:
        console.print("\n[bold cyan]Step 1/4[/] Fetching trending topics from Google News…")
        topics_raw = get_trending_topics(limit=10)
        if not topics_raw:
            console.print("[red]No topics found from RSS. Check your internet connection.[/]")
            return

    # ── Step 2: Claude picks best topics ────────────────────────────
    console.print("\n[bold cyan]Step 2/4[/] Selecting best postable topics via Claude…")
    selected_topics = pick_best_topics(topics_raw, n=MAX_TOPICS)
    console.print(f"  Selected: [bold]{', '.join(selected_topics)}[/]")

    if dry_run:
        console.print("\n[yellow]Dry-run mode — stopping before content generation.[/]")
        return

    # ── Step 3: Collect tweets per topic ────────────────────────────
    console.print(f"\n[bold cyan]Step 3/4[/] Searching Twitter content via Google…")
    tweet_map = await collect_content(selected_topics)

    for topic, tweets in tweet_map.items():
        console.print(f"  [dim]{topic}[/] → {len(tweets)} tweet(s) found")

    # ── Step 4: Generate posts ───────────────────────────────────────
    console.print(f"\n[bold cyan]Step 4/4[/] Generating LinkedIn posts via Claude…")
    saved_ids = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for topic in selected_topics:
            task = progress.add_task(f"  Writing: {topic[:55]}…", total=None)
            tweets = tweet_map.get(topic, [])
            generated = generate_post(topic, tweets)
            post_id = store.save_pending(topic, tweets, generated)
            saved_ids.append((topic, post_id, generated))
            progress.update(task, completed=True)

    # ── Summary table ────────────────────────────────────────────────
    table = Table(title="\n✅ Posts saved to pending/", show_lines=True)
    table.add_column("Topic", style="cyan", max_width=30)
    table.add_column("Hook", style="white", max_width=45)
    table.add_column("ID", style="dim", max_width=10)

    for topic, post_id, gen in saved_ids:
        table.add_row(topic[:30], gen.get("hook", "")[:45], post_id[:8])

    console.print(table)
    console.print(
        "\n[bold green]Done![/] Open the dashboard to review:\n"
        "  [bold]python dashboard.py[/]  →  [link=http://localhost:8000]http://localhost:8000[/link]\n"
    )


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Twitter Content Agent")
    parser.add_argument(
        "--topics", nargs="+", metavar="TOPIC",
        help="Manual topics (skips auto-discovery)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Discover topics only, skip generation",
    )
    args = parser.parse_args()
    asyncio.run(run(manual_topics=args.topics, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
