"""Custom exceptions for Google Sheets CLI."""


class SheetsClientError(Exception):
    """Base exception for all Sheets client errors."""
    pass


class AuthenticationError(SheetsClientError):
    """Raised when OAuth authentication fails."""
    pass


class SheetsAPIError(SheetsClientError):
    """Raised when Google Sheets API returns an error."""

    def __init__(self, message: str, status_code: int = None, response: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class RateLimitError(SheetsAPIError):
    """Raised when API rate limit is exceeded (429)."""
    pass


class ServerError(SheetsAPIError):
    """Raised when API returns server error (500, 503)."""
    pass
