"""OAuth 2.0 authentication for Google Sheets API."""

import os
import pickle
from typing import Optional

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

from .exceptions import AuthenticationError


# Scopes required for Google Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def get_credentials(credentials_path: str = 'credentials.json',
                   token_path: str = 'token.pickle') -> Credentials:
    """Get OAuth 2.0 credentials, prompting user if needed.

    Args:
        credentials_path: Path to OAuth client credentials JSON file
        token_path: Path to cached token pickle file

    Returns:
        Valid Credentials object

    Raises:
        AuthenticationError: If authentication fails
    """
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
        except Exception as e:
            raise AuthenticationError(f"Failed to save token to {token_path}: {e}")

    return creds
