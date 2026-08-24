"""Create Gmail drafts or send emails via the Gmail API."""

import base64
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from googleapiclient.discovery import build
from gmail_auth import get_gmail_credentials
from email_generator import GeneratedEmail
from config import MY_BACKGROUND


def _plain_to_html(body: str) -> str:
    """Convert plain text with \n line breaks into clean HTML paragraphs."""
    import html
    paragraphs = body.strip().split("\n\n")
    parts = []
    for para in paragraphs:
        lines = para.strip().splitlines()
        escaped = "<br>".join(html.escape(line) for line in lines)
        parts.append(f"<p>{escaped}</p>")
    return (
        '<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#000;">'
        + "".join(parts)
        + "</div>"
    )


def _build_message(to: str, subject: str, body: str) -> dict:
    msg = MIMEMultipart("alternative")
    msg["to"] = to
    msg["from"] = MY_BACKGROUND["email"]
    msg["subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    msg.attach(MIMEText(_plain_to_html(body), "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


def create_draft(email: GeneratedEmail, to_address: str) -> dict:
    creds = get_gmail_credentials()
    service = build("gmail", "v1", credentials=creds)
    message = _build_message(to_address, email.subject, email.body)
    draft = service.users().drafts().create(
        userId="me", body={"message": message}
    ).execute()
    return draft


def send_email(email: GeneratedEmail, to_address: str) -> dict:
    creds = get_gmail_credentials()
    service = build("gmail", "v1", credentials=creds)
    message = _build_message(to_address, email.subject, email.body)
    sent = service.users().messages().send(userId="me", body=message).execute()
    return sent
