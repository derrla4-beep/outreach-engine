"""Shared text helpers for outgoing emails: cleanup, sign-off, and plain text to HTML."""

import html
import re
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import MY_BACKGROUND, RESUME_ATTACHMENT_NAME, RESUME_PDF


def clean_email_text(text: str) -> str:
    # Em/en dashes used as sentence separators become commas. Handle the
    # padded case first so we don't leave a stray space before the comma
    # (e.g. "science — placed" must become "science, placed", not "science , placed").
    text = text.replace(" — ", ", ").replace("—", ", ")
    text = text.replace(" – ", ", ").replace("–", ", ")
    text = text.replace(" → ", " to ").replace("→", " to ")

    # General comma-spacing normalizer, in case the model (or the dash
    # substitution above) leaves commas misspaced anywhere else.
    text = re.sub(r"[ \t]+,", ",", text)  # no space before a comma
    text = re.sub(r"(\d),(\d)", r"\1<COMMA>\2", text)  # protect "1,000"-style grouping
    text = re.sub(r",(?!\s|$)", ", ", text)  # ensure one space after a comma
    text = text.replace("<COMMA>", ",")

    return text


# Matches an http(s) URL or a bare linkedin.com path. Applied to already-escaped
# text, where html.escape has turned any & into &amp; and any < > into entities,
# so stopping at whitespace and angle brackets is enough to bound the match.
_URL_RE = re.compile(r'https?://[^\s<>]+|(?:www\.)?linkedin\.com/[^\s<>]+')

# Trailing sentence punctuation belongs after the link, not inside the href.
_URL_TAIL = ".,;:!?)"


def _linkify(escaped: str) -> str:
    # Gmail does not auto-link inside a supplied text/html part, so a bare URL in the
    # HTML alternative renders as dead text. The text/plain part keeps the raw URL.
    def repl(m):
        url = m.group(0)
        tail = ""
        while url and url[-1] in _URL_TAIL:
            tail = url[-1] + tail
            url = url[:-1]
        if not url:
            return tail
        href = url if url.startswith("http") else "https://" + url
        return '<a href="%s">%s</a>%s' % (href, url, tail)

    return _URL_RE.sub(repl, escaped)


def plain_to_html(body: str, signature_html: str = "") -> str:
    """Convert plain text with \n line breaks into HTML that looks hand-typed in Gmail.

    Shared by every send path so every email renders the same way. Gmail's "Sans Serif" is arial,sans-serif and its "Normal" size is simply
    no font-size, so none is set; blank lines are <br><br> rather than <p> margins,
    matching what Gmail compose produces.
    """
    lines = body.strip().splitlines()
    content = "<br>".join(_linkify(html.escape(line)) for line in lines)
    if signature_html:
        content += '<br><div class="gmail_signature">' + signature_html + "</div>"
    return '<div dir="ltr" style="font-family:arial,sans-serif">' + content + "</div>"


def signature_to_text(signature_html: str) -> str:
    """Plain-text rendering of the Gmail signature for the text/plain MIME part."""
    def anchor(m):
        href, text = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        bare = re.sub(r"^(https?://(www\.)?|mailto:|tel:)", "", href).rstrip("/")
        return text if not href or bare in text else f"{text} ({bare})"

    text = re.sub(r'<a\b[^>]*href="([^"]*)"[^>]*>(.*?)</a>', anchor, signature_html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</?(div|p)\b[^>]*>", "\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def strip_signoff(body: str) -> str:
    """Everything before the sign-off: cut at the resume P.S. or a closer.

    The closer only counts when followed by the name or the end of the body, so a
    "Thanks, ..." sentence inside Lines 1-4 is left alone. This also removes a
    hand-typed name line under the closer, which the Gmail signature replaces.
    """
    name = MY_BACKGROUND["name"]
    first = name.split()[0]
    cut = len(body)
    for pattern in (
        r"\n\s*P\.S\.",
        rf"^(?:Thanks|Thank you),[ \t]*(?:\n(?:{name}|{first})\b|\s*\Z)",
    ):
        m = re.search(pattern, body, re.M)
        if m:
            cut = min(cut, m.start())
    return body[:cut].strip()


def signoff_block() -> str:
    # The resume goes out as a PDF attachment (see attach_bodies). The P.S. goes
    # first and "Thanks," last so the Gmail signature (which carries the name)
    # sits directly under the closer.
    block = ""
    if RESUME_PDF:
        block = "P.S. I've attached my resume in case you wanted to take a look.\n\n"
    return block + "Thanks,"


def ensure_signoff(body: str) -> str:
    """Canonical outreach ending. Also rewrites older queued bodies (name, LinkedIn,
    or the old resume-link P.S.) into the current format at send time."""
    return strip_signoff(body) + "\n\n" + signoff_block()


def attach_bodies(msg, body: str, signature_html: str, with_resume: bool = False):
    """Attach the text/plain and text/html alternatives, each ending with the Gmail
    signature, plus the resume PDF when with_resume. msg must be multipart/mixed."""
    plain = body
    if signature_html:
        plain += "\n" + signature_to_text(signature_html)
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain, "plain"))
    alt.attach(MIMEText(plain_to_html(body, signature_html), "html"))
    msg.attach(alt)
    if with_resume and RESUME_PDF:
        with open(RESUME_PDF, "rb") as f:
            pdf = MIMEApplication(f.read(), _subtype="pdf")
        pdf.add_header("Content-Disposition", "attachment", filename=RESUME_ATTACHMENT_NAME)
        msg.attach(pdf)
