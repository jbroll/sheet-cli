"""Tests for _execute_with_retry backoff behavior."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_client import SheetsClient
from sheet_client.exceptions import RateLimitError, ServerError, SheetsAPIError


def _http_error(status):
    """Construct a googleapiclient HttpError-like mock with a .resp.status."""
    from googleapiclient.errors import HttpError
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b'err')


@pytest.fixture
def client():
    with patch('sheet_client.client.get_credentials'), \
         patch('sheet_client.client.build'):
        yield SheetsClient()


@pytest.fixture(autouse=True)
def no_sleep():
    """Make retries instant."""
    with patch('sheet_client.client.time.sleep'):
        yield


class TestRetry:
    def test_success_no_retry(self, client):
        req = MagicMock()
        req.execute.return_value = {'ok': True}
        assert client._execute_with_retry(req) == {'ok': True}
        assert req.execute.call_count == 1

    def test_429_retries_then_succeeds(self, client):
        req = MagicMock()
        req.execute.side_effect = [_http_error(429), _http_error(429), {'ok': True}]
        assert client._execute_with_retry(req) == {'ok': True}
        assert req.execute.call_count == 3

    def test_429_exhausts_retries(self, client):
        req = MagicMock()
        req.execute.side_effect = [_http_error(429)] * 3
        with pytest.raises(RateLimitError) as info:
            client._execute_with_retry(req)
        assert info.value.status_code == 429
        assert req.execute.call_count == 3

    def test_500_retries_then_succeeds(self, client):
        req = MagicMock()
        req.execute.side_effect = [_http_error(500), {'ok': True}]
        assert client._execute_with_retry(req) == {'ok': True}

    def test_503_exhausts_retries(self, client):
        req = MagicMock()
        req.execute.side_effect = [_http_error(503)] * 3
        with pytest.raises(ServerError) as info:
            client._execute_with_retry(req)
        assert info.value.status_code == 503

    def test_400_no_retry(self, client):
        req = MagicMock()
        req.execute.side_effect = _http_error(400)
        with pytest.raises(SheetsAPIError) as info:
            client._execute_with_retry(req)
        assert info.value.status_code == 400
        # Not retried
        assert req.execute.call_count == 1

    def test_404_no_retry(self, client):
        req = MagicMock()
        req.execute.side_effect = _http_error(404)
        with pytest.raises(SheetsAPIError):
            client._execute_with_retry(req)
        assert req.execute.call_count == 1


class TestClearMethod:
    def test_clear_calls_batch_clear(self, client):
        mock_values = MagicMock()
        mock_req = MagicMock()
        mock_req.execute.return_value = {'clearedRanges': ['A1:B2']}
        mock_values.batchClear.return_value = mock_req
        client.spreadsheets.values.return_value = mock_values

        result = client.clear('SID', ['A1:B2'])

        assert result == {'clearedRanges': ['A1:B2']}
        mock_values.batchClear.assert_called_once()
        kwargs = mock_values.batchClear.call_args.kwargs
        assert kwargs['spreadsheetId'] == 'SID'
        assert kwargs['body'] == {'ranges': ['A1:B2']}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
