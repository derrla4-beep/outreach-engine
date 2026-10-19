"""Checks add_emails.py runs on each email Claude Code writes, plus the processed-URL list.

The writing rules themselves live in email_rules.md; this module enforces the ones
that can be checked mechanically (word caps, banned phrases, single ask).
"""

import re
from pathlib import Path

from text_utils import strip_signoff

PROCESSED_URLS_FILE = Path(__file__).parent / "data" / "processed_urls.txt"

# HARD RULE 5 lists banned phrases in prose, but nothing checked them, so they kept
# reaching drafts. Checked here as substrings on the lowercased body, with the
# contraction variants that actually show up ("I'd love to" for "I would love to").
BANNED_PHRASES = (
    "i came across your profile",
    "i would love to",
    "i'd love to",
    "please let me know",
    "genuinely",
    "i was impressed by",
    "your incredible background",
    "hope this email finds you well",
    "i completely understand your schedule",
    # HARD RULE 10b: stiff cover-letter constructions the 4-line format is meant to kill.
    "i am reaching out to express",
    "i wanted to take a moment",
    "i am currently serving as",
    "i am writing to inquire",
)


def validate_email_body(body: str) -> list[str]:
    """Check a body against the numeric/structural rules in email_rules.md (word caps,
    banned phrases, single-ask phrasing). Returns violation descriptions, empty if none."""
    content = strip_signoff(body)
    violations = []

    word_count = len(content.split())
    if word_count >= 130:
        violations.append(
            f"Body is {word_count} words (greeting through Line 4, excluding sign-off) — must be under 130."
        )

    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    for p in paragraphs[1:5]:
        wc = len(p.split())
        if wc >= 35:
            violations.append(f"A body line is {wc} words (must be under 35): \"{p[:60]}\"")

    lowered = content.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            violations.append(f'Contains banned phrase "{phrase}" (HARD RULE 5).')

    ask_line = paragraphs[4] if len(paragraphs) > 4 else content
    question_count = ask_line.count("?")
    if question_count > 1:
        violations.append("Line 4 contains more than one question mark — must be a single ask.")
    elif question_count == 1 and re.search(r"\band (how|what|why|whether|when)\b", ask_line, re.IGNORECASE):
        violations.append(
            "Line 4's question combines two asks joined by 'and' (e.g. 'what X and how Y') — "
            "must be a single one-line-yes question about one thing."
        )

    return violations


def load_processed_urls() -> set[str]:
    if not PROCESSED_URLS_FILE.exists():
        return set()
    return {line.strip() for line in PROCESSED_URLS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()}


def mark_url_processed(url: str):
    PROCESSED_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PROCESSED_URLS_FILE.open("a", encoding="utf-8") as f:
        f.write(url.strip() + "\n")
