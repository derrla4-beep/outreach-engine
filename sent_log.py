"""Record of every outreach email sent: its Gmail thread, follow-ups, and reply status.

data/sent_log.json is a list with one record per original email:
  {to, name, first_name, subject, thread_id, original_msg_id, sent_at, batch, source,
   followups: [{n, msg_id, sent_at}], reply, auto_reply_at, bounced_at}

Follow-ups only ever go to threads recorded here, so nothing is guessed from
keywords. `reply` is {at, after, how} once a reply is detected, where `after` is the
last email of ours before it ("original", "followup1" or "followup2").
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

SENT_LOG_FILE = Path(__file__).parent / "data" / "sent_log.json"
BACKUPS_TO_KEEP = 5

_GREETING_RE = re.compile(r"^\s*(?:Good (?:Morning|Afternoon|Evening)|Hi|Hello|Hey|Dear)\s+([^,\n]+),", re.I)


def load() -> list[dict]:
    if not SENT_LOG_FILE.exists():
        return []
    return json.loads(SENT_LOG_FILE.read_text(encoding="utf-8"))


def save(records: list[dict]):
    """Write via a temp file and rename, so an interrupted run can't leave a half-written log."""
    SENT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SENT_LOG_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(records, indent=2), encoding="utf-8")
    os.replace(tmp, SENT_LOG_FILE)


def backup(tag: str) -> Path | None:
    """Copy the log to data/sent_log.pre-<tag>-<timestamp>.bak.json, keeping the newest few."""
    if not SENT_LOG_FILE.exists():
        return None
    dest = SENT_LOG_FILE.with_name(f"sent_log.pre-{tag}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak.json")
    dest.write_text(SENT_LOG_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    prune_backups(SENT_LOG_FILE.parent, "sent_log.pre-*.bak.json")
    return dest


def prune_backups(folder: Path, pattern: str, keep: int = BACKUPS_TO_KEEP):
    olds = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]
    for p in olds:
        p.unlink()


def first_name_for(body: str, name: str) -> str:
    """The name you actually greeted them by ("Good Morning Chris," -> "Chris"),
    falling back to the first word of their full name."""
    m = _GREETING_RE.match(body or "")
    if m and m.group(1).strip():
        return m.group(1).strip()
    return (name or "").split()[0] if (name or "").strip() else ""


def batch_of(sent_at: datetime) -> str:
    """The Monday (local date) of the week an email went out: one batch per week."""
    d = sent_at.astimezone().date()
    return (d - timedelta(days=d.weekday())).isoformat()


def new_record(entry: dict, thread_id: str, msg_id: str, sent_at: datetime, source: str = "send") -> dict:
    """A log record for an original outreach email. sent_at must be timezone-aware."""
    return {
        "to": entry["to"].strip().lower(),
        "name": entry.get("name", ""),
        "first_name": first_name_for(entry.get("body", ""), entry.get("name", "")),
        "subject": entry["subject"],
        "thread_id": thread_id,
        "original_msg_id": msg_id,
        "sent_at": sent_at.isoformat(),
        "batch": batch_of(sent_at),
        "source": source,
        "followups": [],
        "reply": None,
        "auto_reply_at": None,
        "bounced_at": None,
    }


def already_sent(records: list[dict], to: str, subject: str) -> bool:
    to = to.strip().lower()
    return any(r["to"] == to and r["subject"] == subject for r in records)
