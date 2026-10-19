#!/usr/bin/env python3
"""
Put emails that Claude Code already wrote into the send queue.

This is the current workflow:
  1. You give Claude Code each contact: name, LinkedIn URL, email address, notes.
  2. Claude Code writes the email and saves the batch as a JSON file.
  3. Claude Code runs:  python add_emails.py <batch.json>
  4. You run:           python main.py --send-now

The writing rules are in email_rules.md; the mechanical ones are checked here
(email_checks.py). Each batch entry looks like:
  {"name": "...", "to": "...", "linkedin_url": "...", "location": "New York",
   "subject": "...", "body": "Good Morning X,\\n\\n...line 4"}

The body is greeting through Line 4 only; the sign-off and resume P.S. are appended here.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from email_checks import load_processed_urls, mark_url_processed, validate_email_body
from followups import load_stop_list
from schedule_sender import _EMAIL_RE, QUEUE_FILE, _load_queue, infer_timezone, queue_email
import sent_log
from text_utils import clean_email_text, ensure_signoff

SUBJECT_MAX_CHARS = 40


def _norm_url(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def main():
    parser = argparse.ArgumentParser(description="Queue emails written by Claude Code")
    parser.add_argument("batch", help="JSON file with a list of emails")
    parser.add_argument("--dry-run", action="store_true", help="Check and print, queue nothing")
    args = parser.parse_args()

    batch = json.loads(Path(args.batch).read_text(encoding="utf-8"))
    queue = _load_queue()
    queued_to = {e["to"].strip().lower() for e in queue}
    queued_urls = {_norm_url(e.get("linkedin_url")) for e in queue} - {""}
    emailed_on = {r["to"]: r["batch"] for r in sent_log.load()}
    processed_urls = {_norm_url(u) for u in load_processed_urls()} - {""}
    stop_list = load_stop_list()

    ready, problems = [], []
    for item in batch:
        label = item.get("name") or item.get("to", "?")
        subject = clean_email_text(item["subject"]).strip()
        body = ensure_signoff(clean_email_text(item["body"]))
        issues = validate_email_body(body)
        if len(subject) > SUBJECT_MAX_CHARS:
            issues.append(f"Subject is {len(subject)} chars (cap {SUBJECT_MAX_CHARS}).")
        if not _EMAIL_RE.match(item["to"].strip()):
            issues.append(f"{item['to']!r} is not a valid email address.")
        if item["to"].strip().lower() in queued_to:
            issues.append(f"{item['to']} is already in the queue (or earlier in this batch).")
        if item["to"].strip().lower() in emailed_on:
            issues.append(f"{item['to']} was already emailed (batch of {emailed_on[item['to'].strip().lower()]}).")
        if item["to"].strip().lower() in stop_list:
            issues.append(f"{item['to']} is on data/do_not_followup.txt (already replied).")
        if _norm_url(item.get("linkedin_url")) in queued_urls:
            issues.append("LinkedIn URL is already in the queue.")
        elif _norm_url(item.get("linkedin_url")) in processed_urls:
            issues.append("LinkedIn URL was already queued before (data/processed_urls.txt). "
                          "If they were never actually emailed, delete that line and re-run.")
        if issues:
            problems.append((label, issues))
        else:
            ready.append({**item, "subject": subject, "body": body})
            queued_to.add(item["to"].strip().lower())
            queued_urls.add(_norm_url(item.get("linkedin_url")))
            queued_urls.discard("")

    # Gmail's Sent folder is the final word on who was already emailed: the sent log
    # only covers what this tool sent or could backfill. Any doubt means skip.
    if ready:
        print(f"Checking Gmail Sent for {len(ready)} address(es)...")
        try:
            from gmail_auth import gmail_service
            from schedule_sender import _sent_to_before
            service = gmail_service()
        except Exception as e:
            service, gmail_error = None, e
        still_ready = []
        for item in ready:
            label = item.get("name") or item["to"]
            try:
                if service is None:
                    raise gmail_error
                if _sent_to_before(service, item["to"]):
                    problems.append((label, [f"{item['to']} is already in Gmail Sent (emailed before)."]))
                    continue
            except Exception as e:
                problems.append((label, [f"Couldn't check Gmail Sent ({e}); not queued."]))
                continue
            still_ready.append(item)
        ready = still_ready

    for label, issues in problems:
        print(f"SKIPPED {label}:")
        for issue in issues:
            print(f"  - {issue}")

    if args.dry_run:
        for item in ready:
            print("=" * 72)
            print(f"{item['name']} <{item['to']}>  |  {item['subject']}")
            print("-" * 72)
            print(item["body"])
        print(f"\nDRY RUN: {len(ready)} ready, {len(problems)} skipped. Nothing queued.")
        return

    if not ready:
        print("Nothing queued.")
        return

    backup = QUEUE_FILE.with_name(
        f"scheduled_queue.pre-add-{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak.json"
    )
    backup.write_text(json.dumps(queue, indent=2))
    sent_log.prune_backups(QUEUE_FILE.parent, "scheduled_queue.pre-add-*.bak.json")
    print(f"Queue backed up to {backup.name}")

    processed = load_processed_urls()

    for item in ready:
        # Location only, never the notes: a note like "previously at UBS Germany"
        # would otherwise schedule a New York banker on Berlin time.
        tz = str(infer_timezone(location=item.get("location", "")))
        queue_email(
            to=item["to"].strip(),
            subject=item["subject"],
            body=item["body"],
            name=item["name"],
            linkedin_url=item.get("linkedin_url", ""),
            recipient_tz=tz,
        )
        url = item.get("linkedin_url", "")
        if url and url.strip() not in processed:
            mark_url_processed(url)
        print(f"Queued {item['name']} ({tz.split('/')[-1]})")

    print(f"\n{len(ready)} queued, {len(problems)} skipped. Send with: python main.py --send-now")


if __name__ == "__main__":
    main()
