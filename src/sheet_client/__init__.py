"""Google Sheets CLI - Minimal Python wrapper for Google Sheets REST API v4."""

from .client import SheetsClient, CellData
from .exceptions import (
    SheetsClientError,
    AuthenticationError,
    SheetsAPIError,
    RateLimitError,
    ServerError
)
from .utils import column_to_index, index_to_column, a1_to_grid_range

__version__ = '0.1.0'

__all__ = [
    'SheetsClient',
    'CellData',
    'SheetsClientError',
    'AuthenticationError',
    'SheetsAPIError',
    'RateLimitError',
    'ServerError',
    'column_to_index',
    'index_to_column',
    'a1_to_grid_range',
]
