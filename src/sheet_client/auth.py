"""OAuth 2.0 authentication for Google Sheets API."""

import os
import pickle
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

from .exceptions import AuthenticationError


# Scopes required for Google Sheets and Drive API
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.metadata.readonly',
]

# Default credentials directory
DEFAULT_CREDS_DIR = Path.home() / '.sheet-cli'


def _has_required_scopes(creds: Credentials) -> bool:
    """Return True if credentials include all required scopes."""
    if not getattr(creds, 'scopes', None):
        return False
    return set(SCOPES).issubset(set(creds.scopes))


def get_credentials(credentials_path: str = None,
                   token_path: str = None,
                   force_reauth: bool = False) -> Credentials:
    """Get OAuth 2.0 credentials, prompting user if needed.

    Args:
        credentials_path: Path to OAuth client credentials JSON file
                         (defaults to ~/.sheet-cli/credentials.json)
        token_path: Path to cached token pickle file
                   (defaults to ~/.sheet-cli/token.pickle)
        force_reauth: If True, delete any cached token and re-run OAuth flow

    Returns:
        Valid Credentials object

    Raises:
        AuthenticationError: If authentication fails
    """
    # Use default paths if not specified
    if credentials_path is None:
        credentials_path = str(DEFAULT_CREDS_DIR / 'credentials.json')
    if token_path is None:
        token_path = str(DEFAULT_CREDS_DIR / 'token.pickle')

    # Ensure credentials directory exists
    DEFAULT_CREDS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

    creds: Optional[Credentials] = None

    # Force re-authentication if requested
    if force_reauth and os.path.exists(token_path):
        os.remove(token_path)

    # Try to load cached token
    if os.path.exists(token_path):
        try:
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
        except Exception as e:
            raise AuthenticationError(f"Failed to load token from {token_path}: {e}")

        # Check if token has all required scopes (e.g. after scope expansion)
        if creds and not _has_required_scopes(creds):
            print("OAuth scopes have changed, re-authenticating...", flush=True)
            os.remove(token_path)
            creds = None

    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh expired token
            try:
                creds.refresh(Request())
            except Exception as e:
                raise AuthenticationError(f"Failed to refresh token: {e}")
        else:
            # Start OAuth flow
            if not os.path.exists(credentials_path):
                raise AuthenticationError(
                    f"Credentials file not found: {credentials_path}\n"
                    "Please download OAuth 2.0 Client ID credentials from Google Cloud Console."
                )

            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                raise AuthenticationError(f"OAuth flow failed: {e}")

        # Save token for future use
        try:
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)
            # Set secure permissions (read/write for user only)
            os.chmod(token_path, 0o600)
        except Exception as e:
            raise AuthenticationError(f"Failed to save token to {token_path}: {e}")

    return creds
