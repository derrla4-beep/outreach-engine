"""Gmail OAuth2 authentication. The first run opens a browser and saves token.json."""

from pathlib import Path
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from config import GMAIL_SCOPES, GMAIL_CREDENTIALS_FILE, GMAIL_TOKEN_FILE, MY_BACKGROUND


def get_gmail_credentials() -> Credentials:
    creds = None

    if Path(GMAIL_TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                # Expired or revoked (Google expires them after 7 days while the OAuth
                # app is in Testing). Log in again in the browser instead of crashing.
                print("Gmail login expired - opening the browser to log in again.")
                creds = None
        if not creds or not creds.valid:
            if not Path(GMAIL_CREDENTIALS_FILE).exists():
                raise FileNotFoundError(
                    "Missing credentials.json. "
                    "See SETUP.md for instructions to download it from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                GMAIL_CREDENTIALS_FILE, GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(GMAIL_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds


def gmail_service():
    """An authenticated Gmail API client."""
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=get_gmail_credentials())


_signature_cache: dict = {}


def get_signature_html(service) -> str:
    """The Gmail signature for the send-from address, fetched once per run.

    The API does not append signatures to sent mail, so the send paths add it
    themselves. It only exposes the signature set as the default for new emails,
    not one picked by name, so your outreach signature must be that default.
    """
    address = MY_BACKGROUND["email"]
    if address not in _signature_cache:
        send_as = service.users().settings().sendAs().get(
            userId="me", sendAsEmail=address
        ).execute()
        signature = (send_as.get("signature") or "").strip()
        if not signature:
            raise RuntimeError(
                f"No Gmail signature found for {address}. In Gmail go to Settings > General > "
                "Signature defaults and set 'For new emails use' to your outreach signature."
            )
        _signature_cache[address] = signature
    return _signature_cache[address]


if __name__ == "__main__":
    creds = get_gmail_credentials()
    print("Gmail authentication successful. token.json saved.")
