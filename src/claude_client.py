"""Thin wrapper around the Anthropic SDK with retries and JSON extraction."""

import json
import re
import time
from typing import Any

import anthropic

from config import ANTHROPIC_API_KEY

_client = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def call(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 8000,
    tools: list | None = None,
    retries: int = 3,
) -> str:
    """Send one message and return the concatenated text blocks.

    Server tools such as web_search run inside the API call, so the response
    may contain tool_use and tool_result blocks interleaved with text. We keep
    only the text blocks, which is where the model's actual answer lives.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if tools:
        kwargs["tools"] = tools

    last_error = None
    for attempt in range(retries):
        try:
            # Stream rather than using messages.create. The SDK refuses
            # non-streaming requests whose max_tokens implies a call that could
            # run past ten minutes, and the research call needs a large budget
            # because server-side web search consumes output tokens. Streaming
            # removes that ceiling. We still wait for the whole message.
            with client().messages.stream(**kwargs) as stream:
                response = stream.get_final_message()

            if getattr(response, "stop_reason", None) == "max_tokens":
                print(
                    "Warning: hit the max_tokens cap. Output is truncated. "
                    "Raise max_tokens or ask for fewer candidates."
                )
            return "\n".join(
                block.text
                for block in response.content
                if getattr(block, "type", None) == "text"
            ).strip()
        except anthropic.APIStatusError as exc:
            status = getattr(exc, "status_code", None)

            # 4xx other than rate limiting means the request itself is wrong:
            # no credit, bad key, malformed body. Retrying cannot fix any of
            # those, so fail immediately with a usable message instead of
            # burning three attempts and 20 seconds of backoff.
            if status is not None and 400 <= status < 500 and status != 429:
                raise RuntimeError(_diagnose(status, exc)) from exc

            last_error = exc
            if attempt == retries - 1:
                break
            time.sleep(4 ** (attempt + 1))
        except anthropic.APIConnectionError as exc:
            last_error = exc
            if attempt == retries - 1:
                break
            time.sleep(4 ** (attempt + 1))

    raise RuntimeError(f"Claude API failed after {retries} attempts: {last_error}")


def _diagnose(status: int, exc: Exception) -> str:
    """Turn an API status code into something actionable."""
    text = str(exc)
    hints = {
        400: (
            "Bad request. If this mentions credit balance, add credit at "
            "console.anthropic.com under Plans & Billing."
        ),
        401: "Authentication failed. Check ANTHROPIC_API_KEY starts with 'sk-ant-'.",
        403: "Forbidden. The API key may be revoked or lack permission.",
        404: (
            "Not found. Usually a model name that does not exist. Check "
            "RESEARCH_MODEL and DRAFT_MODEL in your .env."
        ),
        413: "Request too large. Lower MAX_POOL_ITEMS in your .env.",
    }
    hint = hints.get(status, "Check the message above.")
    return f"Anthropic API returned {status}, not retrying.\n{hint}\n\n{text}"


def _salvage_array(text: str) -> list | None:
    """Recover the complete objects from a truncated JSON array.

    When the model hits the output token cap mid-array, the response is
    unparseable but most of it is perfectly good. Four usable candidates beat
    a failed run, so decode objects one at a time and stop at the broken one.
    """
    start = text.find("[")
    if start == -1:
        return None

    decoder = json.JSONDecoder()
    index = start + 1
    items: list = []

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

    return items or None


def extract_json(text: str) -> Any:
    """Pull a JSON array or object out of a model response.

    Models sometimes wrap JSON in code fences or add a sentence before it,
    even when told not to. This handles both without being clever about it.
    """
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fall back to the outermost bracketed span.
    for opener, closer in (("[", "]"), ("{", "}")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue

    # Last resort: the array was cut off mid-flight. Keep what is complete.
    salvaged = _salvage_array(cleaned)
    if salvaged:
        print(
            f"Warning: model response was truncated. Salvaged "
            f"{len(salvaged)} complete items and discarded the rest."
        )
        return salvaged

    raise ValueError(f"Could not parse JSON from model response:\n{text[:1000]}")
