"""Integration tests for GFW annotations with mocked HTTP calls.

These tests validate the GFW client behavior without making real network calls,
which ensures tests are fast, reliable, and don't require API tokens.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from phase0.scripts.gfw_annotations import GFWClient, _normalize_response_entries


@pytest.fixture
def mock_gfw_client():
    """Create a GFW client with mocked HTTP requests."""
    with patch('phase0.scripts.gfw_annotations._request_with_retry') as mock_req:
        client = GFWClient("test_token_12345")
        yield client, mock_req


def test_gfw_client_initialization():
    """Test that GFW client initializes with required headers."""
    client = GFWClient("test_token")
    assert client.api_token == "test_token"
    assert "Authorization" in client.headers
    assert client.headers["Authorization"] == "Bearer test_token"


def test_get_sar_detections_success(mock_gfw_client):
    """Test successful SAR detections retrieval."""
    client, mock_req = mock_gfw_client

    # Mock successful response
    mock_req.return_value = {
        "entries": [
            {"lat": 33.0, "lon": -9.0, "confidence": 0.9, "id": "vessel1"},
            {"lat": 33.5, "lon": -9.5, "confidence": 0.85, "id": "vessel2"}
        ]
    }

    bbox = [-10.0, 32.0, -8.0, 34.0]
    results = client.get_sar_detections(bbox, "2024-01-01", "2024-01-02")

    assert len(results) == 2
    assert results[0]["lat"] == 33.0
    assert results[1]["lat"] == 33.5
    mock_req.assert_called()


def test_get_sar_detections_empty_response(mock_gfw_client):
    """Test handling of empty SAR detections response."""
    client, mock_req = mock_gfw_client

    # Mock empty response
    mock_req.return_value = {"entries": []}

    bbox = [-10.0, 32.0, -8.0, 34.0]
    results = client.get_sar_detections(bbox, "2024-01-01", "2024-01-02")

    assert len(results) == 0


def test_get_sar_detections_422_fallback_to_post(mock_gfw_client):
    """Test that 422 error triggers POST fallback."""
    client, mock_req = mock_gfw_client

    # First call (GET) raises 422, second call (POST) succeeds
    from httpx import HTTPStatusError

    mock_response_422 = Mock()
    mock_response_422.status_code = 422

    error_422 = HTTPStatusError(
        "422 Unprocessable Entity",
        request=Mock(),
        response=mock_response_422
    )

    mock_req.side_effect = [
        error_422,  # First call fails with 422
        {"entries": [{"lat": 33.0, "lon": -9.0}]}  # Second call succeeds
    ]

    bbox = [-10.0, 32.0, -8.0, 34.0]
    results = client.get_sar_detections(bbox, "2024-01-01", "2024-01-02")

    # Should eventually succeed after fallback
    assert len(results) == 1
    assert mock_req.call_count == 2  # GET + POST fallback


def test_get_sar_detections_404_no_silent_fallback(mock_gfw_client):
    """Test that 404 error does NOT have silent fallback (per requirements)."""
    client, mock_req = mock_gfw_client

    # Mock 404 error
    from httpx import HTTPStatusError

    mock_response_404 = Mock()
    mock_response_404.status_code = 404

    error_404 = HTTPStatusError(
        "404 Not Found",
        request=Mock(),
        response=mock_response_404
    )

    mock_req.side_effect = error_404

    bbox = [-10.0, 32.0, -8.0, 34.0]

    # Should raise the 404 error (no silent fallback)
    with pytest.raises(HTTPStatusError) as exc_info:
        client.get_sar_detections(bbox, "2024-01-01", "2024-01-02")

    assert exc_info.value.response.status_code == 404


def test_normalize_response_entries_various_formats():
    """Test that response normalization handles various API response formats."""
    # Test with 'entries' field
    assert len(_normalize_response_entries({"entries": [1, 2, 3]})) == 3

    # Test with 'results' field
    assert len(_normalize_response_entries({"results": [1, 2]})) == 2

    # Test with 'data' field
    assert len(_normalize_response_entries({"data": [1]})) == 1

    # Test with None
    assert len(_normalize_response_entries(None)) == 0

    # Test with unrecognized format
    assert len(_normalize_response_entries({"unknown": [1, 2]})) == 0


def test_search_vessels(mock_gfw_client):
    """Test vessel search functionality."""
    client, mock_req = mock_gfw_client

    mock_req.return_value = {
        "entries": [
            {"name": "Test Vessel", "id": "vessel123"}
        ]
    }

    results = client.search_vessels("test query", limit=10)

    assert len(results) == 1
    assert results[0]["name"] == "Test Vessel"
    mock_req.assert_called_once()


def test_gfw_client_retry_logic():
    """Test that client implements retry logic for transient errors."""
    with patch('phase0.scripts.gfw_annotations.time.sleep') as mock_sleep, \
         patch('phase0.scripts.gfw_annotations.httpx.Client') as mock_client:

        mock_client_instance = MagicMock()
        mock_client.return_value.__enter__.return_value = mock_client_instance

        from httpx import Response

        # Mock responses
        mock_response_500 = Response(status_code=500, request=MagicMock())
        mock_response_success = Response(
            status_code=200,
            request=MagicMock(),
            json={"entries": [{"lat": 33.0, "lon": -9.0}]}
        )

        mock_client_instance.get.side_effect = [
            mock_response_500,
            mock_response_500,
            mock_response_success
        ]

        client = GFWClient("test_token")
        results = client.get_sar_detections([-10.0, 32.0, -8.0, 34.0], "2024-01-01", "2024-01-02")

        # Should succeed after retries
        assert len(results) == 1
        assert mock_client_instance.get.call_count == 3  # 2 failures + 1 success
        assert mock_sleep.call_count == 2  # 2 backoff sleeps
