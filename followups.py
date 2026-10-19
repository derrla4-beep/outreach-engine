"""Automatic follow-ups: `python main.py --followups`.

Weekly rhythm: originals go out Monday (--send-now), follow-up #1 on Tuesday, #2 on
Thursday. Only threads recorded in data/sent_log.json are ever followed up.

The rule that matters most: anyone who has replied never gets another email. So
every contact is checked against Gmail twice, once for the preview table and again
right before its own send, and any doubt or error means NOT sending:

  1. Thread: any message in it not from you (reply, auto-reply, bounce), or any
     message from you that isn't a logged email (you already wrote back).
  2. Mailbox, by address: anything from them since the original, in any thread,
     including spam and trash.
  3. Mailbox, sent: anything you sent them outside this sequence.
  4. Bounces mentioning the address.
  5. Same full name from a different address: HOLD for you to decide.
  6. Someone at the same company domain mentioning their name: HOLD.
  7. Auto-replies (out of office): HOLD, not counted as a reply.
  8. data/do_not_followup.txt (replies by phone, LinkedIn, text).
"""

import base64
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.utils import parseaddr
from pathlib import Path

import sent_log
from config import MY_BACKGROUND
from text_utils import attach_bodies

# Fixed follow-up text; only the first name changes (edit the wording to taste). No Gmail signature
# and no sign-off rewrite: the name at the bottom is part of the template.
TEMPLATES = {
    1: (
        "Hi {first_name},\n\n"
        "Hope all is well, I understand things are probably busy. Just wanted to push this "
        "to the top of your inbox in case you are up for a 5-10 minute chat.\n\n"
        "Thanks\n"
        + MY_BACKGROUND["name"]
    ),
    2: (
        "Hi {first_name},\n\n"
        "Hope you're doing well! Just wanted to circle back one more time — totally "
        "understand if things have been hectic. Still hoping to grab 5-10 minutes if your "
        "schedule opens up at any point.\n\n"
        "Thanks,\n"
        + MY_BACKGROUND["name"]
    ),
}

# Monday original -> Tuesday #1 -> Thursday #2. Days are local calendar days; the
# hour minimums stop a late-night original from getting a nudge first thing next morning.
FOLLOWUP1_AFTER_DAYS = 1      # calendar days after the original
FOLLOWUP1_MIN_HOURS = 12
FOLLOWUP2_AFTER_DAYS = 2      # calendar days after #1
FOLLOWUP2_MIN_HOURS = 24
FOLLOWUP1_MAX_AGE_DAYS = 7    # too stale for #1 after this (days since original)
FOLLOWUP2_MAX_AGE_DAYS = 10   # too stale for #2 after this (days since original)
SEND_SPACING_SECONDS = 2

STOP_LIST_FILE = Path(__file__).parent / "data" / "do_not_followup.txt"
MY_EMAIL = MY_BACKGROUND["email"].lower()

# Personal mail providers: a message from someone else at gmail.com says nothing
# about the contact, so the same-company check only runs on company domains.
PUBLIC_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com",
    "msn.com", "icloud.com", "me.com", "mac.com", "aol.com", "protonmail.com", "proton.me",
    # Add your school's domain here (e.g. "yourschool.edu") so classmates writing in
    # don't trip the same-company check. Your own domain is added automatically below.
}
PUBLIC_DOMAINS.add(MY_EMAIL.rsplit("@", 1)[-1])

_THREAD_HEADERS = ["From", "To", "Subject", "Message-ID", "Auto-Submitted",
                   "X-Autoreply", "X-Autorespond", "Precedence"]
_BOUNCE_SENDERS = ("mailer-daemon", "postmaster")
# Subject patterns are anchored at the start: a real reply's subject is "Re: <our
# subject>", so words anywhere in your own subject ("vacation rental coverage")
# must never turn a genuine reply into an auto-reply or a bounce.
_BOUNCE_SUBJECT_RE = re.compile(r"^\s*(delivery status notification|undeliverable|mail delivery (failed|subsystem)|returned mail)", re.I)
_AUTO_SUBJECT_RE = re.compile(r"^\s*(automatic reply|auto[- ]?reply|autoreply|auto[- ]?response|out of (the )?office|ooo\b|away from (the )?office)", re.I)
# Temporary delivery notices ("Delivery Status Notification (Delay)") are not bounces.
_DELAY_RE = re.compile(r"\bdela(y|yed)\b", re.I)
_EMAIL_IN_TEXT_RE = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
# Name tokens that aren't a surname: suffixes, credentials, single initials ("N.").
_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "cfa", "cpa", "mba", "phd", "md", "esq", "caia", "frm"}

# Check outcomes, most decisive first. Only OK (and a HOLD you release) may send.
REPLIED, SKIP, BOUNCED, ERROR, HOLD, OK = "replied", "skip", "bounced", "error", "hold", "ok"


@dataclass
class Check:
    status: str = OK
    reasons: list = field(default_factory=list)
    reply_at: datetime | None = None
    reply_how: str | None = None
    auto_reply_at: datetime | None = None
    bounced_at: datetime | None = None
    last_rfc_id: str | None = None  # Message-ID of our latest email in the thread, for In-Reply-To

    def flag(self, status: str, reason: str):
        order = [REPLIED, SKIP, BOUNCED, ERROR, HOLD, OK]
        if order.index(status) < order.index(self.status):
            self.status = status
        self.reasons.append(reason)


# ---------------------------------------------------------------------------
# Which follow-up is due
# ---------------------------------------------------------------------------

def _local_date(iso: str):
    return datetime.fromisoformat(iso).astimezone().date()


def due_followup(rec: dict, today, now: datetime | None = None) -> int | None:
    """1 or 2 if that follow-up is due for this record today (local date), else None.
    Never on a weekend. `now` (timezone-aware) enables the minimum-hours checks."""
    if rec.get("source") != "send" or rec.get("reply") or rec.get("bounced_at"):
        return None
    if today.weekday() >= 5:
        return None

    def hours_since(iso):
        return (now - datetime.fromisoformat(iso)).total_seconds() / 3600 if now else float("inf")

    done = len(rec.get("followups", []))
    days_since_original = (today - _local_date(rec["sent_at"])).days
    if done == 0:
        if (FOLLOWUP1_AFTER_DAYS <= days_since_original <= FOLLOWUP1_MAX_AGE_DAYS
                and hours_since(rec["sent_at"]) >= FOLLOWUP1_MIN_HOURS):
            return 1
    elif done == 1:
        first = rec["followups"][0]["sent_at"]
        if ((today - _local_date(first)).days >= FOLLOWUP2_AFTER_DAYS
                and days_since_original <= FOLLOWUP2_MAX_AGE_DAYS
                and hours_since(first) >= FOLLOWUP2_MIN_HOURS):
            return 2
    return None


def stage_before(rec: dict, at: datetime) -> str:
    """Which of our emails was the latest one sent before `at`."""
    stage = "original"
    for f in rec.get("followups", []):
        if datetime.fromisoformat(f["sent_at"]) <= at:
            stage = f"followup{f['n']}"
    return stage


# ---------------------------------------------------------------------------
# Gmail reply checks
# ---------------------------------------------------------------------------

def _headers(msg: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def _sender(msg: dict) -> str:
    """The From address. parseaddr gives up on headers like 'Smith, Chris <x@bank.com>'
    (unquoted comma), so fall back to the first address-shaped text in the header."""
    raw = _headers(msg).get("from", "")
    addr = parseaddr(raw)[1]
    if "@" not in addr:
        m = _EMAIL_IN_TEXT_RE.search(raw)
        addr = m.group(0) if m else ""
    return addr.lower()


def name_parts(name: str) -> tuple[str, str]:
    """(full name for a from:"..." search, surname for a mention search), either may be ''.
    Drops suffixes, credentials and bare initials so 'Michael N.' or 'Chris Smith, CFA'
    don't search for 'N.' or 'CFA'."""
    tokens = [t.strip(",.") for t in name.replace('"', "").split()]
    words = [t for t in tokens if len(t) > 1 and t.lower() not in _NAME_SUFFIXES]
    full = " ".join(words) if len(words) >= 2 else ""
    surname = words[-1] if len(words) >= 2 else ""
    return full, surname


def _when(msg: dict) -> datetime:
    return datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc)


def classify_inbound(msg: dict) -> str:
    """'bounce', 'auto' (out of office etc.) or 'reply' for a message not from you."""
    h = _headers(msg)
    sender = _sender(msg)
    subject = h.get("subject", "")
    if sender.split("@")[0] in _BOUNCE_SENDERS or _BOUNCE_SUBJECT_RE.search(subject):
        # A delay notice means the email is still being retried: HOLD, not a bounce.
        return "auto" if _DELAY_RE.search(subject) else "bounce"
    if (h.get("auto-submitted", "no").lower() != "no" or "x-autoreply" in h or "x-autorespond" in h
            or h.get("precedence", "").lower() == "auto_reply" or _AUTO_SUBJECT_RE.search(subject)):
        return "auto"
    return "reply"


def _search(service, query: str) -> list[str]:
    res = service.users().messages().list(
        userId="me", q=query, includeSpamTrash=True, maxResults=50
    ).execute(num_retries=3)
    return [m["id"] for m in res.get("messages", [])]


def _get_meta(service, msg_id: str) -> dict:
    return service.users().messages().get(
        userId="me", id=msg_id, format="metadata", metadataHeaders=_THREAD_HEADERS
    ).execute(num_retries=3)


def _note_inbound(check: Check, msg: dict, how: str):
    kind = classify_inbound(msg)
    when = _when(msg)
    who = _sender(msg) or "unknown sender"
    if kind == "reply":
        if check.reply_at is None or when < check.reply_at:
            check.reply_at, check.reply_how = when, how
        check.flag(REPLIED, f"Reply from {who} ({how})")
    elif kind == "bounce":
        check.bounced_at = check.bounced_at or when
        check.flag(BOUNCED, f"Bounce from {who}")
    else:
        check.auto_reply_at = check.auto_reply_at or when
        check.flag(HOLD, f"Auto-reply or delay notice from {who} (out of office?)")


def check_contact(service, rec: dict, stop_list: set, thorough: bool = True) -> Check:
    """Every reply check for one sent_log record. Never raises: any failure is ERROR.

    thorough=False (used by --stats) skips the HOLD-only searches (same name, same
    company, separate sends), which only matter when deciding whether to send.
    """
    check = Check()
    try:
        _run_checks(service, rec, stop_list, thorough, check)
    except Exception as e:  # fail closed: an unanswerable check is a reason not to send
        check.flag(ERROR, f"Gmail check failed: {type(e).__name__}: {e}")
    return check


def _run_checks(service, rec, stop_list, thorough, check):
    to = rec["to"].lower()
    if to in stop_list:
        check.flag(SKIP, "On data/do_not_followup.txt")
    if rec.get("reply"):
        check.flag(REPLIED, f"Reply already recorded ({rec['reply'].get('how', '?')})")
    if not rec.get("first_name"):
        check.flag(ERROR, "No first name recorded")

    # 1. The thread itself.
    ours = {rec["original_msg_id"]} | {f["msg_id"] for f in rec.get("followups", [])}
    thread = service.users().threads().get(
        userId="me", id=rec["thread_id"], format="metadata", metadataHeaders=_THREAD_HEADERS
    ).execute(num_retries=3)
    msgs = sorted(thread.get("messages", []), key=lambda m: int(m["internalDate"]))
    seen = set()
    found_original = False
    for m in msgs:
        seen.add(m["id"])
        if _sender(m) == MY_EMAIL:
            if m["id"] in ours:
                found_original |= m["id"] == rec["original_msg_id"]
                check.last_rfc_id = _headers(m).get("message-id") or check.last_rfc_id
            elif "DRAFT" in m.get("labelIds", []):
                check.flag(SKIP, "You have an unsent draft in this thread")
            else:
                check.flag(SKIP, "You already wrote in this thread yourself")
        else:
            _note_inbound(check, m, "thread")
    if not found_original:
        check.flag(ERROR, "Original email not found in its thread")
    if not check.last_rfc_id:
        check.flag(ERROR, "Couldn't read the Message-ID to reply to")

    sent_at = datetime.fromisoformat(rec["sent_at"])
    # Gmail's after: is coarse, so search from a day early and drop anything that
    # arrived before the original went out (earlier mail isn't a reply to it).
    after = int(sent_at.timestamp()) - 86400

    def new_since_original(query):
        for mid in _search(service, query):
            if mid not in seen:
                seen.add(mid)
                meta = _get_meta(service, mid)
                if _when(meta) >= sent_at:
                    yield meta

    # 2. Anything from their address, in any thread.
    for meta in new_since_original(f"from:{to} after:{after}"):
        _note_inbound(check, meta, "mailbox")

    # 4. Bounce or delay notices that mention the address.
    for meta in new_since_original(f'from:(mailer-daemon OR postmaster) after:{after} "{to}"'):
        _note_inbound(check, meta, "mailbox")

    if not thorough:
        return

    # 3. Anything you sent them outside this sequence.
    for mid in _search(service, f"in:sent to:{to} after:{after}"):
        if mid not in ours:
            check.flag(SKIP, "You emailed them separately since the original")
            break

    full_name, surname = name_parts(rec.get("name") or "")

    # 5. Same full name from another address (personal email, new job).
    if full_name:
        for mid in _search(service, f'from:"{full_name}" after:{after}'):
            other = _sender(_get_meta(service, mid))
            if other != to and other != MY_EMAIL:
                check.flag(HOLD, f"Message from {other or 'an unreadable sender'}, same name as the contact")
                break

    # 6. A colleague at the same company mentioning them (assistant, forward).
    domain = to.split("@")[-1]
    term = surname or rec.get("first_name") or ""
    if domain not in PUBLIC_DOMAINS and len(term) > 1:
        for mid in _search(service, f'from:{domain} after:{after} "{term}"'):
            other = _sender(_get_meta(service, mid))
            same_company = other.endswith("@" + domain) or other.endswith("." + domain)
            if same_company and other != to and other != MY_EMAIL:
                check.flag(HOLD, f"{other} (same company) emailed you mentioning \"{term}\"")
                break


def apply_detection(rec: dict, check: Check):
    """Store what a check found on the record, for --stats. Never clears anything."""
    if check.reply_at and not rec.get("reply"):
        rec["reply"] = {
            "at": check.reply_at.isoformat(),
            "after": stage_before(rec, check.reply_at),
            "how": check.reply_how,
        }
    if check.auto_reply_at and not rec.get("auto_reply_at"):
        rec["auto_reply_at"] = check.auto_reply_at.isoformat()
    if check.bounced_at and not rec.get("bounced_at"):
        rec["bounced_at"] = check.bounced_at.isoformat()


# ---------------------------------------------------------------------------
# Stop list and manual replies
# ---------------------------------------------------------------------------

def _read_text_any(path: Path) -> str:
    """Text from a file a person may have edited: UTF-8 with or without a BOM
    (PowerShell adds one), or UTF-16 (Notepad's "Unicode")."""
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    return data.decode("utf-8-sig", errors="replace")


def load_stop_list() -> set:
    """Every address on data/do_not_followup.txt. A line may be a bare address,
    'Name <address>', or have a trailing '# comment'; every address on it counts."""
    if not STOP_LIST_FILE.exists():
        return set()
    found = set()
    for line in _read_text_any(STOP_LIST_FILE).splitlines():
        found |= {a.lower() for a in _EMAIL_IN_TEXT_RE.findall(line.split("#", 1)[0])}
    return found


def mark_replied(address: str, console, log: list | None = None) -> bool:
    """--mark-replied: a reply that came outside Gmail (call, LinkedIn, text). Adds the
    address to the stop list and records the reply on `log` (loaded if not given).
    Returns False, changing nothing, if `address` doesn't contain an email address."""
    m = _EMAIL_IN_TEXT_RE.search(address or "")
    if not m:
        console.print(f"[red]{address!r} isn't an email address - nothing changed.[/red]")
        return False
    address = m.group(0).lower()
    if address not in load_stop_list():
        # Rewrite as plain UTF-8 rather than append, so a hand-edited file (no final
        # newline, BOM, UTF-16) can't glue this address onto the previous line.
        STOP_LIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        old = _read_text_any(STOP_LIST_FILE).splitlines() if STOP_LIST_FILE.exists() else []
        STOP_LIST_FILE.write_text("\n".join(old + [address]) + "\n", encoding="utf-8")
        if address not in load_stop_list():
            console.print(f"[red]Couldn't add {address} to {STOP_LIST_FILE.name} - check the file by hand.[/red]")
            return False
    log = sent_log.load() if log is None else log
    now = datetime.now(tz=timezone.utc)
    hits = [r for r in log if r["to"] == address]
    for r in hits:
        if not r.get("reply"):
            r["reply"] = {"at": now.isoformat(), "after": stage_before(r, now), "how": "manual"}
    if hits:
        sent_log.save(log)
    console.print(
        f"[green]{address} will never get a follow-up"
        + (f", and is counted as replied in --stats ({len(hits)} email(s)).[/green]" if hits
           else ". (Not in the sent log, so it doesn't change --stats.)[/green]")
    )
    return True


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def build_followup(rec: dict, n: int, last_rfc_id: str) -> dict:
    """The Gmail API body for follow-up #n, threaded under our latest email."""
    subject = rec["subject"]
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject
    msg = MIMEMultipart("mixed")
    msg["to"] = rec["to"]
    msg["from"] = MY_BACKGROUND["email"]
    msg["subject"] = subject
    msg["In-Reply-To"] = last_rfc_id
    msg["References"] = last_rfc_id
    attach_bodies(msg, TEMPLATES[n].format(first_name=rec["first_name"]), signature_html="")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw, "threadId": rec["thread_id"]}


def run_followups(console, limit=None, dry_run=False, service=None, today=None,
                  ask=None, sleep=time.sleep) -> int:
    """Check every due thread, show the plan, and send on confirmation. Returns sends.

    Replies and bounces found are saved to the sent log even on a dry run (that's
    only Gmail facts, nothing is sent), so --stats and the next run see them.
    """
    from rich.markup import escape
    from rich.table import Table

    if ask is None:
        from rich.prompt import Prompt
        ask = Prompt.ask
    now = datetime.now(tz=timezone.utc)
    today = today or now.astimezone().date()

    log = sent_log.load()
    due = [(r, n) for r in log if (n := due_followup(r, today, now))]
    if not due:
        why = " (follow-ups never go out on weekends)" if today.weekday() >= 5 else ""
        console.print(f"[green]No follow-ups are due today{why}.[/green]")
        return 0

    if service is None:
        from gmail_auth import gmail_service
        service = gmail_service()

    b = sent_log.backup("followups")
    console.print(f"[dim]Sent log backed up to {b.name}[/dim]")

    stop_list = load_stop_list()
    console.print(f"[bold]Checking Gmail for replies from {len(due)} contact(s)...[/bold]")
    results = []
    for i, (rec, n) in enumerate(due, 1):
        check = check_contact(service, rec, stop_list)
        apply_detection(rec, check)
        results.append((rec, n, check))
        if i % 25 == 0:
            console.print(f"[dim]  {i}/{len(due)} checked[/dim]")
    sent_log.save(log)  # keep detected replies/bounces for --stats

    groups = {}
    for rec, n, check in results:
        key = f"Will send #{n}" if check.status == OK else check.status
        groups.setdefault(key, []).append((rec, n, check))
    labels = {"Will send #1": "green", "Will send #2": "green", REPLIED: "cyan", SKIP: "cyan",
              BOUNCED: "magenta", HOLD: "yellow", ERROR: "red"}
    table = Table(title=f"Follow-ups for {today:%A %b %d}")
    table.add_column("Group")
    table.add_column("Contact", style="bold")
    table.add_column("Email")
    table.add_column("Why")
    for key in labels:
        for rec, n, check in groups.get(key, []):
            why = "; ".join(check.reasons) if check.reasons else f"No reply since {'the original' if n == 1 else '#1'}"
            table.add_row(f"[{labels[key]}]{key}[/{labels[key]}]", escape(rec.get("name") or rec["to"]), escape(rec["to"]), escape(why))
    console.print(table)
    console.print(" | ".join(f"{k}: {len(v)}" for k, v in groups.items()))

    if dry_run:
        console.print("[yellow]DRY RUN - nothing sent.[/yellow]")
        return 0

    to_send = [(rec, n, None) for rec, n, _ in groups.get("Will send #1", []) + groups.get("Will send #2", [])]
    if limit is not None and len(to_send) > limit:
        console.print(f"[dim]--limit {limit}: {len(to_send) - limit} ready follow-up(s) wait for the next run.[/dim]")
        to_send = to_send[:limit]
    for rec, n, check in groups.get(HOLD, []):
        console.print(f"\n[yellow]HOLD[/yellow] {escape(rec.get('name') or '')} <{escape(rec['to'])}>: " + escape("; ".join(check.reasons)))
        choice = ask("  (r)elease and send, (m)ark as replied, (k)eep held", choices=["r", "m", "k"], default="k")
        if choice == "r":
            to_send.append((rec, n, set(check.reasons)))
        elif choice == "m":
            mark_replied(rec["to"], console, log)
    if not to_send:
        console.print("[dim]Nothing to send.[/dim]")
        return 0

    answer = ask(f"\nType 'send' to send {len(to_send)} follow-up(s), anything else to cancel", default="")
    if answer.strip().lower() != "send":
        console.print("[dim]Cancelled - nothing sent.[/dim]")
        return 0

    stop_list = load_stop_list()
    sent = 0
    for rec, n, released in to_send:
        label = escape(rec.get("name") or rec["to"])
        # Re-check right before sending: a reply can land after the preview.
        check = check_contact(service, rec, stop_list)
        apply_detection(rec, check)
        allowed = check.status == OK or (
            check.status == HOLD and released is not None and set(check.reasons) <= released
        )
        if not allowed or due_followup(rec, today, datetime.now(tz=timezone.utc)) != n:
            sent_log.save(log)
            console.print(f"  [cyan]Not sent to {label}: {escape('; '.join(check.reasons)) or 'no longer due'}[/cyan]")
            continue
        try:
            res = service.users().messages().send(
                userId="me", body=build_followup(rec, n, check.last_rfc_id)
            ).execute()
        except Exception as e:
            # Not retried. If Gmail did send it anyway, the next run sees an unlogged
            # message of ours in the thread and skips the contact.
            console.print(f"  [red]Failed sending #{n} to {label}: {e}[/red]")
            continue
        rec["followups"].append({"n": n, "msg_id": res["id"], "sent_at": datetime.now(tz=timezone.utc).isoformat()})
        sent_log.save(log)
        sent += 1
        console.print(f"  [green]✓ #{n} sent to {label}[/green]")
        sleep(SEND_SPACING_SECONDS)
    console.print(f"\n[bold green]Sent {sent} follow-up(s).[/bold green]")
    return sent
