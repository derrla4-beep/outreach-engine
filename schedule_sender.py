"""Email queue: add_emails.py puts emails here, `python main.py --send-now` sends them.

Each entry keeps a suggested send time (next weekday 9:00-10:59 AM in the recipient's
timezone), but nothing sends on its own: every send is started by hand.
"""

import base64
import json
import random
import re
import time
from datetime import datetime, timedelta, timezone as _utc
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from zoneinfo import ZoneInfo

import sent_log
from config import MY_BACKGROUND
from text_utils import attach_bodies, ensure_signoff

QUEUE_FILE = Path(__file__).parent / "data" / "scheduled_queue.json"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EST = ZoneInfo("America/New_York")

# Weekdays only, Mon-Fri (Python weekday: Mon=0 … Sun=6). Never weekends.
TARGET_WEEKDAYS = {0, 1, 2, 3, 4}

# Send window, as minutes after local midnight: 9:00 AM through 10:59 AM.
SEND_WINDOW_START_MIN = 9 * 60    # 540
SEND_WINDOW_END_MIN = 11 * 60 - 1  # 659

# Pause between emails in a bulk --send-now run.
SEND_SPACING_SECONDS = 2

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
    """Return candidate's date with a random time in the 9:00-10:59 AM window."""
    minutes_after_midnight = random.randint(SEND_WINDOW_START_MIN, SEND_WINDOW_END_MIN)
    hour = minutes_after_midnight // 60
    minute = minutes_after_midnight % 60
    return candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)


def next_send_time(tz: ZoneInfo = EST) -> datetime:
    """Return the next weekday at a random minute between 9:00-10:59 AM in the given timezone."""
    now = datetime.now(tz=tz)
    for days_ahead in range(1, 8):
        candidate = now + timedelta(days=days_ahead)
        if candidate.weekday() in TARGET_WEEKDAYS:
            return _random_morning_time(candidate)
    # Unreachable while TARGET_WEEKDAYS covers Mon-Fri, but keep a safe fallback.
    days_to_monday = (0 - now.weekday()) % 7 or 7
    return _random_morning_time(now + timedelta(days=days_to_monday))


def queue_email(
    to: str,
    subject: str,
    body: str,
    name: str = "",
    linkedin_url: str = "",
    recipient_tz: str = "America/New_York",
) -> datetime:
    """Add an email to the send queue. Returns the scheduled send time in the recipient's local timezone."""
    # Guard the address at the boundary. Single keystrokes ("k", "d", "x") have been
    # captured here from menu prompts before, which parks a real contact in the queue
    # as permanently unsendable and is only noticed when the send silently fails.
    if not _EMAIL_RE.match((to or "").strip()):
        raise ValueError(
            f"Refusing to queue {name or 'contact'}: {to!r} is not a valid email address."
        )

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


def send_queue_interactive(console=None, limit=None, dry_run=False, review=False,
                           ask=None, sleep=time.sleep) -> int:
    """Send the queue oldest-first.

    By default it shows the whole batch as one table and sends everything after a
    single typed "send". With review=True it walks the queue one email at a time and
    sends only the ones you approve; entries you skip keep their place in the queue.

    Each entry's stored subject and body are sent verbatim. Right before each send,
    Gmail's Sent folder is checked so nobody gets the same cold email twice, and every
    send is recorded in data/sent_log.json so --followups and --stats can find its thread.
    """
    from rich.console import Console
    from rich.markup import escape
    from rich.prompt import Prompt
    if console is None:
        console = Console()
    if ask is None:
        ask = Prompt.ask

    queue = _load_queue()
    if not queue:
        console.print("[green]No emails in the scheduled queue.[/green]")
        return 0

    queue.sort(key=lambda e: e["scheduled_at"])
    batch = queue[:limit] if limit is not None else list(queue)
    log = sent_log.load()

    if not review:
        from rich.table import Table
        table = Table(title=f"{len(batch)} of {len(queue)} queued email(s)")
        table.add_column("#", justify="right")
        table.add_column("Contact", style="bold")
        table.add_column("Email")
        table.add_column("Subject")
        for i, entry in enumerate(batch, 1):
            table.add_row(str(i), escape(entry.get("name") or ""), escape(entry["to"]),
                          escape(entry["subject"]))
        console.print(table)
        if dry_run:
            console.print("[yellow]DRY RUN - nothing sent. Add --review to read each email.[/yellow]")
            return len(batch)
        answer = ask(f"\nType 'send' to send all {len(batch)} email(s), anything else to cancel",
                     default="")
        if answer.strip().lower() != "send":
            console.print("[dim]Cancelled - nothing sent.[/dim]")
            return 0

    if dry_run:
        console.print(
            f"[yellow]DRY RUN — Reviewing {len(batch)} email(s) — nothing will be sent.[/yellow]\n"
        )
        service = None
    else:
        backup = QUEUE_FILE.with_name(
            f"scheduled_queue.pre-send-{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak.json"
        )
        backup.write_text(json.dumps(queue, indent=2))
        sent_log.prune_backups(QUEUE_FILE.parent, "scheduled_queue.pre-send-*.bak.json")
        console.print(f"[dim]Queue backed up to {backup.name}[/dim]")
        verb = "Reviewing" if review else "Sending"
        console.print(f"[bold]{verb} {len(batch)} of {len(queue)} queued email(s).[/bold]\n")
        from gmail_auth import gmail_service
        service = gmail_service()

    sent_count = 0

    for i, entry in enumerate(batch, 1):
        label = escape(entry.get("name") or entry["to"])
        console.print(f"[bold cyan]── [{i}/{len(batch)}] {label} <{escape(entry['to'])}>[/bold cyan]")

        # An interrupted run can log a send before the queue file is rewritten, so
        # never trust the queue alone: the sent log decides what already went out.
        if sent_log.already_sent(log, entry["to"], entry["subject"]):
            console.print("[yellow]Already sent (in data/sent_log.json) - removing from queue, not sending again.[/yellow]\n")
            if not dry_run:
                queue = [e for e in queue if e is not entry]
                _save_queue(queue)
            continue

        if review:
            console.print(f"[bold]Subject:[/bold] {escape(entry['subject'])}")
            console.print()
            console.print(ensure_signoff(entry["body"]), markup=False)
            console.print()
            console.print(
                "[bold]Actions:[/bold] (s)end now  (k)eep queued  (x) drop without sending  (q)uit"
            )
            action = ask("Action", choices=["s", "k", "x", "q"], default="k")
        else:
            action = "s"

        if action == "q":
            console.print("[dim]Stopping — everything not yet sent stays queued.[/dim]")
            break

        if action == "k":
            console.print("[dim]Kept in queue.[/dim]\n")
            continue

        if action == "x":
            if dry_run:
                console.print("[yellow]DRY RUN — would drop from queue.[/yellow]\n")
                continue
            queue = [e for e in queue if e is not entry]
            _save_queue(queue)
            console.print("[dim]Dropped from queue without sending.[/dim]\n")
            continue

        if dry_run:
            console.print(f"[yellow]DRY RUN — would send to {entry['to']}.[/yellow]\n")
            sent_count += 1
            continue

        # Gmail is the final word on what already went out: a send that timed out, or
        # one that succeeded but couldn't be logged, shows up here and is never repeated.
        try:
            earlier = _sent_to_before(service, entry["to"])
        except Exception as e:
            console.print(f"  [red]Couldn't check Gmail Sent for {escape(entry['to'])} ({escape(str(e))}) - not sent, left in queue.[/red]\n")
            continue
        if earlier:
            queue = [e for e in queue if e is not entry]
            _save_queue(queue)
            console.print(f"  [yellow]Gmail Sent already has an email to {escape(entry['to'])} - not sending again, removed from queue.[/yellow]\n")
            continue

        try:
            sent = _send_entry(service, entry)
        except Exception as e:
            console.print(
                f"  [red]Failed sending to {escape(entry.get('to', '?'))}: {escape(str(e))} — left in queue.[/red]\n"
            )
            continue

        # Log first, then drop from the queue, saving each right away. If saving fails
        # after Gmail accepted the email, stop the run: the Sent check above keeps the
        # next run from sending it again.
        try:
            log.append(sent_log.new_record(entry, sent["threadId"], sent["id"], datetime.now(tz=_utc.utc)))
            sent_log.save(log)
            queue = [e for e in queue if e is not entry]
            _save_queue(queue)
        except Exception as e:
            console.print(
                f"[bold red]Sent to {escape(entry['to'])}, but couldn't save the log/queue ({escape(str(e))}). "
                "Stopping here. Close anything holding data/ files open and run --send-now again; "
                "it will skip this person automatically.[/bold red]"
            )
            raise
        sent_count += 1
        console.print(f"  [green]✓ Sent to {label}[/green]\n")
        if not review:
            # Space out the bulk run the same way --followups does.
            sleep(SEND_SPACING_SECONDS)

    return sent_count


def _sent_to_before(service, to: str) -> bool:
    """True if Gmail's Sent folder already has any email to this address."""
    res = service.users().messages().list(
        userId="me", q=f"in:sent to:{to.strip()}", includeSpamTrash=True, maxResults=1
    ).execute(num_retries=3)
    return bool(res.get("messages"))


def _send_entry(service, entry: dict) -> dict:
    """Send one outreach email; returns Gmail's {id, threadId, ...} for the sent message."""
    from gmail_auth import get_signature_html

    msg = MIMEMultipart("mixed")
    msg["to"] = entry["to"]
    msg["from"] = MY_BACKGROUND["email"]
    msg["subject"] = entry["subject"]
    attach_bodies(msg, ensure_signoff(entry["body"]), get_signature_html(service), with_resume=True)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()


def _load_queue() -> list:
    if QUEUE_FILE.exists():
        return json.loads(QUEUE_FILE.read_text())
    return []


def _save_queue(queue: list):
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(queue, indent=2))
