"""Fetch networking emails from Gmail sent folder and extract tone/style patterns."""

import base64
import re
from dataclasses import dataclass
from typing import Optional
from googleapiclient.discovery import build
from gmail_auth import get_gmail_credentials
from config import SENT_EMAILS_TO_SAMPLE, MY_BACKGROUND


@dataclass
class EmailSample:
    subject: str
    body: str
    to: str


def _decode_body(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        text = _decode_body(part)
        if text:
            return text

    return ""


def _extract_recipient(headers: list[dict]) -> str:
    for h in headers:
        if h["name"].lower() == "to":
            return h["value"]
    return ""


def _extract_subject(headers: list[dict]) -> str:
    for h in headers:
        if h["name"].lower() == "subject":
            return h["value"]
    return ""


def _school_signals() -> list:
    """Lowercased school name plus its initials, so the heuristic is not
    hardcoded to one university."""
    school = (MY_BACKGROUND.get("school") or "").strip()
    if not school:
        return []
    words = [w for w in school.split() if w[:1].isalpha()]
    initials = "".join(w[0] for w in words).lower()
    signals = [school.lower()]
    if len(initials) >= 2:
        signals.append(initials + " ")
    return signals


def _looks_like_networking_email(subject: str, body: str) -> bool:
    """Heuristic filter to surface cold outreach / networking emails."""
    networking_signals = [
        "coffee chat", "coffee call", "quick call", "intro", "reach out",
        "networking", "opportunity", "banking", "finance", "internship",
        "your background", "your experience", "your work", "learning from",
        "advice", "career",
    ] + _school_signals()
    text = (subject + " " + body).lower()
    return any(sig in text for sig in networking_signals)


def fetch_sent_networking_emails(
    max_results: int = SENT_EMAILS_TO_SAMPLE,
    query: str = "",
) -> list[EmailSample]:
    """
    Returns up to max_results sent emails that look like networking outreach.
    Broadens the search if not enough matches are found.
    """
    creds = get_gmail_credentials()
    service = build("gmail", "v1", credentials=creds)

    search_query = f"in:sent {query}".strip()
    results = (
        service.users()
        .messages()
        .list(userId="me", q=search_query, maxResults=max_results * 3)
        .execute()
    )

    messages = results.get("messages", [])
    samples: list[EmailSample] = []

    for msg in messages:
        if len(samples) >= max_results:
            break

        full = (
            service.users()
            .messages()
            .get(userId="me", id=msg["id"], format="full")
            .execute()
        )
        payload = full.get("payload", {})
        headers = payload.get("headers", [])
        subject = _extract_subject(headers)
        to = _extract_recipient(headers)
        body = _decode_body(payload).strip()

        if not body:
            continue

        if _looks_like_networking_email(subject, body):
            samples.append(EmailSample(subject=subject, body=body, to=to))

    # If we didn't find enough networking emails, fall back to any sent emails
    if len(samples) < 3:
        for msg in messages:
            if len(samples) >= max_results:
                break
            full = (
                service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="full")
                .execute()
            )
            payload = full.get("payload", {})
            headers = payload.get("headers", [])
            subject = _extract_subject(headers)
            to = _extract_recipient(headers)
            body = _decode_body(payload).strip()
            if body and not any(s.body == body for s in samples):
                samples.append(EmailSample(subject=subject, body=body, to=to))

    return samples[:max_results]


def format_samples_for_prompt(samples: list[EmailSample]) -> str:
    """Format email samples into a string block for the Claude prompt."""
    if not samples:
        return "(No sent email samples found — emails will use a reasonable default style.)"

    parts = []
    for i, s in enumerate(samples, 1):
        parts.append(
            f"--- Email {i} ---\n"
            f"Subject: {s.subject}\n"
            f"To: {s.to}\n\n"
            f"{s.body}\n"
        )
    return "\n".join(parts)
