#!/usr/bin/env python3
"""
Banking Outreach
----------------
Claude Code writes each email and queues it with add_emails.py. Then, each week:

  Monday:    python main.py --send-now              show the queue, type "send", sends it all
  Tuesday:   python main.py --followups             follow-up #1 to anyone who hasn't replied
  Thursday:  python main.py --followups             follow-up #2 to anyone who still hasn't

  python main.py --stats                     reply rates, overall and per batch
  python main.py --mark-replied EMAIL        they replied outside Gmail; never follow up

Add --dry-run to --send-now or --followups to preview without sending, and
--limit N to cap how many go out. --send-now --review goes one email at a time.
"""

import argparse
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from rich.console import Console

console = Console(legacy_windows=False)


def _non_negative(value: str) -> int:
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("--limit can't be negative")
    return n


def parse_args():
    parser = argparse.ArgumentParser(description="Banking outreach: send, follow up, track replies.",
                                     allow_abbrev=False)  # removed flags like --followup must not match --followups
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--send-now", action="store_true", help="Review and send the queued emails")
    action.add_argument("--followups", action="store_true",
                        help="Send follow-up #1/#2 to everyone due who hasn't replied")
    action.add_argument("--stats", action="store_true", help="Check for replies and show response rates")
    action.add_argument("--mark-replied", metavar="EMAIL",
                        help="Record a reply that came outside Gmail; they never get a follow-up")
    parser.add_argument("--limit", type=_non_negative, default=None, help="Cap how many emails go out")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending anything")
    parser.add_argument("--review", action="store_true",
                        help="With --send-now: go one email at a time instead of sending the whole batch")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.send_now:
        from schedule_sender import send_queue_interactive
        count = send_queue_interactive(console, limit=args.limit, dry_run=args.dry_run,
                                       review=args.review)
        if args.dry_run:
            console.print(f"[bold yellow]Dry run complete - {count} email(s) would have been sent.[/bold yellow]")
        elif count:
            console.print(f"[bold green]Sent {count} email(s).[/bold green]")
        else:
            console.print("[dim]Nothing sent.[/dim]")
        return

    if args.followups:
        import sent_log
        from followups import run_followups
        from stats import print_report
        run_followups(console, limit=args.limit, dry_run=args.dry_run)
        console.print()
        print_report(sent_log.load(), console)
        return

    if args.stats:
        from stats import run_stats
        run_stats(console)
        return

    if args.mark_replied:
        from followups import mark_replied
        mark_replied(args.mark_replied, console)
        return

    console.print(__doc__)


if __name__ == "__main__":
    main()
