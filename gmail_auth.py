"""Gmail OAuth2 authentication. Run this once to generate token.json."""

import os
import json
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from config import GMAIL_SCOPES, GMAIL_CREDENTIALS_FILE, GMAIL_TOKEN_FILE


def get_gmail_credentials() -> Credentials:
    creds = None

    if Path(GMAIL_TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(GMAIL_CREDENTIALS_FILE).exists():
                raise FileNotFoundError(
                    f"Missing {GMAIL_CREDENTIALS_FILE}. "
                    "See SETUP.md for instructions to download it from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                GMAIL_CREDENTIALS_FILE, GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(GMAIL_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds


if __name__ == "__main__":
    creds = get_gmail_credentials()
    print("Gmail authentication successful. token.json saved.")
