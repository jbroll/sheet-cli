"""OAuth 2.0 authentication for Google Sheets API."""

import os
import pickle
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

from .exceptions import AuthenticationError


# Scopes required for Google Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Default credentials directory
DEFAULT_CREDS_DIR = Path.home() / '.sheet-cli'


def get_credentials(credentials_path: str = None,
                   token_path: str = None) -> Credentials:
    """Get OAuth 2.0 credentials, prompting user if needed.

    Args:
        credentials_path: Path to OAuth client credentials JSON file
                         (defaults to ~/.sheet-cli/credentials.json)
        token_path: Path to cached token pickle file
                   (defaults to ~/.sheet-cli/token.pickle)

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

    # Try to load cached token
    if os.path.exists(token_path):
        try:
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
        except Exception as e:
            raise AuthenticationError(f"Failed to load token from {token_path}: {e}")

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
