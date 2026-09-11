"""Turn scored candidates into finished, paste-ready LinkedIn posts."""

import json
import re

import claude_client as cc
from config import DRAFT_MODEL, NUM_OPTIONS, load_prompt

SYSTEM_TEMPLATE = """You write LinkedIn posts for one specific person.

<style_guide>
{style}
</style_guide>

You will be given researched news stories. Write one post per story.

Every factual claim must trace to the supplied research. If a story's facts are
too thin to support a post, say so in the "warning" field rather than padding
with invented detail.

Return ONLY a JSON array. No preamble, no code fences, no commentary."""

USER_TEMPLATE = """Write {n} LinkedIn posts, one for each story below.

Make them genuinely different from each other in argument, not just in wording.
The reader will pick one and discard the rest.

<stories>
{stories}
</stories>

Return a JSON array, one object per story, same order:

{{
  "topic": "short label for this post, 4 to 8 words",
  "hook": "the first line of the post, repeated here for scanning",
  "post": "the complete post text, plain text, line breaks as \\n",
  "word_count": 210,
  "first_comment": "the source link and one line of context, to be posted as the first comment",
  "why_this_angle": "one sentence on what this post argues that others will not",
  "warning": "anything the author should check or soften before posting, or 'none'"
}}"""

EM_DASH = "\u2014"
EN_DASH = "\u2013"
# American spelling is a hard rule. A generic -ise pattern would flag
# "raised", "advised" and "promised", so use an explicit stem list instead.
_BRITISH_STEMS = [
    "organis", "recognis", "analyse", "analysing", "criticis", "prioritis", "optimis",
    "realis", "specialis", "categoris", "standardis", "minimis", "maximis",
    "summaris", "utilis", "authoris", "customis", "digitis", "formalis",
    "generalis", "modernis", "normalis", "personalis", "rationalis",
    "visualis", "behaviour", "colour", "favour", "labour", "honour",
    "rumour", "neighbour", "defence", "licence", "centre", "metre",
    "programme", "fulfilment", "enrolment", "modelling", "labelled",
    "cancelled", "travelled", "whilst", "amongst",
]

BANNED_PATTERNS = [
    (r"\bsmall team\b", "uses the word 'small' about the team"),
    (r"\*\*", "contains markdown bold"),
    (r"https?://", "contains a link in the body"),
    (r"(thoughts|agree|what do you think)\?\s*$", "generic closing question"),
    (r"\b\d+(\.\d+)? (million|billion) dollars\b", "write $550m, not spelled out"),
] + [(rf"\b\w*{stem}\w*\b", f"British spelling: {stem}") for stem in _BRITISH_STEMS]


def lint(post: str) -> list[str]:
    """Catch house style violations the model let through.

    Cheaper and more reliable than asking the model to self-check.
    """
    issues = []
    if EM_DASH in post:
        issues.append("contains an em dash")
    if EN_DASH in post:
        issues.append("contains an en dash")
    for pattern, message in BANNED_PATTERNS:
        if re.search(pattern, post, flags=re.IGNORECASE | re.MULTILINE):
            issues.append(message)

    words = len(post.split())
    if words > 300:
        issues.append(f"long at {words} words")
    if words < 100:
        issues.append(f"short at {words} words")

    # A post with no blank lines will render as a wall of text.
    if post.count("\n\n") < 2:
        issues.append("not enough line breaks for LinkedIn rendering")

    return issues


def _autofix(post: str) -> str:
    """Fix the mechanical violations rather than regenerating the whole post."""
    return post.replace(EM_DASH, ".").replace(EN_DASH, "-")


def write(candidates: list[dict]) -> list[dict]:
    """Draft one post per candidate. Returns drafts with lint results attached."""
    selected = candidates[:NUM_OPTIONS]
    if not selected:
        return []

    style = load_prompt("style_guide.md")
    stories = json.dumps(selected, indent=2, ensure_ascii=False)

    raw = cc.call(
        model=DRAFT_MODEL,
        system=SYSTEM_TEMPLATE.format(style=style),
        user=USER_TEMPLATE.format(n=len(selected), stories=stories),
        max_tokens=8000,
    )

    drafts = cc.extract_json(raw)
    if not isinstance(drafts, list):
        raise ValueError("Drafting did not return a list of posts.")

    for draft, candidate in zip(drafts, selected):
        draft["post"] = _autofix(draft.get("post", ""))
        draft["lint"] = lint(draft["post"])
        draft["score"] = candidate.get("score")
        draft["sources"] = candidate.get("sources", [])
        draft["risks"] = candidate.get("risks", "")
        draft["discussion_url"] = candidate.get("discussion_url")

    return drafts
