import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# EDIT THESE: your name (signs the follow-ups and names the resume attachment) and the
# Gmail address you send from (the account you log in with).
MY_BACKGROUND = {
    "name": "Your Name",
    "email": "you@example.com",
}


def _resume_pdfs() -> list:
    """Root PDFs with 'resume' in the name, newest first.

    Newest first, so dropping in an updated resume wins over an older copy that
    happens to sort earlier in the directory listing.
    """
    names = [
        f for f in os.listdir(_BASE_DIR)
        if "resume" in f.lower() and f.lower().endswith(".pdf") and not f.startswith(("~$", "#"))
    ]
    names.sort(key=lambda f: os.path.getmtime(os.path.join(_BASE_DIR, f)), reverse=True)
    return names


# Resume PDF attached to every outreach email: put a PDF with "resume" in its name in
# the repo root (PDFs are gitignored). Recipients see it as RESUME_ATTACHMENT_NAME, not
# the local filename. With no PDF, emails go out without the attachment or the P.S.
_pdfs = _resume_pdfs()
RESUME_PDF = os.path.join(_BASE_DIR, _pdfs[0]) if _pdfs else ""
RESUME_ATTACHMENT_NAME = MY_BACKGROUND["name"].replace(" ", "_") + "_Resume.pdf"

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

GMAIL_CREDENTIALS_FILE = os.path.join(_BASE_DIR, "credentials.json")
GMAIL_TOKEN_FILE = os.path.join(_BASE_DIR, "token.json")
