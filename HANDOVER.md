# Daily LinkedIn Brief: build notes

A working Claude-powered content agent, built and shipped in one day. This
document is written for a developer building similar agents. It covers what it
does, how it is put together, the API patterns that matter, and the specific
things that broke.

The code is the least interesting part. The design decisions and the failure
modes are the transferable content.

---

## 1. What it does

Every weekday at 06:30 IST, without human involvement:

1. Gathers a candidate pool from Hacker News and 9 RSS feeds
2. Filters that pool by keyword and by a title blocklist
3. Sends the pool to Claude with the web search tool, which verifies each item
   against primary sources, searches for anything missed, and returns scored
   candidates as JSON
4. Sends the top candidates to a second Claude call which drafts LinkedIn posts
   in a defined house style
5. Lints the drafts in Python for style violations the model let through
6. Emails the result with scores, sources and warnings
7. Records the topics so tomorrow does not repeat them

It publishes nothing. A human reads the email and decides.

---

## 2. The single most important design decision

**It drafts. It does not publish.**

Full autonomy was technically available. Posting to a personal LinkedIn profile
is self-serve: add the "Share on LinkedIn" product to a developer app and the
`w_member_social` scope arrives with no review. We deliberately did not use it.

The reasoning: the content goes out under a founder's name, and the product
being sold is senior judgment. One autonomously published post that misreads a
story, cites a vendor blog as research, or reads as machine-written costs more
than the two minutes a day that automation saves. Automating research is safe.
Automating the decision to publish is not.

This generalizes. For any agent producing content or taking action under a
person's identity, separate the expensive-to-automate part (research,
synthesis, drafting) from the cheap-to-do-manually part (approve, publish). The
value is almost entirely in the first.

---

## 3. Architecture

```
GitHub Actions cron (01:00 UTC, Mon-Fri)
    |
    v
main.py  ──> history.py        read topics offered in last 21 days
    |
    v
research.py
    |
    ├──> sources.py            HN Algolia API + 9 RSS feeds, concurrent
    │        │                 keyword pass-list, title block-list
    │        v
    │    candidate pool (~25 items)
    │
    └──> Claude call #1        model: claude-sonnet-5
             + web_search      verifies pool, searches independently
             |                 returns scored candidates as JSON
             v
       4 candidates, scored 1-10
             |
             v
    draft.py ──> Claude call #2   model: claude-opus-5
             |                    writes posts in house style
             v
         lint() in Python         mechanical style enforcement
             |
             v
    mailer.py ──> Resend HTTP API
             |
             v
    history.py                    record topics, git commit back
```

Two model calls per run. Sonnet for research because it runs many searches and
volume matters more than prose quality. Opus for drafting because that is where
output quality is visible.

---

## 4. Claude API patterns that matter

### 4.1 Server-side tools consume your output token budget

The web search tool runs inside the API call. Everything the model emits counts
against `max_tokens`: every search query, every citation, and the running text
between searches.

We set `max_tokens=20000` for a response whose JSON needed about 2,500 tokens,
and it still truncated, because 12 searches ate the rest. The fix is to budget
the two separately:

```python
search_overhead = MAX_SEARCHES * 1500
answer_budget = 6000
max_tokens = search_overhead + answer_budget
```

This is not documented anywhere obvious. If an agent using server tools returns
truncated output, this is the first thing to check.

### 4.2 Large max_tokens requires streaming

Raising `max_tokens` to 24,000 produced:

```
ValueError: Streaming is required for operations that may take
longer than 10 minutes.
```

The SDK refuses non-streaming requests whose token budget implies a long call.
Switch to `messages.stream()` and take the final message. You still get one
complete response, you just cannot use `messages.create()`:

```python
with client.messages.stream(**kwargs) as stream:
    response = stream.get_final_message()
```

Any agent using server tools will hit this, because server tools force the
budget up. Build with streaming from the start.

### 4.3 Salvage truncated JSON rather than failing

Even with correct budgeting, a response can be cut off. When that happens the
array is unparseable but most of it is fine. Decode objects one at a time with
`json.JSONDecoder().raw_decode` and stop at the broken one:

```python
decoder = json.JSONDecoder()
index = text.find("[") + 1
items = []
while index < len(text):
    while index < len(text) and text[index] in ", \t\r\n":
        index += 1
    if index >= len(text) or text[index] == "]":
        break
    try:
        obj, index = decoder.raw_decode(text, index)
    except json.JSONDecodeError:
        break
    items.append(obj)
```

In production this turned a hard failure into a brief with 2 options instead of
4. Degraded, not dead. For an unattended daily job that difference is the whole
game.

Also check `response.stop_reason == "max_tokens"` and log it, so truncation is
visible rather than mysterious.

### 4.4 Do not retry 4xx

The default retry loop burned 3 attempts and 20 seconds of backoff on
`credit balance is too low`. That will never succeed. Retry 429 and 5xx. Fail
immediately on everything else in the 4xx range, with a diagnosis:

```python
if status is not None and 400 <= status < 500 and status != 429:
    raise RuntimeError(_diagnose(status, exc))
```

Map status codes to actionable messages: 401 means check the key format, 404
usually means a model name that does not exist, 400 mentioning credit means
top up billing.

### 4.5 Extract text blocks by type, never by position

With server tools the response contains interleaved `tool_use`, `tool_result`
and `text` blocks. `response.content[0].text` is wrong and will break
intermittently:

```python
"\n".join(b.text for b in response.content
          if getattr(b, "type", None) == "text")
```

### 4.6 Prompt for JSON, but parse defensively

Even with "Return ONLY a JSON array. No preamble, no code fences" in the system
prompt, models sometimes wrap in fences or add a lead-in sentence. The parser
does three passes: direct `json.loads`, then outermost bracketed span, then
salvage. Assume the instruction will be violated occasionally.

### 4.7 Current API facts as of September 2026

- Models used: `claude-sonnet-5`, `claude-opus-5`
- Web search tool: `web_search_20250305` (baseline, widely supported).
  `web_search_20260318` adds dynamic filtering on newer models.
- Declare it as `tools=[{"type": "...", "name": "web_search", "max_uses": 12}]`

---

## 5. The pattern worth stealing: enforce rules twice

Every hard style rule is enforced in two places: once in the prompt, once in
Python after generation.

The model drifts. It will use an em dash eventually, no matter how firmly the
system prompt forbids it. So `draft.py` has a linter:

```python
BANNED_PATTERNS = [
    (r"\bsmall team\b", "uses the word 'small' about the team"),
    (r"\*\*", "contains markdown bold"),
    (r"https?://", "contains a link in the body"),
    (r"(thoughts|agree|what do you think)\?\s*$", "generic closing question"),
    (r"\b\d+(\.\d+)? (million|billion) dollars\b", "write $550m instead"),
] + [(rf"\b\w*{stem}\w*\b", f"British spelling: {stem}")
     for stem in _BRITISH_STEMS]
```

Mechanical violations get auto-fixed (em dashes become full stops). Judgment
violations get flagged in the output for the human to see.

**Lesson learned building the linter:** be careful with broad regexes. A
generic `-ise` pattern to catch British spelling also flagged "raised",
"advised" and "promised". An explicit stem list has no false positives. Test
your linter against text that should pass, not just text that should fail.

---

## 6. The config-as-product principle

The Python is about 1,300 lines and has barely changed. The five plain-text
config files are where all the value is, and they are edited constantly:

| File | What it controls |
|---|---|
| `config/icp.md` | Who the audience is, what makes a story worth posting, how to score. 269 lines. |
| `config/style_guide.md` | How posts are written. Hard rules, voice, structure, sourcing. |
| `config/feeds.txt` | RSS sources, one per line, label and URL separated by a pipe |
| `config/hn_queries.txt` | 28 Hacker News search terms |
| `config/keywords.txt` | Pass-list: an RSS item must match one to enter the pool |
| `config/blocklist.txt` | Block-list: drops webinars, podcasts, award roundups by title |

The owner tunes behavior by editing English, never Python. This matters because
the person who knows whether the output is good is not the person who wants to
open an editor.

Design implication: **push as much agent behavior as possible into
human-readable config that ships with the repo and is version controlled.** The
git history of `icp.md` is a record of what the owner learned about their own
audience.

### The two-stage filter

`keywords.txt` is a pass-list. `blocklist.txt` is a block-list on titles only.

You need both. The pass-list alone lets webinar listings through, because they
mention AI constantly. The block-list alone lets everything unrelated through.
Titles only for the block-list, so an article that merely mentions a webinar in
passing still gets in.

**Word-boundary matching matters at short lengths.** Substring matching on "AI"
also matches "Airlines", "Bahrain" and "campaign". Terms of four characters or
fewer match as whole words; longer terms match as prefixes so "agent" catches
"agents" and "agentic".

---

## 7. Sources: what worked and what did not

We tested this empirically in one morning. The results were not what we
expected.

| Source | Result | Verdict |
|---|---|---|
| Vertical trade press (legal, insurance, fintech) | 5 on-topic items each, daily | **Best by far** |
| Hacker News (Algolia API) | 2-3 items, high comment counts | Good, comment count is the signal |
| Techmeme | 1 useful in 5 | Marginal, kept |
| Reddit (`/top/.rss?t=day`) | 3 hobbyist project posts, 0 relevant | Cut |
| Lobsters | 1 marginal item | Cut |
| Hyperscaler blogs (AWS, Google Cloud) | 10 items, all product release notes | Cut |
| MIT Technology Review | 5 items, 4 about batteries and math | Cut |
| X/Twitter trending | Anime hashtags, K-pop, tennis | Never integrated |

**The X finding is worth understanding.** The original request was "look at
Twitter trends". The trending algorithm surfaces topics that *spike* relative to
their baseline. A steady professional conversation among a few hundred thousand
people can never out-spike a football match. B2B topics structurally cannot
trend. Aggregator sites that scrape those boards inherit the same problem.

**The general lesson: narrow, unglamorous, domain-specific sources beat broad
ranked ones.** One legal-industry trade publication outperformed every
aggregator we tried.

**Hacker News comment count is a better signal than points.** A story with 200
comments is contested, and a contested story is one where an argument exists.
A story with 200 points and 4 comments is consensus, which makes a boring post.

---

## 8. Infrastructure notes

### Hosting

GitHub Actions on a cron schedule. No server. Free for this volume, roughly
2 minutes per run against a 2,000 minute monthly allowance on private repos.

The workflow commits `data/history.json` back to the repo after each run, which
gives free persistent state with a full audit trail. `permissions: contents:
write` is required.

Caveat: GitHub cron fires late under platform load, sometimes 20 minutes.
Schedule earlier than you need. Scheduled workflows are also auto-disabled
after 60 days of repository inactivity.

### Email

Resend, via its HTTP API. Free tier is 3,000/month capped at 100/day, which is
far above the ~22/month this uses.

**Use a real HTTP client, not `urllib`.** From a GitHub Actions IP, `urllib`
requests were blocked by Cloudflare with error 1010, which blocks on client
signature. `urllib` identifies itself as `Python-urllib/3.12` and sends no
other headers. Switching to `httpx`, which ships with the Anthropic SDK,
resolved it. This worked fine from a laptop and only failed in CI, which is a
nasty class of bug.

### macOS certificates

Python installed from python.org ships without root certificates. Every HTTPS
call fails with `CERTIFICATE_VERIFY_FAILED`. Rather than depending on the user
running `Install Certificates.command`, the code builds an SSL context from
`certifi` directly:

```python
import certifi, ssl
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
```

Note that `feedparser.parse(url)` does its own fetching with its own context, so
fetch the bytes yourself and hand them over.

### RSS fetching

Several publishers return 403 to unrecognized clients, so send a normal browser
User-Agent. Some reject an `Accept` header outright with 415, so retry once
without it. Every fetch runs in a thread pool and is individually wrapped, so
one dead feed logs a warning rather than killing the run.

---

## 9. Failure modes for unattended jobs

The realistic failure is not a crash you notice. It is the job dying quietly
and nobody noticing for three weeks.

- Every failure path exits non-zero so GitHub emails on workflow failure
- Degrade rather than die: source collection failure falls back to
  search-only, truncation salvages what completed, a dead feed is skipped
- Log the diagnosis, not just the exception
- Warn when a result looks suspicious (fewer than 3 candidates prints a note
  explaining what to check)

---

## 10. Cost

| Item | Monthly |
|---|---|
| Anthropic API, 2 calls x 22 weekdays | under $10 |
| GitHub Actions | free |
| Resend | free |
| Hacker News, RSS | free |

The research call dominates, because web search pulls a lot of tokens. Lower
`MAX_SEARCHES` to reduce it.

---

## 11. What to reuse

For a developer building similar agents, the transferable pieces are:

1. **`claude_client.py`** — streaming, retry policy, status diagnosis, and the
   JSON salvage. Roughly 170 lines and drop-in reusable.
2. **The two-call pattern** — a cheap, wide research call with tools, then an
   expensive, narrow generation call. Different models for each.
3. **Enforce rules twice** — prompt plus post-generation linter.
4. **Config as English** — behavior lives in markdown the owner edits.
5. **Deduplication memory** — a JSON file of what was produced recently, fed
   back into the prompt as an exclusion list. Without this, a daily agent
   repeats itself within a fortnight.
6. **Draft, do not publish** — for anything going out under a human's name.

---

## 12. Repo layout

```
linkedin-brief/
├── .github/workflows/daily-brief.yml   cron, secrets, history commit
├── config/
│   ├── icp.md              audience and scoring rules
│   ├── style_guide.md      writing rules
│   ├── feeds.txt           RSS sources
│   ├── hn_queries.txt      Hacker News searches
│   ├── keywords.txt        pass-list filter
│   └── blocklist.txt       block-list filter
├── src/
│   ├── main.py             orchestration, CLI flags
│   ├── sources.py          HN + RSS, concurrent, filtered
│   ├── research.py         Claude call 1, scoring
│   ├── draft.py            Claude call 2, linting
│   ├── mailer.py           HTML email via Resend
│   ├── history.py          dedupe memory
│   ├── config.py           env loading, SSL context
│   └── claude_client.py    API wrapper
├── data/history.json       committed by the workflow
├── requirements.txt        anthropic, feedparser, certifi, httpx
└── README.md               setup guide
```

CLI flags worth having on any agent like this:

- `--sources-only` fetch and print sources, no API calls, no cost
- `--dry-run` full pipeline, writes an HTML preview, sends nothing
- `--save-json` dump raw model output for inspection

The free `--sources-only` mode was used dozens of times while tuning feeds. Make
the cheap diagnostic path a first-class feature.
