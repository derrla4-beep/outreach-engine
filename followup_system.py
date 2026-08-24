"""Follow-up email system for banking outreach.

Scans sent outreach threads and sends follow-up replies after periods of silence.
Two cases trigger follow-ups:
  1. Original email sent, no reply at all. Gets up to two follow-ups
     (follow-up #1 after FOLLOWUP_DELAY_DAYS, follow-up #2 after
     SECOND_FOLLOWUP_DELAY_DAYS more), capped at MAX_FOLLOWUPS.
  2. Contact replied, user replied back, contact went quiet again. Gets exactly
     one follow-up total (never escalated to a second nudge).
"""

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from googleapiclient.discovery import build

from gmail_auth import get_gmail_credentials
from config import MY_BACKGROUND
from followup_generator import generate_followup_body

STATE_FILE = Path(__file__).parent / "data" / "followup_state.json"
FOLLOWUP_DELAY_DAYS = 5
SECOND_FOLLOWUP_DELAY_DAYS = 7  # measured from last_followup_at, not original_sent_at
FOLLOWUP_MAX_AGE_DAYS = 21  # don't follow up on threads older than this — too stale
MAX_FOLLOWUPS = 2  # hard cap — never send a 3rd follow-up on any thread
MY_EMAIL = MY_BACKGROUND["email"].lower()

def _school_signals() -> list:
    """Lowercased school name plus its initials, so thread matching is not
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


NETWORKING_SIGNALS = [
    "coffee chat", "coffee call", "quick call", "quick question", "intro",
    "reach out", "networking", "banking", "finance", "internship",
    "your background", "your experience", "advice", "career",
    "connecting",
] + _school_signals()
NON_NETWORKING_SIGNALS = [
    "unsubscribe", "invoice", "receipt", "order confirmation", "your order",
    "shipment", "delivery", "transaction id", "subscription", "payment",
    "password reset", "verification code", "two-factor", "2fa",
    "no-reply", "noreply", "do not reply", "do-not-reply",
    "auto-reply", "autoreply", "out of office", "automatic reply",
]
FOLLOWUP_SIGNALS = [
    "follow up", "follow-up", "following up", "got buried", "previous email",
]


@dataclass
class ThreadStatus:
    thread_id: str
    message_id: str
    raw_message_id: str       # RFC 2822 Message-ID for In-Reply-To threading
    subject: str
    recipient_email: str
    recipient_name: Optional[str]
    original_sent_at: datetime
    last_our_msg_at: datetime
    conversation_history: str = ""   # full thread text for Claude context
    case: str = "no_reply"           # "no_reply", "stalled", or "second_no_reply"
    followup_number: int = 1         # 1 or 2 — which follow-up in the sequence this is


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def _normalize_state_entry(entry: dict) -> dict:
    """Normalize a state entry to the count-based shape used for eligibility checks.

    Legacy entries used a boolean shape (`followup_sent: true` or
    `followup_queued: true`) representing exactly one follow-up sent/queued.
    New entries use `followup_count` (int) + `last_followup_at` (iso str).
    Both shapes are normalized here so callers only ever deal with the new shape.
    """
    if not entry or "followup_count" in entry:
        return entry
    normalized = dict(entry)
    if entry.get("followup_sent") or entry.get("followup_queued"):
        normalized["followup_count"] = 1
        normalized["last_followup_at"] = (
            entry.get("followup_sent_at")
            or entry.get("scheduled_send_at")
            or entry.get("followup_queued_at")
        )
    return normalized


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _decode_body(payload: dict) -> str:
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


def _parse_date(internal_date: str) -> datetime:
    return datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)


def _greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good Morning"
    if hour < 17:
        return "Good Afternoon"
    return "Good Evening"


def _extract_first_name(to_header: str, body: str = "") -> Optional[str]:
    """Pull first name from display name or email greeting. Returns None if uncertain."""
    import re
    if "<" in to_header:
        name_part = to_header.split("<")[0].strip().strip('"')
        if name_part:
            return name_part.split()[0]
    if body:
        m = re.search(r"(?:Hi|Hey|Hello|Dear)\s+([A-Za-z][a-zA-Z\-']+)", body)
        if m:
            return m.group(1)
    return None


def _is_networking_email(subject: str, body: str) -> bool:
    text = (subject + " " + body).lower()
    if any(sig in text for sig in NON_NETWORKING_SIGNALS):
        return False
    return any(sig in text for sig in NETWORKING_SIGNALS)


def _is_followup_email(body: str) -> bool:
    text = body.lower()
    return any(sig in text for sig in FOLLOWUP_SIGNALS)


def _build_conversation_history(thread_msgs: list, my_email: str) -> str:
    """Render a readable chronological transcript of the thread for Claude."""
    parts = []
    for i, tm in enumerate(thread_msgs, 1):
        tm_payload = tm.get("payload", {})
        tm_headers = tm_payload.get("headers", [])
        tm_from = _get_header(tm_headers, "from")
        tm_date = _parse_date(tm["internalDate"])
        tm_body = _decode_body(tm_payload).strip()
        if not tm_body:
            continue
        is_ours = my_email in tm_from.lower()
        sender = "You" if is_ours else f"Contact ({tm_from.split('<')[0].strip() or tm_from})"
        parts.append(
            f"--- Message {i} | {sender} | {tm_date.strftime('%b %d, %Y')} ---\n{tm_body[:1800]}"
        )
    return "\n\n".join(parts)


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


def build_followup_body(
    first_name: str,
    subject: str = "",
    conversation_history: str = "",
    case: str = "no_reply",
    greeting: Optional[str] = None,
) -> str:
    """Build a follow-up body. `greeting` overrides the time-of-day greeting —
    used for the queue path, where the email always lands in the recipient's
    8:30-9:59 AM local window regardless of when this text is generated."""
    return generate_followup_body(
        first_name,
        subject,
        conversation_history,
        greeting if greeting is not None else _greeting(),
        case,
    )


def scan_threads(service, state: dict, now: datetime) -> list[ThreadStatus]:
    """Return threads from the sent folder that need a follow-up."""
    cutoff = (now - timedelta(days=90)).strftime("%Y/%m/%d")
    messages = []
    page_token = None
    while True:
        results = (
            service.users()
            .messages()
            .list(userId="me", q=f"in:sent after:{cutoff}", maxResults=500, pageToken=page_token)
            .execute()
        )
        messages.extend(results.get("messages", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break

    seen_threads: set[str] = set()
    needs_followup: list[ThreadStatus] = []

    for msg_stub in messages:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=msg_stub["id"], format="full")
            .execute()
        )
        thread_id = msg["threadId"]
        if thread_id in seen_threads:
            continue
        seen_threads.add(thread_id)

        # Already handled (dismissed is terminal; count-based state gates further down)
        thread_state = _normalize_state_entry(state.get(thread_id, {}))
        if thread_state.get("followup_dismissed"):
            continue
        if thread_state.get("followup_count", 0) >= MAX_FOLLOWUPS:
            continue

        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        subject = _get_header(headers, "subject")
        to = _get_header(headers, "to")
        body = _decode_body(payload)
        original_sent_at = _parse_date(msg["internalDate"])

        if not _is_networking_email(subject, body):
            continue
        # Skip if the sent message itself is already a follow-up
        if _is_followup_email(body):
            continue

        # Fetch the full thread to analyse reply state
        thread = (
            service.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
            .execute()
        )
        thread_msgs = sorted(
            thread.get("messages", []),
            key=lambda m: int(m["internalDate"]),
        )

        last_our_msg_date: Optional[datetime] = None
        last_our_raw_msg_id: str = _get_header(headers, "message-id")
        last_our_gmail_msg_id: str = msg["id"]
        contact_replied_after_us = False
        contact_replied_at_least_once = False
        # Fallback signal for threads that predate the state file: count our own
        # sent messages that read like a follow-up, and remember the latest one.
        # `followup_count`/`last_followup_at` from state is the source of truth
        # whenever a state entry exists — this is only used when it doesn't.
        fallback_followup_count = 0
        fallback_last_followup_at: Optional[datetime] = None

        for tm in thread_msgs:
            tm_payload = tm.get("payload", {})
            tm_headers = tm_payload.get("headers", [])
            tm_from = _get_header(tm_headers, "from").lower()
            tm_date = _parse_date(tm["internalDate"])
            tm_body = _decode_body(tm_payload)
            tm_raw_id = _get_header(tm_headers, "message-id")

            is_ours = MY_EMAIL in tm_from

            if is_ours:
                if _is_followup_email(tm_body):
                    fallback_followup_count += 1
                    if fallback_last_followup_at is None or tm_date > fallback_last_followup_at:
                        fallback_last_followup_at = tm_date
                last_our_msg_date = tm_date
                last_our_raw_msg_id = tm_raw_id
                last_our_gmail_msg_id = tm["id"]
                # Reset: we replied, now waiting on contact again
                contact_replied_after_us = False
            else:
                if last_our_msg_date and tm_date > last_our_msg_date:
                    contact_replied_after_us = True
                    contact_replied_at_least_once = True

        if last_our_msg_date is None:
            continue
        if contact_replied_after_us:
            continue

        if thread_state:
            followup_count = thread_state.get("followup_count", 0)
            last_followup_at_str = thread_state.get("last_followup_at")
            last_followup_at = (
                datetime.fromisoformat(last_followup_at_str) if last_followup_at_str else None
            )
        else:
            followup_count = fallback_followup_count
            last_followup_at = fallback_last_followup_at

        if followup_count >= MAX_FOLLOWUPS:
            continue

        current_case = "stalled" if contact_replied_at_least_once else "no_reply"

        if followup_count == 0:
            days_since = (now - last_our_msg_date).days
            if days_since < FOLLOWUP_DELAY_DAYS:
                continue
            if days_since > FOLLOWUP_MAX_AGE_DAYS:
                continue
            followup_number = 1
            case = current_case
        elif followup_count == 1:
            prior_case = thread_state.get("case", current_case)
            if prior_case == "stalled":
                # Stalled threads get exactly one follow-up total, then stop.
                continue
            if last_followup_at is None:
                continue
            days_since_followup = (now - last_followup_at).days
            days_since_original = (now - original_sent_at).days
            if days_since_followup < SECOND_FOLLOWUP_DELAY_DAYS:
                continue
            if days_since_original > FOLLOWUP_MAX_AGE_DAYS:
                continue
            followup_number = 2
            case = "second_no_reply"
        else:
            continue

        conversation_history = _build_conversation_history(thread_msgs, MY_EMAIL)

        needs_followup.append(ThreadStatus(
            thread_id=thread_id,
            message_id=last_our_gmail_msg_id,
            raw_message_id=last_our_raw_msg_id,
            subject=subject,
            recipient_email=to,
            recipient_name=_extract_first_name(to, conversation_history or body),
            original_sent_at=original_sent_at,
            last_our_msg_at=last_our_msg_date,
            conversation_history=conversation_history,
            case=case,
            followup_number=followup_number,
        ))

    return needs_followup


def send_followup(service, status: ThreadStatus, state: dict) -> str:
    """Send the follow-up as a reply in the original Gmail thread."""
    body_text = build_followup_body(
        status.recipient_name,
        status.subject,
        status.conversation_history,
        status.case,
    )

    msg = MIMEMultipart("alternative")
    msg["to"] = status.recipient_email
    msg["from"] = MY_BACKGROUND["email"]
    msg["subject"] = f"Re: {status.subject}"
    msg["In-Reply-To"] = status.raw_message_id
    msg["References"] = status.raw_message_id
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(_plain_to_html(body_text), "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw, "threadId": status.thread_id})
        .execute()
    )

    prior = _normalize_state_entry(state.get(status.thread_id, {}))
    prior_count = prior.get("followup_count", 0)
    # Store "stalled" only for the single-follow-up stalled case; a "second_no_reply"
    # send still belongs to the no_reply sequence for future cap checks.
    case_to_store = "stalled" if status.case == "stalled" else "no_reply"

    state[status.thread_id] = {
        "followup_count": prior_count + 1,
        "last_followup_at": datetime.now(tz=timezone.utc).isoformat(),
        "followup_message_id": sent["id"],
        "case": case_to_store,
        "recipient_email": status.recipient_email,
        "recipient_name": status.recipient_name,
        "subject": status.subject,
    }
    _save_state(state)
    return sent["id"]


def _lookup_recipient_tz(recipient_email_field: str) -> str:
    """Best-effort recipient timezone lookup from data/contacts.json (matched by
    email). Falls back to America/New_York if no match or on any error."""
    import re
    m = re.search(r"[\w.+-]+@[\w.-]+", recipient_email_field)
    email = (m.group(0) if m else recipient_email_field).lower()
    try:
        from schedule_sender import infer_timezone
        contacts_file = Path(__file__).parent / "data" / "contacts.json"
        contacts = json.loads(contacts_file.read_text(encoding="utf-8")).get("contacts", [])
        for c in contacts:
            if c.get("email", "").lower() == email:
                return infer_timezone(c.get("firm", ""), c.get("research", "")).key
    except Exception:
        pass
    return "America/New_York"


def run_followup_flow(console=None):
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    from schedule_sender import queue_followup
    from zoneinfo import ZoneInfo

    if console is None:
        console = Console()

    state = _load_state()
    creds = get_gmail_credentials()
    service = build("gmail", "v1", credentials=creds)
    now = datetime.now(tz=timezone.utc)

    console.print("[bold]Scanning sent emails for follow-up opportunities...[/bold]")
    statuses = scan_threads(service, state, now)

    if not statuses:
        console.print("[green]No threads need a follow-up right now.[/green]")
        return

    table = Table(title=f"{len(statuses)} thread(s) need a follow-up")
    table.add_column("Recipient", style="cyan")
    table.add_column("Subject")
    table.add_column("Originally sent")
    table.add_column("Days waiting", justify="right")
    for s in statuses:
        days = (now - s.last_our_msg_at).days
        table.add_row(
            s.recipient_name,
            s.subject[:55],
            s.original_sent_at.strftime("%Y-%m-%d"),
            str(days),
        )
    console.print(table)
    console.print()

    queued_count = 0
    sent_count = 0

    for status in statuses:
        if status.recipient_name is None:
            console.print(f"  [yellow]Could not detect name for {status.recipient_email}[/yellow]")
            status.recipient_name = Prompt.ask("  Enter their first name").strip()

        console.print("[dim]Generating personalized follow-up...[/dim]")
        # Queued sends always land in the recipient's 8:30-9:59 AM local window,
        # so the preview (which becomes the queued body) always opens "Good
        # Morning" regardless of when this text is generated. The immediate-send
        # path (send_followup) regenerates its own body using the real _greeting().
        preview = build_followup_body(
            status.recipient_name,
            status.subject,
            status.conversation_history,
            status.case,
            greeting="Good Morning",
        )
        console.print(Panel(
            f"[bold]To:[/bold] {status.recipient_email}\n"
            f"[bold]Subject:[/bold] Re: {status.subject}\n\n"
            f"{preview}",
            title=f"Follow-up for {status.recipient_name}",
            border_style="yellow",
        ))

        choice = Prompt.ask(
            f"  [bold]{status.recipient_name}[/bold] → action",
            choices=["s", "t", "k"],
            default="t",
            show_choices=True,
            show_default=True,
        ).lower()
        # s = send now, t = schedule next Tue/Wed/Thu morning, k = skip

        if choice == "s":
            try:
                msg_id = send_followup(service, status, state)
                console.print(f"  [green]✓ Sent now (id: {msg_id})[/green]")
                sent_count += 1
            except Exception as e:
                console.print(f"  [red]Failed: {e}[/red]")

        elif choice == "t":
            recipient_tz = _lookup_recipient_tz(status.recipient_email)
            send_at = queue_followup(
                to=status.recipient_email,
                subject=f"Re: {status.subject}",
                body=preview,
                name=status.recipient_name,
                thread_id=status.thread_id,
                in_reply_to=status.raw_message_id,
                references=status.raw_message_id,
                recipient_tz=recipient_tz,
            )
            day_str = send_at.strftime("%A %b %d at %I:%M %p")
            console.print(f"  [cyan]✓ Queued for {day_str}[/cyan]")
            # Mark as queued in state (count-based) so it won't re-appear in next
            # scan until it's eligible for the next follow-up in the sequence.
            prior = _normalize_state_entry(state.get(status.thread_id, {}))
            prior_count = prior.get("followup_count", 0)
            case_to_store = "stalled" if status.case == "stalled" else "no_reply"
            state[status.thread_id] = {
                "followup_count": prior_count + 1,
                "last_followup_at": send_at.isoformat(),
                "case": case_to_store,
                "recipient_email": status.recipient_email,
                "recipient_name": status.recipient_name,
                "subject": status.subject,
            }
            _save_state(state)
            queued_count += 1

        else:
            state[status.thread_id] = {
                "followup_dismissed": True,
                "followup_dismissed_at": datetime.now(tz=timezone.utc).isoformat(),
                "recipient_email": status.recipient_email,
                "recipient_name": status.recipient_name,
                "subject": status.subject,
            }
            _save_state(state)
            console.print("  [dim]Skipped (won't be shown again).[/dim]")

        console.print()

    summary_parts = []
    if sent_count:
        summary_parts.append(f"[green]{sent_count} sent[/green]")
    if queued_count:
        summary_parts.append(f"[cyan]{queued_count} queued[/cyan]")
    console.print(f"[bold]Follow-up run complete — {', '.join(summary_parts) if summary_parts else 'nothing actioned'}.[/bold]")


if __name__ == "__main__":
    run_followup_flow()
