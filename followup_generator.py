"""Generate personalized follow-up replies using Claude (voice + full thread context)."""

import json
from typing import Optional

import anthropic

from config import MY_BACKGROUND, VOICE_TEXT, BEST_EMAILS_TEXT, ANTHROPIC_MODEL
from text_utils import clean_email_text

_clean = clean_email_text


def _generic_followup_body(first_name: str, greeting: str) -> str:
    me = MY_BACKGROUND
    return (
        f"{greeting} {first_name},\n\n"
        "Just wanted to bump this in case it got buried in your inbox. Would still love to "
        "grab 15 minutes to hear about your path and any advice you'd have for someone early "
        "in their career.\n\n"
        f"Thank you,\n{me['name']}\n{me['linkedin']}"
    )


def _build_system_prompt(case: str) -> str:
    me = MY_BACKGROUND
    voice_block = ""
    if VOICE_TEXT:
        voice_block = f"""
THE SENDER'S VOICE (match tone; do not copy verbatim or repeat long backstory):
{"=" * 60}
{VOICE_TEXT[:2500]}
{"=" * 60}
"""
    examples_block = ""
    if BEST_EMAILS_TEXT:
        examples_block = f"""
HIS BEST OUTREACH EMAILS (match this tone — direct, specific, not corporate):
{"=" * 60}
{BEST_EMAILS_TEXT[:4000]}
{"=" * 60}
"""

    if case == "stalled":
        case_instruction = (
            "The contact replied at some point but stopped responding after the sender's last message. "
            "Reference the actual exchange naturally — acknowledge what they said or asked. "
            "Do NOT act like this is the first follow-up with no context."
        )
    elif case == "second_no_reply":
        case_instruction = (
            "This is the sender's second and final follow-up; the contact never replied to either message. "
            "Two sentences max, under 60 words. Re-state the ONE specific hook from the original email "
            "in a fresh way (do not repeat the same sentence verbatim), make the same 15-minute ask once, "
            "and close the loop gracefully — for example, a line signaling this is the last note on the "
            "topic, without guilt-tripping or apologizing for emailing again. No \"I know you're busy,\" "
            "no apology for a second email."
        )
    else:
        case_instruction = (
            "The contact never replied to the sender's original outreach. "
            "Reference ONE specific hook from the original email (career move, group, sport, school tie, etc.) "
            "to remind them what made this email worth opening."
        )

    return f"""You ghostwrite SHORT follow-up replies for {me['name']}, a {me['year']} at {me['school']} recruiting for IB.

{voice_block}{examples_block}
SITUATION: {case_instruction}

RULES:
1. Read the full conversation history provided and write a reply that fits it naturally.
2. Do NOT re-introduce the sender from scratch or dump their full background again.
3. Open with a brief pleasantry, then connect to something specific from the conversation.
4. Keep it to 2 short paragraphs plus sign-off (under 80 words total).
5. Re-ask for a 15 minute call in natural language — do not sound desperate or template-like.
6. No em dashes, en dashes, or arrows. No "genuinely", "I would love to", "I came across your profile".
7. Sign-off exactly:
Thank you,
{me['name']}
{me['linkedin']}

Output ONLY JSON: {{"body": "<full email with \\n for line breaks>"}}"""


def _build_user_prompt(
    first_name: str,
    subject: str,
    conversation_history: str,
    greeting: str,
) -> str:
    start = f'{greeting} {first_name},'
    return f"""Write a follow-up reply to {first_name}.

Original subject: {subject}

Full conversation so far (read this carefully — your reply must make sense in this context):
---
{conversation_history[:5000]}
---

Start with: "{start}\""""


def generate_followup_body(
    first_name: str,
    subject: str,
    conversation_history: str,
    greeting: str,
    case: str = "no_reply",
    client: Optional[anthropic.Anthropic] = None,
) -> str:
    """Return a personalized follow-up body, or generic fallback on failure."""
    if not conversation_history.strip():
        return _generic_followup_body(first_name, greeting)

    if client is None:
        client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=512,
            system=_build_system_prompt(case),
            messages=[
                {
                    "role": "user",
                    "content": _build_user_prompt(
                        first_name, subject, conversation_history, greeting
                    ),
                }
            ],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        data = json.loads(raw)
        body = _clean(data["body"].strip())
        if body:
            return body
    except Exception:
        pass

    return _generic_followup_body(first_name, greeting)
