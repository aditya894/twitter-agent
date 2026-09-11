"""
writer.py — AI-powered content generation via OpenRouter.

Two LLM calls per agent run:
  1. pick_best_topics()   — choose top 3 most "postable" topics
  2. generate_post()      — turn news context into an engaging LinkedIn post
"""
import json
import re

from openai import OpenAI

from config import OPENROUTER_API_KEY, CLAUDE_MODEL, MAX_TOPICS

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

_JSON_SYSTEM = (
    "You are a JSON API. Output ONLY valid JSON — no markdown fences, "
    "no explanations, no reasoning steps, no preamble. Raw JSON only."
)


def _extract_json(raw: str) -> dict | list:
    """
    Robustly extract JSON from model output even when CoT reasoning precedes it.
    CoT models output JSON at the END — scan from the right to find it.
    """
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Scan from the right: find last complete {...} or [...]
    for opener, closer in (('{', '}'), ('[', ']')):
        end = raw.rfind(closer)
        if end == -1:
            continue
        # Walk left matching brackets to find the corresponding opener
        depth = 0
        for i in range(end, -1, -1):
            if raw[i] == closer:
                depth += 1
            elif raw[i] == opener:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[i:end + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"No JSON found in model output: {raw[:200]}")


# ─────────────────────────────────────────────────────────────────────
# LLM Call 1 — Topic selection
# ─────────────────────────────────────────────────────────────────────

def pick_best_topics(topics: list[str], n: int = MAX_TOPICS) -> list[str]:
    headline_list = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics))
    prompt = f"""Pick the {n} best topics from this list to write LinkedIn posts about for an Indian tech/startup audience.

Headlines:
{headline_list}

Criteria: high professional relevance, non-obvious insight potential, broad tech/AI/startup appeal.
Avoid pure politics or celebrity news.

Return ONLY a JSON array of {n} strings (exact matches from the list).
Example: ["Topic A", "Topic B", "Topic C"]"""

    response = client.chat.completions.create(
        model=CLAUDE_MODEL,
        max_tokens=300,
        messages=[
            {"role": "system", "content": _JSON_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
    raw = response.choices[0].message.content.strip()
    try:
        selected = _extract_json(raw)
        if isinstance(selected, list):
            return [str(t) for t in selected[:n]]
    except (ValueError, TypeError):
        pass
    return topics[:n]


# ─────────────────────────────────────────────────────────────────────
# LLM Call 2 — Post generation
# ─────────────────────────────────────────────────────────────────────

def generate_post(topic: str, articles: list[dict]) -> dict:
    """
    Turn a topic + news articles into a ready-to-publish LinkedIn post.
    Returns: {post, hook, hashtags, source_note}
    """
    if articles:
        context_block = "\n\n".join(
            f"[{a['author']}] {a['text']}\nURL: {a['url']}"
            for a in articles
        )
        source_note = f"Based on {len(articles)} news article(s)."
    else:
        context_block = "(No articles found — use your knowledge of this topic.)"
        source_note = "Generated from general knowledge."

    prompt = f"""Write a LinkedIn post about the topic below using the news context provided.

TOPIC: {topic}

NEWS CONTEXT:
{context_block}

POST REQUIREMENTS:
- 180-250 words
- Tone: calm, sharp, insightful — never sensational or clickbait
- Structure (do NOT label these sections):
  1. Open with one specific data point, fact, or observation — NOT "I"
  2. Paragraph: what this really signals + a nuance most people miss
  3. Paragraph: concrete takeaway for Indian tech/startup professionals
  4. End with a genuine open question that invites comments
- Exactly 3 relevant hashtags on their own line at the very end
- Do NOT include any preamble, title, or "LinkedIn post:" label
- Write the post text directly — no meta-commentary

Return ONLY this JSON (no other text before or after):
{{"post": "full post text here including hashtags at end", "hook": "one punchy sentence that teases the post", "hashtags": ["#Tag1", "#Tag2", "#Tag3"]}}"""

    response = client.chat.completions.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": _JSON_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
    raw = response.choices[0].message.content.strip()
    try:
        result = _extract_json(raw)
        if not isinstance(result, dict):
            raise ValueError("not a dict")
    except (ValueError, TypeError):
        result = {"post": raw, "hook": topic, "hashtags": []}

    result["source_note"] = source_note
    return result
