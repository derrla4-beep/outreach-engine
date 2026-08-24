"""
LinkedIn profile data extraction.

Three modes (in order of reliability):
  1. CSV / manual input  — fastest, always works, use this by default
  2. Playwright scraping — requires `playwright install chromium` and LinkedIn login
  3. requests fallback   — almost always blocked by LinkedIn; kept for completeness
"""

import csv
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()


CSV_TEMPLATE_PATH = Path("data/profiles.csv")
CSV_HEADERS = ["url", "first_name", "last_name", "title", "company", "school", "grad_year", "notes"]


@dataclass
class LinkedInProfile:
    url: str
    first_name: str
    last_name: str
    title: str
    company: str
    school: str = ""
    grad_year: str = ""
    notes: str = ""
    # enriched fields populated by Claude extraction
    past_roles: str = ""       # "Analyst at JPMorgan (2022–2023), Intern at Lazard (2021)"
    location: str = ""         # "New York, NY"
    clubs: str = ""            # "Finance Club, Investment Club"
    fraternity: str = ""       # "Alpha Kappa Psi"
    activities: str = ""       # other extracurriculars / leadership
    about: str = ""            # LinkedIn About / summary section

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


# ---------------------------------------------------------------------------
# CSV / manual input
# ---------------------------------------------------------------------------

def create_csv_template() -> None:
    """Write a blank CSV template for the user to fill in."""
    CSV_TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CSV_TEMPLATE_PATH.exists():
        with open(CSV_TEMPLATE_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerow({
                "url": "https://www.linkedin.com/in/example",
                "first_name": "Jane",
                "last_name": "Smith",
                "title": "Vice President",
                "company": "Goldman Sachs",
                "school": "Harvard University",
                "grad_year": "2015",
                "notes": "Met at a campus finance panel",
            })
        print(f"Created template at {CSV_TEMPLATE_PATH} — fill it in and re-run.")
    else:
        print(f"Template already exists at {CSV_TEMPLATE_PATH}")


def load_profiles_from_csv(path: Path | None = None) -> list[LinkedInProfile]:
    from config import resolve_data_file

    if path is None:
        path = Path(resolve_data_file("profiles.csv"))
    if not path.exists():
        raise FileNotFoundError(
            f"Profile CSV not found at {path}. Run with --template to create one."
        )

    processed = load_processed_urls()
    profiles = []
    skipped = 0
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            first = row.get("first_name", "").strip()
            last = row.get("last_name", "").strip()
            title = row.get("title", "").strip()
            company = row.get("company", "").strip()
            if not first or not title or not company:
                continue  # skip blank/example rows
            url = row.get("url", "").strip()
            if url and url in processed:
                skipped += 1
                continue
            profiles.append(LinkedInProfile(
                url=url,
                first_name=first,
                last_name=last,
                title=title,
                company=company,
                school=row.get("school", "").strip(),
                grad_year=row.get("grad_year", "").strip(),
                notes=row.get("notes", "").strip(),
            ))
    if skipped:
        print(f"Skipping {skipped} already-processed profile(s) from CSV.")
    return profiles


# ---------------------------------------------------------------------------
# Playwright scraping (best-effort; requires logged-in LinkedIn session)
# ---------------------------------------------------------------------------

def _parse_profile_from_page(page) -> dict:
    """Extract profile fields from a rendered LinkedIn page using Claude to parse raw text."""
    import anthropic

    # Scroll through the page to trigger lazy-loaded sections
    try:
        page.evaluate("window.scrollTo(0, 800)")
        time.sleep(1.5)
        page.evaluate("window.scrollTo(0, 1600)")
        time.sleep(1)
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.5)
    except Exception:
        pass

    # Extract text from main content (avoids nav/footer noise)
    page_text = ""
    try:
        main_el = page.query_selector("main")
        page_text = main_el.inner_text() if main_el else page.inner_text("body")
    except Exception:
        try:
            page_text = page.inner_text("body")
        except Exception:
            pass

    if not page_text or len(page_text) < 30:
        return {}

    # First 6000 chars covers name, headline, experience, education
    page_text = page_text[:6000]

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{
                "role": "user",
                "content": (
                    "Extract profile information from this LinkedIn page text. "
                    "Return ONLY valid JSON with exactly these fields (empty string if not found):\n"
                    "{\n"
                    '  "first_name": "",\n'
                    '  "last_name": "",\n'
                    '  "title": "",\n'
                    '  "company": "",\n'
                    '  "school": "",\n'
                    '  "grad_year": "",\n'
                    '  "past_roles": "",\n'
                    '  "location": "",\n'
                    '  "clubs": "",\n'
                    '  "fraternity": "",\n'
                    '  "activities": "",\n'
                    '  "about": ""\n'
                    "}\n\n"
                    "Rules:\n"
                    "- title: current job title\n"
                    "- company: current employer\n"
                    "- school: most recent university\n"
                    "- grad_year: 4-digit graduation year or empty\n"
                    "- past_roles: comma-separated previous jobs, e.g. 'Analyst at JPMorgan (2022–2023), Intern at Lazard (2021)'\n"
                    "- location: current city/region, e.g. 'New York, NY'\n"
                    "- clubs: campus clubs, finance clubs, honor societies, case competitions — comma-separated\n"
                    "- fraternity: fraternity or sorority name, or empty\n"
                    "- activities: sports teams, volunteer work, leadership roles outside work — comma-separated\n"
                    "- about: 1–2 sentence summary of their LinkedIn About section if present\n\n"
                    f"LinkedIn page text:\n{page_text}"
                ),
            }],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return json.loads(raw)
    except Exception as e:
        print(f"    Claude profile parsing failed: {e}")
        return {}


def scrape_profiles_playwright(
    url_notes: dict[str, str],
    session_file: str = "data/linkedin_session.json",
) -> list[LinkedInProfile]:
    """
    Scrape LinkedIn profiles using Playwright.

    On first run (no session file), it opens a visible browser for you to log in
    manually, then saves the session. Subsequent runs reuse the saved session.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return []

    profiles = []
    session_path = Path(session_file)
    session_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = (
            browser.new_context(storage_state=str(session_path))
            if session_path.exists()
            else browser.new_context()
        )
        page = context.new_page()

        # First-run login flow
        if not session_path.exists():
            print("\nOpening browser for LinkedIn login...")
            print("Log in to LinkedIn, then press Enter here to continue.")
            page.goto("https://www.linkedin.com/login")
            input("Press Enter after you've logged in to LinkedIn > ")
            context.storage_state(path=str(session_path))
            print(f"Session saved to {session_path}")

        logged_in = False

        for url, note in url_notes.items():
            print(f"  Scraping {url} ...")
            try:
                page.goto(url, timeout=60_000)
                # networkidle waits until no network requests for 500ms — gives React time to hydrate
                try:
                    page.wait_for_load_state("networkidle", timeout=30_000)
                except Exception:
                    page.wait_for_load_state("domcontentloaded", timeout=15_000)
                time.sleep(3)

                current_url = page.url
                print(f"    Landed on: {current_url}")

                # Detect redirect to login/authwall and trigger interactive login
                if any(x in current_url for x in ("login", "authwall", "checkpoint", "signup")):
                    if not logged_in:
                        print("\n    LinkedIn requires login. Log in in the browser window.")
                        input("    Press Enter here after you've logged in > ")
                        context.storage_state(path=str(session_path))
                        print(f"    Session saved to {session_path}")
                        logged_in = True
                        # Re-navigate to the profile after login
                        page.goto(url, timeout=60_000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=30_000)
                        except Exception:
                            page.wait_for_load_state("domcontentloaded", timeout=15_000)
                        time.sleep(5)
                    else:
                        print(f"    Still not logged in — skipping {url}")
                        continue
                else:
                    logged_in = True

                # Scroll to trigger lazy-loaded sections, then wait for h1
                page.evaluate("window.scrollTo(0, 600)")
                time.sleep(1)
                try:
                    page.wait_for_selector("h1", timeout=10_000)
                except Exception:
                    # h1 didn't appear — try one more scroll + wait
                    page.evaluate("window.scrollTo(0, 0)")
                    time.sleep(2)

                data = _parse_profile_from_page(page)
                if data.get("first_name"):
                    profiles.append(LinkedInProfile(
                        url=url,
                        first_name=data.get("first_name", ""),
                        last_name=data.get("last_name", ""),
                        title=data.get("title", ""),
                        company=data.get("company", ""),
                        school=data.get("school", ""),
                        grad_year=data.get("grad_year", ""),
                        past_roles=data.get("past_roles", ""),
                        location=data.get("location", ""),
                        clubs=data.get("clubs", ""),
                        fraternity=data.get("fraternity", ""),
                        activities=data.get("activities", ""),
                        about=data.get("about", ""),
                        notes=note,
                    ))
                else:
                    print(f"    Could not parse profile at {url}.")
                    h1_text = ""
                    try:
                        h1_el = page.query_selector("h1")
                        h1_text = h1_el.inner_text().strip() if h1_el else "(no h1 found)"
                    except Exception:
                        h1_text = "(error reading h1)"
                    print(f"    Page title: {page.title()!r}")
                    print(f"    h1 content: {h1_text!r}")
            except Exception as e:
                print(f"    Error scraping {url}: {e}")
            time.sleep(3)

        browser.close()

    return profiles


# ---------------------------------------------------------------------------
# URL-list loader (calls Playwright scraper)
# ---------------------------------------------------------------------------

PROCESSED_URLS_FILE = Path("data/processed_urls.txt")


def load_processed_urls() -> set[str]:
    if not PROCESSED_URLS_FILE.exists():
        return set()
    return {line.strip() for line in PROCESSED_URLS_FILE.read_text().splitlines() if line.strip()}


def mark_url_processed(url: str):
    PROCESSED_URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PROCESSED_URLS_FILE.open("a") as f:
        f.write(url.strip() + "\n")


def load_profiles_from_urls(url_file: str) -> list[LinkedInProfile]:
    path = Path(url_file)
    if not path.exists():
        raise FileNotFoundError(f"URL file not found: {url_file}")

    # Support "URL | personal note" format — note is optional
    url_notes: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            url, note = line.split("|", 1)
            url_notes[url.strip()] = note.strip()
        else:
            url_notes[line] = ""

    processed = load_processed_urls()
    new_url_notes = {u: n for u, n in url_notes.items() if u not in processed}
    skipped = len(url_notes) - len(new_url_notes)
    if skipped:
        print(f"Skipping {skipped} already-processed URL(s).")
    print(f"Found {len(new_url_notes)} new LinkedIn URL(s) to scrape.")
    return scrape_profiles_playwright(new_url_notes)
