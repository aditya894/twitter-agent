"""
writer.py — AI-powered content generation via OpenRouter.

Two LLM calls per agent run:
  1. pick_best_topics()   — choose top 3 most "postable" topics
  2. generate_post()      — rewrite tweets into a toned-down LinkedIn post
"""
import json

from openai import OpenAI

from config import OPENROUTER_API_KEY, CLAUDE_MODEL, MAX_TOPICS

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)


# ─────────────────────────────────────────────────────────────────────
# LLM Call 1 — Topic selection
# ─────────────────────────────────────────────────────────────────────

def pick_best_topics(topics: list[str], n: int = MAX_TOPICS) -> list[str]:
    """
    Ask the model to pick the N most interesting topics for a professional
    LinkedIn audience from a raw list of Google News headlines.
    """
    headline_list = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics))

    prompt = f"""You are a LinkedIn content strategist for a tech professional with an Indian audience.

Here are today's trending tech headlines:
{headline_list}

Pick the {n} best topics to write LinkedIn posts about. Criteria:
- High professional relevance (tech, AI, startups, India market)
- Has a non-obvious angle or insight potential
- Broad enough that a general tech audience cares
- Avoid pure political news or celebrity gossip

Return ONLY a JSON array of {n} topic strings (exact match from the list above).
Example: ["Topic A", "Topic B", "Topic C"]"""

    response = client.chat.completions.create(
        model=CLAUDE_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()
    try:
        selected = json.loads(raw)
        return selected[:n]
    except json.JSONDecodeError:
        # Fallback: just return the first N topics
        return topics[:n]


# ─────────────────────────────────────────────────────────────────────
# LLM Call 2 — Post generation
# ─────────────────────────────────────────────────────────────────────

def generate_post(topic: str, tweets: list[dict]) -> dict:
    """
    Given a topic and raw tweet content, generate a professional
    LinkedIn post with a toned-down, insightful voice.

    Returns:
        {
            "post": str,          # full post text with hashtags
            "hashtags": list[str],
            "hook": str,          # one-line summary for dashboard preview
        }
    """
    if tweets:
        tweet_block = "\n\n".join(
            f"{t['author']}: {t['text']}\nSource: {t['url']}"
            for t in tweets
        )
        source_note = f"Based on {len(tweets)} tweet(s) found on Twitter/X."
    else:
        tweet_block = "(No specific tweets found — generate from general knowledge about this topic)"
        source_note = "Generated from general knowledge about this topic."

    prompt = f"""You are a professional LinkedIn content writer. Your posts are calm, insightful, and always add value — never clickbait.

TOPIC: {topic}

SOURCE TWEETS FROM TWITTER/X:
{tweet_block}

TASK: Write a LinkedIn post about this topic. Rules:
1. Length: 150–250 words
2. Tone: Calm, professional, informative — NOT sensational
3. Structure:
   - Open with a strong, specific observation or data point (NOT "I")
   - Add context or nuance the tweets missed
   - Offer a clear implication or takeaway for professionals
   - End with a genuine open question to drive comments
4. Hashtags: Exactly 3, placed at the very end on their own line
5. Do NOT write "LinkedIn post:" or any preamble — just the post
6. Do NOT copy tweet text verbatim — synthesise and elevate

Also return:
- hook: one punchy sentence summarising the post (for dashboard preview)
- hashtags: array of the 3 hashtags used

Return as valid JSON only:
{{
  "post": "full post text including hashtags at end",
  "hook": "one-line preview text",
  "hashtags": ["#Tag1", "#Tag2", "#Tag3"]
}}"""

    response = client.chat.completions.create(
        model=CLAUDE_MODEL,
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if model wraps in ```json
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: treat entire response as the post
        result = {
            "post": raw,
            "hook": topic,
            "hashtags": [],
        }

    result["source_note"] = source_note
    return result
