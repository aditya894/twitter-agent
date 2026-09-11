"""Render the daily brief as an email and send it."""

import html
import json
from datetime import date

from config import (
    EMAIL_FROM,
    EMAIL_PROVIDER,
    EMAIL_TO,
    RESEND_API_KEY,
    SSL_CONTEXT,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)

RESEND_ENDPOINT = "https://api.resend.com/emails"

INK = "#0C0E14"
BLUE = "#3A5BFF"
VIOLET = "#6E57F2"
MUTED = "#5A6072"
LINE = "#E4E6ED"


def _option_html(index: int, draft: dict) -> str:
    post = html.escape(draft.get("post", ""))
    topic = html.escape(draft.get("topic", "Untitled"))
    why = html.escape(draft.get("why_this_angle", ""))
    warning = draft.get("warning", "").strip()
    lint = draft.get("lint", [])
    score = draft.get("score")

    flags = ""
    notes = []
    if warning and warning.lower() not in ("none", "none identified", ""):
        notes.append(f"Check before posting: {html.escape(warning)}")
    if lint:
        notes.append("Style flags: " + html.escape(", ".join(lint)))
    if notes:
        flags = (
            f'<div style="margin-top:14px;padding:10px 12px;background:#FFF6E5;'
            f'border-left:3px solid #E0A200;font-size:13px;color:{MUTED};'
            f'line-height:1.5;">' + "<br>".join(notes) + "</div>"
        )

    sources = ""
    if draft.get("sources"):
        items = []
        for s in draft["sources"][:4]:
            title = html.escape(str(s.get("title", "source")))
            url = html.escape(str(s.get("url", "")))
            quality = html.escape(str(s.get("source_quality", "")))
            suffix = f' <span style="color:{MUTED};">({quality})</span>' if quality else ""
            items.append(
                f'<li style="margin-bottom:5px;">'
                f'<a href="{url}" style="color:{BLUE};text-decoration:none;">{title}</a>'
                f"{suffix}</li>"
            )
        sources = (
            f'<div style="margin-top:14px;font-size:13px;color:{MUTED};">'
            f'<strong style="color:{INK};">Sources</strong>'
            f'<ul style="margin:6px 0 0;padding-left:18px;line-height:1.5;">'
            + "".join(items)
            + "</ul></div>"
        )

    discussion = ""
    if draft.get("discussion_url"):
        url = html.escape(str(draft["discussion_url"]))
        discussion = (
            f'<div style="margin-top:12px;font-size:13px;">'
            f'<a href="{url}" style="color:{BLUE};text-decoration:none;">'
            f"Read the argument thread before posting</a>"
            f'<span style="color:{MUTED};"> (worth skimming for the counter-argument)</span></div>'
        )

    comment = ""
    if draft.get("first_comment"):
        comment = (
            f'<div style="margin-top:14px;font-size:13px;color:{MUTED};'
            f'line-height:1.6;"><strong style="color:{INK};">Suggested first '
            f'comment</strong><br>{html.escape(draft["first_comment"])}</div>'
        )

    badge = ""
    if score is not None:
        badge = (
            f'<span style="display:inline-block;margin-left:8px;padding:2px 8px;'
            f'background:{VIOLET};color:#fff;border-radius:10px;font-size:11px;'
            f'font-weight:600;vertical-align:middle;">{score}/10</span>'
        )

    return f"""
    <div style="border:1px solid {LINE};border-radius:10px;padding:22px;margin-bottom:22px;">
      <div style="font-size:11px;letter-spacing:.09em;text-transform:uppercase;
                  color:{BLUE};font-weight:700;">Option {index}</div>
      <div style="font-size:19px;font-weight:700;color:{INK};margin:6px 0 4px;">
        {topic}{badge}
      </div>
      <div style="font-size:13px;color:{MUTED};line-height:1.5;margin-bottom:16px;">{why}</div>
      <div style="white-space:pre-wrap;font-family:-apple-system,BlinkMacSystemFont,
                  'Segoe UI',Helvetica,Arial,sans-serif;font-size:15px;line-height:1.65;
                  color:{INK};background:#F7F8FB;border-radius:8px;padding:18px;">{post}</div>
      {discussion}{comment}{sources}{flags}
    </div>"""


def render(drafts: list[dict], candidate_count: int) -> tuple[str, str]:
    """Return (html_body, plain_text_body)."""
    today = date.today().strftime("%A %d %B %Y")

    if not drafts:
        body = f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
                    Helvetica,Arial,sans-serif;max-width:660px;margin:0 auto;padding:28px;">
          <div style="font-size:22px;font-weight:700;color:{INK};">Nothing worth posting today</div>
          <p style="font-size:15px;color:{MUTED};line-height:1.6;">
            The research pass ran and scored {candidate_count} candidate stories.
            None was worth drafting. Skipping a day is better than posting filler.
          </p>
        </div>"""
        return body, "Nothing scored above the bar today. No post recommended."

    options = "".join(_option_html(i + 1, d) for i, d in enumerate(drafts))

    thin = ""
    scores = [d.get("score") or 0 for d in drafts]
    if scores and max(scores) < 6:
        thin = (
            f'<div style="margin-bottom:22px;padding:12px 14px;background:#FFF6E5;'
            f'border-left:3px solid #E0A200;font-size:13px;color:{MUTED};'
            f'line-height:1.5;">Thin news day. Nothing scored above 6, so these '
            f'are the best of a weak field rather than a recommendation. '
            f'Skipping today is a reasonable call.</div>'
        )

    body = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,
                Arial,sans-serif;max-width:660px;margin:0 auto;padding:28px;background:#fff;">
      <div style="border-bottom:2px solid {INK};padding-bottom:14px;margin-bottom:26px;">
        <div style="font-size:11px;letter-spacing:.11em;text-transform:uppercase;
                    color:{MUTED};font-weight:700;">Daily LinkedIn brief</div>
        <div style="font-size:25px;font-weight:700;color:{INK};margin-top:4px;">{today}</div>
        <div style="font-size:14px;color:{MUTED};margin-top:6px;">
          {len(drafts)} drafts from {candidate_count} candidate stories. Pick one, edit it, post it.
        </div>
      </div>
      {thin}{options}
      <div style="font-size:12px;color:{MUTED};border-top:1px solid {LINE};
                  padding-top:16px;line-height:1.6;">
        Post the text as-is with the line breaks intact. Put the source link in the
        first comment, not the body. Reply to this email to change what gets researched.
      </div>
    </div>"""

    plain_parts = [f"Daily LinkedIn brief. {today}\n"]
    for i, d in enumerate(drafts, 1):
        plain_parts.append(
            f"--- OPTION {i}: {d.get('topic','')} ---\n\n{d.get('post','')}\n"
        )
        if d.get("first_comment"):
            plain_parts.append(f"First comment: {d['first_comment']}\n")
    return body, "\n".join(plain_parts)


def _send_resend(subject: str, html_body: str, text_body: str) -> None:
    """Send via the Resend HTTP API.

    Uses httpx rather than urllib. urllib identifies itself as
    "Python-urllib/x.y" and sends no other headers, which Cloudflare blocks
    with error 1010 when the request comes from a shared CI address. httpx
    ships with the Anthropic SDK, so this adds nothing to install.
    """
    import httpx

    payload = {
        "from": EMAIL_FROM,
        "to": EMAIL_TO,
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }

    try:
        response = httpx.post(
            RESEND_ENDPOINT,
            json=payload,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "linkedin-brief/1.0",
            },
            timeout=30.0,
        )
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not reach Resend: {exc}") from exc

    if response.status_code < 300:
        body = response.json()
        print(f"Resend accepted the message. id={body.get('id', 'unknown')}")
        return

    detail = response.text
    hint = ""
    code = response.status_code
    if code == 403 and "1010" in detail:
        hint = (
            "\nHint: Cloudflare blocked the client signature rather than "
            "Resend rejecting the request. Check that httpx is installed."
        )
    elif code == 403 and "domain" in detail.lower():
        hint = (
            "\nHint: EMAIL_FROM must be on a domain verified in Resend. "
            "Before you verify one, use onboarding@resend.dev, which only "
            "delivers to the address you signed up with."
        )
    elif code == 401:
        hint = "\nHint: check RESEND_API_KEY. It should start with 're_'."
    elif code == 422:
        hint = (
            "\nHint: Resend rejected a field. Usually EMAIL_FROM is not a "
            "valid address on a verified domain."
        )
    elif code == 429:
        hint = "\nHint: the free tier caps at 100 emails a day."
    raise RuntimeError(f"Resend returned {code}: {detail}{hint}")


def _send_smtp(subject: str, html_body: str, text_body: str) -> None:
    """Fallback path for anyone who would rather use Gmail or their own server."""
    import smtplib
    from email.message import EmailMessage

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = EMAIL_FROM or SMTP_USER
    message["To"] = ", ".join(EMAIL_TO)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=45) as server:
        server.starttls(context=SSL_CONTEXT)
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)
    print("SMTP accepted the message.")


def send(drafts: list[dict], candidate_count: int) -> None:
    html_body, text_body = render(drafts, candidate_count)

    subject = (
        f"LinkedIn brief, {date.today().strftime('%d %b')}: "
        + (f"{len(drafts)} options" if drafts else "nothing worth posting")
    )

    if EMAIL_PROVIDER == "resend":
        _send_resend(subject, html_body, text_body)
    else:
        _send_smtp(subject, html_body, text_body)
