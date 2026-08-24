#!/usr/bin/env python3
"""
Banking Outreach Email Automation
----------------------------------
Usage:
  python main.py --csv            # Load profiles from data/profiles.csv (recommended)
  python main.py --urls urls.txt  # Scrape profiles from LinkedIn URLs via Playwright
  python main.py --template       # Create blank CSV template and exit
  python main.py --auth           # Run Gmail OAuth flow and exit
  python main.py --no-gmail       # Skip Gmail tone sampling (use built-in defaults)
"""

import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import glob
import json
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich import print as rprint

console = Console(legacy_windows=False)


def parse_args():
    parser = argparse.ArgumentParser(description="Banking outreach email generator")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--csv", action="store_true", help="Load profiles from data/profiles.csv")
    source.add_argument("--urls", metavar="FILE", help="Scrape profiles from a file of LinkedIn URLs")
    source.add_argument("--template", action="store_true", help="Create CSV template and exit")
    source.add_argument("--auth", action="store_true", help="Run Gmail OAuth flow and exit")
    source.add_argument("--followup", action="store_true", help="Scan and send follow-up emails")
    source.add_argument("--send-queue", action="store_true", help="Send any scheduled emails that are now due")
    source.add_argument("--list-queue", action="store_true", help="Show all pending scheduled emails")
    source.add_argument("--check", metavar="FILE", nargs="?", const="urls.txt",
                         help="Lint notes in a URL file for unverified/hedge language without scraping or generating (default: urls.txt)")

    parser.add_argument("--no-gmail", action="store_true", help="Skip Gmail tone sampling")
    parser.add_argument("--send", action="store_true", help="Prompt to send (not just draft) each email")
    parser.add_argument("--output", default="data/drafts", help="Directory to save draft files")
    return parser.parse_args()


def run_auth():
    from gmail_auth import get_gmail_credentials
    console.print("[bold]Running Gmail OAuth flow...[/bold]")
    get_gmail_credentials()
    console.print("[green]✓ Authentication complete. token.json saved.[/green]")


def create_template():
    from linkedin_scraper import create_csv_template
    create_csv_template()


def load_profiles(args):
    if args.urls:
        from linkedin_scraper import load_profiles_from_urls
        console.print(f"[bold]Scraping LinkedIn profiles from {args.urls}...[/bold]")
        return load_profiles_from_urls(args.urls)
    else:
        from linkedin_scraper import load_profiles_from_csv
        console.print("[bold]Loading profiles from data/profiles.csv...[/bold]")
        return load_profiles_from_csv()


UNVERIFIED_NOTE_PHRASES = [
    "confirm from linkedin",
    "confirm group from linkedin",
    "confirm org from linkedin",
    "confirm current firm",
    "pull from linkedin before generating",
    "before generating",
    "unconfirmed",
    "not confirmed",
    "tbd",
]


def check_unverified_notes(profiles) -> None:
    """Warn and require confirmation when a profile's note still contains
    hedge language (e.g. 'confirm before generating') instead of a
    verified fact, so unverified claims don't get written into an email."""
    for profile in profiles:
        note_lower = profile.notes.lower()
        hit = next((p for p in UNVERIFIED_NOTE_PHRASES if p in note_lower), None)
        if hit:
            console.print(
                f"[yellow]⚠ {profile.full_name or profile.url}: note contains "
                f"unverified/hedge language ('{hit}'). Review before generating:[/yellow]"
            )
            console.print(f"[dim]{profile.notes}[/dim]\n")
            if not Confirm.ask(f"Continue generating an email for {profile.full_name or profile.url} anyway?", default=False):
                console.print("[red]Aborting — fix the note in urls.txt/CSV and rerun.[/red]")
                sys.exit(1)


def check_notes_file(url_file: str) -> None:
    """Lint a URL file's notes for unverified/hedge language without scraping
    or calling Claude — lets you see which entries would generate cleanly
    and which would get stopped by check_unverified_notes()."""
    from linkedin_scraper import load_processed_urls

    path = Path(url_file)
    if not path.exists():
        console.print(f"[red]File not found: {url_file}[/red]")
        sys.exit(1)

    url_notes: list[tuple[str, str]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            url, note = line.split("|", 1)
            url_notes.append((url.strip(), note.strip()))
        else:
            url_notes.append((line, ""))

    processed = load_processed_urls()
    new_entries = [(u, n) for u, n in url_notes if u not in processed]
    skipped = len(url_notes) - len(new_entries)

    table = Table(title=f"{len(new_entries)} unprocessed entr{'y' if len(new_entries) == 1 else 'ies'} in {url_file}")
    table.add_column("URL", style="cyan", overflow="fold")
    table.add_column("Status")
    table.add_column("Reason", overflow="fold")

    clean_count = 0
    for url, note in new_entries:
        note_lower = note.lower()
        hit = next((p for p in UNVERIFIED_NOTE_PHRASES if p in note_lower), None)
        if hit:
            table.add_row(url, "[yellow]FLAGGED[/yellow]", f"contains '{hit}'")
        elif not note:
            table.add_row(url, "[yellow]FLAGGED[/yellow]", "no personalization note at all")
        else:
            table.add_row(url, "[green]CLEAN[/green]", "")
            clean_count += 1

    console.print(table)
    console.print(
        f"\n[green]{clean_count} clean[/green] · "
        f"[yellow]{len(new_entries) - clean_count} flagged[/yellow]"
        + (f" · {skipped} already processed (not shown)" if skipped else "")
    )


def fetch_email_samples(skip: bool) -> str:
    if skip:
        console.print("[yellow]--no-gmail set: skipping Gmail tone sampling.[/yellow]")
        return ""
    try:
        from email_analyzer import fetch_sent_networking_emails, format_samples_for_prompt
        console.print("[bold]Fetching sent networking emails from Gmail...[/bold]")
        samples = fetch_sent_networking_emails()
        console.print(f"  [green]✓ Found {len(samples)} email sample(s)[/green]")
        return format_samples_for_prompt(samples)
    except FileNotFoundError:
        console.print(
            "[yellow]credentials.json not found — run [bold]python main.py --auth[/bold] first.\n"
            "Continuing without Gmail tone sampling.[/yellow]"
        )
        return ""
    except Exception as e:
        console.print(f"[yellow]Gmail fetch failed ({e}). Continuing without tone samples.[/yellow]")
        return ""


def display_email(email, index: int, total: int):
    console.print(Panel(
        f"[bold]Subject:[/bold] {email.subject}\n\n{email.body}",
        title=f"[{index}/{total}] {email.profile.full_name} — {email.profile.company}",
        border_style="blue",
    ))


def save_draft_to_file(email, output_dir: str) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_name = email.profile.full_name.replace(" ", "_").lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out / f"{safe_name}_{timestamp}.txt"
    path.write_text(
        f"To: {email.profile.full_name} <{email.profile.company}>\n"
        f"LinkedIn: {email.profile.url}\n"
        f"Subject: {email.subject}\n"
        f"\n{email.body}"
    )
    return path


SPREADSHEET_PATH = next(
    iter(glob.glob(str(Path(__file__).parent / "*.xlsx"))), None
)

PRIVATE_CREDIT_KEYWORDS = {"credit", "lending", "debt", "clo", "fixed income", "distressed"}
PRIVATE_EQUITY_KEYWORDS = {"equity", "buyout", "venture", "vc", "growth equity", "pe "}


def _infer_type(title: str) -> str:
    t = title.lower()
    if any(k in t for k in PRIVATE_CREDIT_KEYWORDS):
        return "Private Credit"
    if any(k in t for k in PRIVATE_EQUITY_KEYWORDS):
        return "Private Equity"
    return "Banking"


def append_to_spreadsheet(email, how_contacted: str):
    if not SPREADSHEET_PATH:
        console.print("[yellow]No .xlsx file found — skipping spreadsheet update.[/yellow]")
        return
    try:
        import openpyxl
        wb = openpyxl.load_workbook(SPREADSHEET_PATH)
        ws = wb.active

        last_row = 1
        for i in range(ws.max_row, 0, -1):
            if any(ws.cell(i, j).value for j in range(1, ws.max_column + 1)):
                last_row = i
                break

        p = email.profile
        row = last_row + 1
        ws.cell(row, 1).value = p.full_name
        ws.cell(row, 2).value = _infer_type(p.title)
        ws.cell(row, 3).value = p.company
        ws.cell(row, 4).value = "No Response"
        ws.cell(row, 5).value = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ws.cell(row, 7).value = how_contacted

        wb.save(SPREADSHEET_PATH)
        console.print(f"  [green]✓ Added {p.full_name} to spreadsheet[/green]")
    except Exception as e:
        console.print(f"  [yellow]Spreadsheet update failed: {e}[/yellow]")


def handle_email_action(email, args):
    """After review, ask user what to do with the email."""
    choices = "[bold]Actions:[/bold] (s)end now  (d)raft to Gmail  (t) schedule Tue/Thu  (f)ile only  (e)dit  (k)ip for now  (x)clude forever"
    console.print(choices)
    action = Prompt.ask("Action", choices=["s", "d", "t", "f", "e", "k", "x"], default="t")

    if action == "k":
        console.print("[dim]Skipped (will reappear next run).[/dim]")
        return

    from linkedin_scraper import mark_url_processed

    if action == "x":
        if email.profile.url:
            mark_url_processed(email.profile.url)
        console.print("[dim]Excluded — won't appear again.[/dim]")
        return

    if action == "e":
        console.print("[dim]Opening your editor is not supported here. Email saved to file — edit it there.[/dim]")
        path = save_draft_to_file(email, args.output)
        console.print(f"  Saved to [bold]{path}[/bold]")
        append_to_spreadsheet(email, "Gmail")
        if email.profile.url:
            mark_url_processed(email.profile.url)
        return

    path = save_draft_to_file(email, args.output)
    console.print(f"  [green]✓ Saved to {path}[/green]")

    how_contacted = "Gmail"
    if action in ("s", "d", "t"):
        to_address = Prompt.ask(f"Recipient email for {email.profile.full_name}")
        if not to_address.strip():
            console.print("[yellow]No address provided — skipping Gmail action.[/yellow]")
            return
        to_address = to_address.strip()

        try:
            if action == "t":
                from schedule_sender import queue_email, DAY_NAMES, infer_timezone
                tz = infer_timezone(
                    location=getattr(email.profile, "location", ""),
                    notes=getattr(email.profile, "notes", ""),
                )
                tz_str = str(tz)
                send_at = queue_email(
                    to=to_address,
                    subject=email.subject,
                    body=email.body,
                    name=email.profile.full_name,
                    linkedin_url=email.profile.url or "",
                    recipient_tz=tz_str,
                )
                day_name = DAY_NAMES.get(send_at.weekday(), "")
                tz_label = tz_str.split("/")[-1].replace("_", " ")
                console.print(
                    f"  [green]✓ Queued — will send [bold]{day_name} "
                    f"{send_at.strftime('%b %d')} at {send_at.strftime('%I:%M %p')} {tz_label}[/bold][/green]"
                )
                how_contacted = "Scheduled"
            elif action == "d":
                from gmail_sender import create_draft
                draft = create_draft(email, to_address)
                console.print(f"  [green]✓ Draft created in Gmail (id: {draft['id']})[/green]")
            else:
                from gmail_sender import send_email
                if Confirm.ask(f"Really SEND to {to_address}?", default=False):
                    send_email(email, to_address)
                    console.print(f"  [green]✓ Sent to {to_address}[/green]")
                else:
                    console.print("[dim]Send cancelled.[/dim]")
        except Exception as e:
            console.print(f"  [red]Gmail action failed: {e}[/red]")

    append_to_spreadsheet(email, how_contacted)
    if email.profile.url:
        mark_url_processed(email.profile.url)

    # Hub: fire-and-forget update to contacts.json
    try:
        import hub_utils as _hub
        if email.profile.url:
            if action == "s":
                _hub.mark_sent(email.profile.url, to_address, email.subject)
            elif action == "t":
                _hub.mark_queued(email.profile.url, to_address, email.subject, send_at.isoformat())
            elif action == "d":
                _hub.mark_drafted(email.profile.url, to_address, email.subject)
    except Exception as _hub_err:
        console.print(f"  [dim]Hub update skipped: {_hub_err}[/dim]")



def main():
    args = parse_args()

    console.print(Panel.fit(
        "[bold blue]Banking Outreach Email Automation[/bold blue]\n"
        "Powered by Claude · Styled like your own emails",
        border_style="blue",
    ))

    if args.auth:
        run_auth()
        return

    if args.template:
        create_template()
        return

    if args.check:
        check_notes_file(args.check)
        return

    if args.followup:
        from followup_system import run_followup_flow
        run_followup_flow(console)
        return

    if args.send_queue:
        from schedule_sender import send_due_emails
        console.print("[bold]Checking scheduled email queue...[/bold]")
        sent = send_due_emails(console)
        if sent:
            console.print(f"[bold green]✓ Sent {sent} scheduled email(s).[/bold green]")
        return

    if args.list_queue:
        from schedule_sender import list_queue
        from rich.table import Table
        from zoneinfo import ZoneInfo
        queue = list_queue()
        if not queue:
            console.print("[green]No emails in the scheduled queue.[/green]")
            return
        table = Table(title=f"{len(queue)} scheduled email(s)")
        table.add_column("Recipient", style="cyan")
        table.add_column("Subject")
        table.add_column("Scheduled (local time)")
        for e in queue:
            dt = datetime.fromisoformat(e["scheduled_at"])
            tz_str = e.get("recipient_tz", "America/New_York")
            tz_label = tz_str.split("/")[-1].replace("_", " ")
            table.add_row(
                e.get("name") or e["to"],
                e["subject"][:55],
                dt.strftime(f"%a %b %d, %I:%M %p") + f" {tz_label}",
            )
        console.print(table)
        return

    # Default to CSV if no source flag given
    if not args.urls and not args.csv:
        args.csv = True

    profiles = load_profiles(args)
    if not profiles:
        console.print("[red]No profiles loaded. Nothing to do.[/red]")
        sys.exit(1)

    console.print(f"  [green]✓ Loaded {len(profiles)} profile(s)[/green]")

    check_unverified_notes(profiles)

    email_samples_text = fetch_email_samples(skip=args.no_gmail)

    console.print("\n[bold]Generating personalized emails with Claude...[/bold]")
    from email_generator import generate_emails_batch
    emails = generate_emails_batch(profiles, email_samples_text)

    console.print(f"\n[green]✓ Generated {len(emails)} email(s). Reviewing now...[/green]\n")

    for i, email in enumerate(emails, 1):
        display_email(email, i, len(emails))
        handle_email_action(email, args)
        console.print()

    console.print("[bold green]Done! All emails processed.[/bold green]")


if __name__ == "__main__":
    main()
