"""OAuth 2.0 authentication for Google Sheets API."""

import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

from .exceptions import AuthenticationError


# Scopes required for Google Sheets and Drive API.
# Drive is needed at the full `drive` level so `delete_spreadsheet()` can move
# user-owned spreadsheets to trash — `drive.metadata.readonly` can list but not
# delete, and `drive.file` only covers files this app created.
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

DEFAULT_CREDS_DIR = Path.home() / '.sheet-cli'


def _has_required_scopes(creds: Credentials) -> bool:
    scopes = getattr(creds, 'scopes', None)
    if not scopes:
        return False
    return set(SCOPES).issubset(set(scopes))


def get_credentials(credentials_path: Optional[str] = None,
                   token_path: Optional[str] = None,
                   force_reauth: bool = False) -> Credentials:
    """Get OAuth 2.0 credentials, prompting user if needed.

    Args:
        credentials_path: Path to OAuth client credentials JSON file
                         (defaults to ~/.sheet-cli/credentials.json)
        token_path: Path to cached token JSON file
                   (defaults to ~/.sheet-cli/token.json)
        force_reauth: If True, delete any cached token and re-run OAuth flow

    Returns:
        Valid Credentials object

    Raises:
        AuthenticationError: If authentication fails
    """
    if credentials_path is None:
        credentials_path = str(DEFAULT_CREDS_DIR / 'credentials.json')
    if token_path is None:
        token_path = str(DEFAULT_CREDS_DIR / 'token.json')

    DEFAULT_CREDS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

    # Legacy pickle tokens from pre-JSON versions are always stale (pickle is
    # unsafe to deserialize and pre-dates the expanded Drive scope). Drop them.
    legacy_pickle = DEFAULT_CREDS_DIR / 'token.pickle'
    if legacy_pickle.exists():
        legacy_pickle.unlink()

    creds: Optional[Credentials] = None

    if force_reauth and os.path.exists(token_path):
        os.remove(token_path)

    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path)
        except Exception as e:
            raise AuthenticationError(f"Failed to load token from {token_path}: {e}")

        if creds and not _has_required_scopes(creds):
            print("OAuth scopes have changed, re-authenticating...", flush=True)
            os.remove(token_path)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                raise AuthenticationError(f"Failed to refresh token: {e}")
        else:
            if not os.path.exists(credentials_path):
                raise AuthenticationError(
                    f"Credentials file not found: {credentials_path}\n"
                    "Please download OAuth 2.0 Client ID credentials from Google Cloud Console."
                )

            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)  # type: ignore[assignment]
            except Exception as e:
                raise AuthenticationError(f"OAuth flow failed: {e}")

        try:
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
            os.chmod(token_path, 0o600)
        except Exception as e:
            raise AuthenticationError(f"Failed to save token to {token_path}: {e}")

    assert creds is not None
    return creds
