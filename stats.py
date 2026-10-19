"""Response-rate tracking: `python main.py --stats`.

Read-only against Gmail. Re-checks recent threads in data/sent_log.json for replies
(same checks as --followups, minus the HOLD-only ones), records what it finds, then
reports reply rates overall, per Monday batch, and per email in the sequence.
"""

from datetime import datetime, timedelta, timezone
from statistics import median

import sent_log
from followups import apply_detection, check_contact, load_stop_list

RESCAN_DAYS = 30  # threads older than this with no reply are treated as final


def refresh(service, log: list, console=None) -> int:
    """Look for new replies on recent unreplied threads. Returns how many were found."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=RESCAN_DAYS)
    stop_list = load_stop_list()
    todo = [r for r in log if not r.get("reply") and not r.get("bounced_at")
            and datetime.fromisoformat(r["sent_at"]) >= cutoff]
    found = errors = 0
    for i, rec in enumerate(todo, 1):
        check = check_contact(service, rec, stop_list, thorough=False)
        errors += any(r.startswith("Gmail check failed") for r in check.reasons)
        apply_detection(rec, check)
        found += bool(rec.get("reply"))
        if console and i % 25 == 0:
            console.print(f"[dim]  {i}/{len(todo)} checked[/dim]")
    if console and errors:
        console.print(f"[yellow]{errors} thread(s) couldn't be checked (Gmail error); run --stats again later.[/yellow]")
    return found


def summarize(records: list) -> dict:
    """Counts and rates for a set of sent_log records."""
    contacted = [r for r in records if not r.get("bounced_at")]
    replied = [r for r in contacted if r.get("reply")]
    got1 = [r for r in contacted if len(r.get("followups", [])) >= 1]
    got2 = [r for r in contacted if len(r.get("followups", [])) >= 2]
    by_stage = {s: [r for r in replied if r["reply"].get("after") == s]
                for s in ("original", "followup1", "followup2")}

    hours = []
    for r in replied:
        stage = r["reply"].get("after")
        if r["reply"].get("how") == "manual":
            continue  # time of a manual mark is when you ran the command, not the reply
        sent = r["sent_at"] if stage == "original" else next(
            (f["sent_at"] for f in r["followups"] if f"followup{f['n']}" == stage), r["sent_at"])
        delta = datetime.fromisoformat(r["reply"]["at"]) - datetime.fromisoformat(sent)
        hours.append(max(delta.total_seconds() / 3600, 0))

    def pct(a, b):
        return f"{100 * a / b:.0f}%" if b else "-"

    def frac(a, b):
        return f"{a}/{b} {pct(a, b)}" if b else "-"

    return {
        "contacted": len(contacted),
        "replied": len(replied),
        "reply_rate": pct(len(replied), len(contacted)),
        "to_original": frac(len(by_stage["original"]), len(contacted)),
        "after_fu1": frac(len(by_stage["followup1"]), len(got1)),
        "after_fu2": frac(len(by_stage["followup2"]), len(got2)),
        "auto_replies": sum(1 for r in records if r.get("auto_reply_at")),
        "bounced": sum(1 for r in records if r.get("bounced_at")),
        "median_reply_hours": f"{median(hours):.0f}h" if hours else "-",
    }


def print_report(log: list, console):
    from rich import box
    from rich.table import Table

    if not log:
        console.print("[dim]No sent emails logged yet.[/dim]")
        return

    cols = [("Week of", "batch"), ("Sent", "contacted"), ("Replied", "replied"),
            ("Rate", "reply_rate"), ("To orig.", "to_original"), ("After #1", "after_fu1"),
            ("After #2", "after_fu2"), ("OOO", "auto_replies"), ("Bounced", "bounced"),
            ("Median", "median_reply_hours")]
    table = Table(title="Response rates", box=box.SIMPLE_HEAD, pad_edge=False)
    for title, _ in cols:
        table.add_column(title, justify="left" if title == "Week of" else "right", no_wrap=True)

    for b in sorted({r["batch"] for r in log}, reverse=True):
        recs = [r for r in log if r["batch"] == b]
        s = summarize(recs)
        tag = "*" if all(r.get("source") == "backfill" for r in recs) else ""
        table.add_row(b + tag, *[str(s[k]) for _, k in cols[1:]])
    s = summarize(log)
    table.add_section()
    table.add_row("[bold]All[/bold]", *[f"[bold]{s[k]}[/bold]" for _, k in cols[1:]])
    console.print(table)
    console.print(
        "[dim]To orig. = replied before #1 went out (of everyone sent). After #1 / After #2 = "
        "replied after that follow-up (of everyone who got it). Bounces aren't counted as sent; "
        "OOO auto-replies aren't counted as replies. Median = time from our email to their reply. "
        "* = backfilled from Gmail history.[/dim]"
    )


def run_stats(console, service=None):
    log = sent_log.load()
    if not log:
        console.print("[dim]No sent emails logged yet. Emails sent with --send-now are logged automatically.[/dim]")
        return
    if service is None:
        from gmail_auth import gmail_service
        service = gmail_service()
    console.print("[bold]Checking Gmail for new replies...[/bold]")
    found = refresh(service, log, console)
    sent_log.save(log)
    console.print(f"[dim]{found} new repl{'y' if found == 1 else 'ies'} found.[/dim]\n")
    print_report(log, console)
