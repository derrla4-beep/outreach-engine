"""Runtime configuration.

Nothing in this file is personal. The operator's identity, background, and
credibility hooks live in `data/profile.json` (gitignored); a fictional
`data/profile.example.json` is committed so the project runs out of the box.
"""

import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))

PROFILE_FILE = os.path.join(BASE, "data", "profile.json")
PROFILE_EXAMPLE_FILE = os.path.join(BASE, "data", "profile.example.json")


def resolve_data_file(filename: str) -> str:
    """Resolve a file in data/, falling back to its committed `.example` twin.

    Real operator data (contacts, queues, profiles) is gitignored, so a fresh
    clone has only the `.example` files. Reads go through here; writes always
    target the real filename so example data is never mutated.
    """
    real = os.path.join(BASE, "data", filename)
    if os.path.exists(real):
        return real
    stem, ext = os.path.splitext(filename)
    example = os.path.join(BASE, "data", stem + ".example" + ext)
    return example if os.path.exists(example) else real


def data_path(filename: str) -> str:
    """Absolute path to a file in data/, for writes."""
    return os.path.join(BASE, "data", filename)


def _load_profile() -> dict:
    """Load the operator profile, preferring the real one over the example."""
    for path in (PROFILE_FILE, PROFILE_EXAMPLE_FILE):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            if path is PROFILE_EXAMPLE_FILE:
                print("[profile] Using data/profile.example.json — copy it to "
                      "data/profile.json and fill in your own details.")
            return profile
    raise FileNotFoundError(
        "No profile found. Copy data/profile.example.json to data/profile.json "
        "and fill in your details."
    )


def _load_resume_text() -> str:
    """Load resume text from any PDF/TXT file containing 'resume' in its name.

    Resumes are gitignored, so this returns "" in a fresh clone and the
    generator falls back to the profile's structured background.
    """
    for fname in os.listdir(BASE):
        if "resume" in fname.lower() and fname.lower().endswith(".pdf"):
            try:
                import pdfplumber
                with pdfplumber.open(os.path.join(BASE, fname)) as pdf:
                    pages = [page.extract_text() or "" for page in pdf.pages]
                text = "\n".join(pages).strip()
                if text:
                    print(f"[resume] Loaded from {fname}")
                    return text
            except Exception as e:
                print(f"[warning] Could not parse {fname}: {e}")

    txt_path = os.path.join(BASE, "resume.txt")
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            return f.read().strip()

    return ""


def _load_text_file(filename: str) -> str:
    path = os.path.join(BASE, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


MY_BACKGROUND = _load_profile()
RESUME_TEXT = _load_resume_text()

# Optional local style inputs (both gitignored — see .gitignore).
#   voice.txt       a few paragraphs in your own writing, for tone matching
#   best_emails.txt outreach emails of yours that actually got replies
VOICE_TEXT = _load_text_file("voice.txt")
BEST_EMAILS_TEXT = _load_text_file("best_emails.txt")

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

SENT_EMAILS_TO_SAMPLE = 10

GMAIL_CREDENTIALS_FILE = "credentials.json"
GMAIL_TOKEN_FILE = "token.json"

ANTHROPIC_MODEL = "claude-sonnet-4-6"
