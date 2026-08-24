"""Scheduled email queue: hold emails and send them on the next Tue/Wed/Thu 8:30-9:59 AM in the recipient's local timezone."""

import base64
import json
import random
from datetime import datetime, timedelta, timezone as _utc
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from config import MY_BACKGROUND
from gmail_auth import get_gmail_credentials

QUEUE_FILE = Path(__file__).parent / "data" / "scheduled_queue.json"
EST = ZoneInfo("America/New_York")

# Tuesday=1, Wednesday=2, Thursday=3 (Python weekday: Mon=0 … Sun=6)
TARGET_WEEKDAYS = {1, 2, 3}
DAY_NAMES = {1: "Tuesday", 2: "Wednesday", 3: "Thursday"}

# Ordered longest-match first to avoid "dc" matching "bangalore"
_TZ_MAP = [
    (["hong kong", "hongkong"],                              "Asia/Hong_Kong"),
    (["singapore", " sg,", "sgp"],                          "Asia/Singapore"),
    (["united arab", "dubai", "abu dhabi"],                  "Asia/Dubai"),
    (["mumbai", "bangalore", "bengaluru", "delhi", "india"], "Asia/Kolkata"),
    (["tokyo", "japan"],                                     "Asia/Tokyo"),
    (["sydney", "melbourne", "brisbane", "australia"],       "Australia/Sydney"),
    (["london", "united kingdom", "england", "britain"],     "Europe/London"),
    (["paris", "france"],                                    "Europe/Paris"),
    (["frankfurt", "munich", "berlin", "germany"],           "Europe/Berlin"),
    (["toronto", "montreal", "ottawa", "canada"],            "America/Toronto"),
    (["chicago", "illinois"],                                "America/Chicago"),
    (["denver", "colorado", "mountain"],                     "America/Denver"),
    (["los angeles", "san francisco", "seattle", "california", "pacific", "la,", " la "],
                                                             "America/Los_Angeles"),
    (["new york", "nyc", "manhattan", "boston", "philadelphia",
      "washington", "east coast", "northeast"],              "America/New_York"),
]


def infer_timezone(location: str = "", notes: str = "") -> ZoneInfo:
    """Return the best-matching IANA timezone for a recipient's location string."""
    combined = (location + " " + notes).lower()
    for keywords, tz_name in _TZ_MAP:
        if any(kw in combined for kw in keywords):
            return ZoneInfo(tz_name)
    return ZoneInfo("America/New_York")


def _random_morning_time(candidate: datetime) -> datetime:
    """Return candidate's date with a random time in the 8:30-9:59 AM window."""
    minutes_after_midnight = random.randint(510, 599)  # 510 = 8:30 AM, 599 = 9:59 AM
    hour = minutes_after_midnight // 60
    minute = minutes_after_midnight % 60
    return candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)


def next_send_time(tz: ZoneInfo = EST) -> datetime:
    """Return the next Tue/Wed/Thu at a random minute between 8:30-9:59 AM in the given timezone."""
    now = datetime.now(tz=tz)
    for days_ahead in range(1, 8):
        candidate = now + timedelta(days=days_ahead)
        if candidate.weekday() in TARGET_WEEKDAYS:
            return _random_morning_time(candidate)
    # Safe fallback: next Tuesday
    days_to_tuesday = (1 - now.weekday()) % 7 or 7
    return _random_morning_time(now + timedelta(days=days_to_tuesday))


def queue_email(
    to: str,
    subject: str,
    body: str,
    name: str = "",
    linkedin_url: str = "",
    recipient_tz: str = "America/New_York",
) -> datetime:
    """Add an email to the send queue. Returns the scheduled send time in the recipient's local timezone."""
    tz = ZoneInfo(recipient_tz)
    send_at = next_send_time(tz)

    queue = _load_queue()
    queue.append({
        "to": to,
        "subject": subject,
        "body": body,
        "name": name,
        "linkedin_url": linkedin_url,
        "scheduled_at": send_at.isoformat(),
        "recipient_tz": recipient_tz,
        "queued_at": datetime.now(tz=_utc.utc).isoformat(),
    })
    _save_queue(queue)
    return send_at


def queue_followup(
    to: str,
    subject: str,
    body: str,
    name: str = "",
    thread_id: str = "",
    in_reply_to: str = "",
    references: str = "",
    recipient_tz: str = "America/New_York",
) -> datetime:
    """Queue a follow-up reply for the next Tue/Wed/Thu send. Stores thread metadata for proper Gmail threading."""
    tz = ZoneInfo(recipient_tz)
    send_at = next_send_time(tz)

    queue = _load_queue()
    queue.append({
        "to": to,
        "subject": subject,
        "body": body,
        "name": name,
        "thread_id": thread_id,
        "in_reply_to": in_reply_to,
        "references": references,
        "scheduled_at": send_at.isoformat(),
        "recipient_tz": recipient_tz,
        "queued_at": datetime.now(tz=_utc.utc).isoformat(),
        "type": "followup",
    })
    _save_queue(queue)
    return send_at


def list_queue() -> list:
    """Return all pending scheduled emails."""
    return _load_queue()


def send_due_emails(console=None) -> int:
    """Send all emails whose scheduled_at time has passed. Returns count sent."""
    from rich.console import Console
    if console is None:
        console = Console()

    queue = _load_queue()
    now = datetime.now(tz=_utc.utc)

    due = [e for e in queue if datetime.fromisoformat(e["scheduled_at"]) <= now]
    remaining = [e for e in queue if datetime.fromisoformat(e["scheduled_at"]) > now]

    if not due:
        console.print("[green]No scheduled emails are due yet.[/green]")
        return 0

    creds = get_gmail_credentials()
    service = build("gmail", "v1", credentials=creds)
    sent_count = 0

    for entry in due:
        try:
            _send_entry(service, entry)
            label = entry["name"] or entry["to"]
            scheduled = entry["scheduled_at"]
            console.print(f"  [green]✓ Sent to {label} (was scheduled {scheduled})[/green]")
            sent_count += 1
        except Exception as e:
            console.print(f"  [red]Failed sending to {entry.get('to', '?')}: {e}[/red]")
            remaining.append(entry)  # Keep failed ones so they retry next run

    _save_queue(remaining)
    return sent_count


def _send_entry(service, entry: dict):
    msg = MIMEMultipart("alternative")
    msg["to"] = entry["to"]
    msg["from"] = MY_BACKGROUND["email"]
    msg["subject"] = entry["subject"]
    if entry.get("in_reply_to"):
        msg["In-Reply-To"] = entry["in_reply_to"]
        msg["References"] = entry.get("references", entry["in_reply_to"])
    msg.attach(MIMEText(entry["body"], "plain"))
    msg.attach(MIMEText(_plain_to_html(entry["body"]), "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    send_body = {"raw": raw}
    if entry.get("thread_id"):
        send_body["threadId"] = entry["thread_id"]
    service.users().messages().send(userId="me", body=send_body).execute()


def _plain_to_html(body: str) -> str:
    import html as html_lib
    paragraphs = body.strip().split("\n\n")
    parts = []
    for para in paragraphs:
        lines = para.strip().splitlines()
        escaped = "<br>".join(html_lib.escape(line) for line in lines)
        parts.append(f"<p>{escaped}</p>")
    return (
        '<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#000;">'
        + "".join(parts)
        + "</div>"
    )


def _load_queue() -> list:
    if QUEUE_FILE.exists():
        return json.loads(QUEUE_FILE.read_text())
    return []


def _save_queue(queue: list):
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(queue, indent=2))
