"""Integration tests for GFW annotations with mocked HTTP calls.

These tests validate the GFW client behavior without making real network calls,
which ensures tests are fast, reliable, and don't require API tokens.

NOTE per PH0-CORR-002:
- get_sar_detections() has been REMOVED from the module (dataset returns grid cell aggregates)
- Replaced by gfw_get_ais_presence() for Level 1 annotation seeds
- get_ais_vessels() kept for backward compatibility
"""

from unittest.mock import MagicMock, patch

import pytest

from research.scripts.gfw_annotations import GFWClient, _normalize_response_entries


@pytest.fixture
def mock_gfw_client():
    """Create a GFW client with mocked HTTP requests."""
    with patch("research.scripts.gfw_annotations._request_with_retry") as mock_req:
        client = GFWClient("test_token_12345")  # noqa: S105
        yield client, mock_req


def test_gfw_client_initialization():
    """Test that GFW client initializes with required headers."""
    client = GFWClient("test_token")
    assert client.api_token == "test_token"  # noqa: S105
    assert "Authorization" in client.headers
    assert client.headers["Authorization"] == "Bearer test_token"


def test_gfw_get_ais_presence_success(mock_gfw_client):
    """Test successful AIS Vessel Presence retrieval (Level 1 annotation seeds)."""
    client, mock_req = mock_gfw_client

    mock_req.return_value = {
        "entries": [
            {"lat": 33.0, "lon": -9.0, "mmsi": "123456789", "timestamp": "2024-01-01T12:00:00Z"},
            {"lat": 33.5, "lon": -9.5, "mmsi": "987654321", "timestamp": "2024-01-01T12:30:00Z"},
        ]
    }

    bbox = [-10.0, 32.0, -8.0, 34.0]
    results = client.gfw_get_ais_presence(bbox, "2024-01-01", "2024-01-02", limit=500)

    assert len(results) == 2
    assert results[0]["lat"] == 33.0
    assert results[0]["lon"] == -9.0
    assert results[0]["mmsi"] == "123456789"
    # Verify annotation seed contract
    assert results[0]["source"] == "ais_presence_amorce"
    assert results[0]["requires_human_validation"] is True
    mock_req.assert_called()


def test_gfw_get_ais_presence_empty_response(mock_gfw_client):
    """Test handling of empty AIS Vessel Presence response."""
    client, mock_req = mock_gfw_client

    mock_req.return_value = {"entries": []}

    bbox = [-10.0, 32.0, -8.0, 34.0]
    results = client.gfw_get_ais_presence(bbox, "2024-01-01", "2024-01-02", limit=500)

    assert len(results) == 0


def test_gfw_get_ais_presence_normalized_output(mock_gfw_client):
    """Test that AIS presence entries are normalized to the contract format."""
    client, mock_req = mock_gfw_client

    mock_req.return_value = {
        "entries": [
            {
                "lat": 35.0,
                "lon": -5.0,
                "MMSI": "111222333",
                "vessel_name": "TEST VESSEL",
                "vessel_type": "fishing",
            },
        ]
    }

    bbox = [-6.0, 34.0, -4.0, 36.0]
    results = client.gfw_get_ais_presence(bbox, "2024-01-01", "2024-01-02", limit=500)

    assert len(results) == 1
    entry = results[0]
    assert entry["lat"] == 35.0
    assert entry["lon"] == -5.0
    assert entry["mmsi"] == "111222333"
    assert entry["vessel_name"] == "TEST VESSEL"
    assert entry["source"] == "ais_presence_amorce"
    assert entry["requires_human_validation"] is True


def test_gfw_get_ais_presence_api_failure(mock_gfw_client):
    """Test graceful degradation when AIS Presence API call fails."""
    client, mock_req = mock_gfw_client

    mock_req.side_effect = RuntimeError("API timeout")

    bbox = [-10.0, 32.0, -8.0, 34.0]
    results = client.gfw_get_ais_presence(bbox, "2024-01-01", "2024-01-02", limit=500)

    # Should return empty list on error, not crash
    assert len(results) == 0


def test_get_dark_vessel_events(mock_gfw_client):
    """Test dark vessel events retrieval (Level 2)."""
    client, mock_req = mock_gfw_client

    mock_req.return_value = {
        "entries": [
            {"position": {"lat": 34.0, "lon": -8.0}, "timestamp_off": "2024-01-01T12:00:00Z"},
        ]
    }

    bbox = [-10.0, 32.0, -8.0, 34.0]
    results = client.get_dark_vessel_events(bbox, "2024-01-01", "2024-01-02", limit=200)

    assert len(results) == 1
    assert results[0]["position"]["lat"] == 34.0


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

    # Test with unrecognized format (non-dict items in list)
    assert len(_normalize_response_entries({"unknown": [1, 2]})) == 0

    # Test with grouped format {dataset_key: [entries]} — top-level
    grouped = {
        "public-global-presence:v4.0": [
            {"lat": 33.0, "lon": -9.0, "mmsi": "123"},
            {"lat": 34.0, "lon": -8.0, "mmsi": "456"},
        ]
    }
    assert len(_normalize_response_entries(grouped)) == 2
    assert _normalize_response_entries(grouped)[0]["mmsi"] == "123"

    # Test with nested grouped format (actual 4wings/report response)
    # entries = [{dataset_key: [entry, ...]}, ...]
    nested_grouped = {
        "entries": [
            {
                "public-global-presence:v4.0": [
                    {"lat": 33.0, "lon": -9.0, "mmsi": "123", "shipName": "HELENA"},
                    {"lat": 34.0, "lon": -8.0, "mmsi": "456", "shipName": "BOATY"},
                ]
            }
        ]
    }
    result = _normalize_response_entries(nested_grouped)
    assert len(result) == 2
    assert result[0]["mmsi"] == "123"
    assert result[1]["shipName"] == "BOATY"

    # Test with standard format (unchanged)
    standard = {"entries": [{"id": 1}, {"id": 2}]}
    assert len(_normalize_response_entries(standard)) == 2

    # Test with multiple dataset keys
    multi_grouped = {
        "public-global-presence:v4.0": [{"lat": 33.0, "lon": -9.0}],
        "public-global-presence:v3.0": [{"lat": 34.0, "lon": -8.0}],
    }
    assert len(_normalize_response_entries(multi_grouped)) == 2


def test_search_vessels(mock_gfw_client):
    """Test vessel search functionality."""
    client, mock_req = mock_gfw_client

    mock_req.return_value = {"entries": [{"name": "Test Vessel", "id": "vessel123"}]}

    results = client.search_vessels("test query", limit=10)

    assert len(results) == 1
    assert results[0]["name"] == "Test Vessel"
    mock_req.assert_called_once()


def test_gfw_client_retry_logic():
    """Test that client implements retry logic for transient errors."""
    with (
        patch("research.scripts.gfw_annotations.time.sleep") as mock_sleep,
        patch("research.scripts.gfw_annotations.httpx.Client") as mock_client,
    ):
        mock_client_instance = MagicMock()
        mock_client.return_value.__enter__.return_value = mock_client_instance

        from httpx import Response

        # Mock responses
        mock_response_500 = Response(status_code=500, request=MagicMock())
        mock_response_success = Response(
            status_code=200, request=MagicMock(), json={"entries": [{"lat": 33.0, "lon": -9.0}]}
        )
        # Use post.side_effect because _request_with_retry uses POST for AIS presence queries
        mock_client_instance.post.side_effect = [
            mock_response_500,
            mock_response_500,
            mock_response_success,
        ]

        client = GFWClient("test_token")
        results = client.gfw_get_ais_presence(
            [-10.0, 32.0, -8.0, 34.0], "2024-01-01", "2024-01-02", limit=500
        )

        # Should succeed after retries
        assert len(results) == 1
        assert mock_client_instance.post.call_count == 3  # 2 failures + 1 success
        assert mock_sleep.call_count == 2  # 2 backoff sleeps


def test_get_ais_vessels_compatibility(mock_gfw_client):
    """Test that get_ais_vessels (legacy) still works."""
    client, mock_req = mock_gfw_client

    mock_req.return_value = {
        "entries": [
            {"lat": 33.0, "lon": -9.0, "mmsi": "123456789"},
        ]
    }

    bbox = [-10.0, 32.0, -8.0, 34.0]
    results = client.get_ais_vessels(bbox, "2024-01-01T12:00:00Z", window_hours=1.0)

    assert len(results) == 1
    assert results[0]["lat"] == 33.0


def test_gfw_get_ais_presence_query_param_contract(mock_gfw_client):
    """Lock the GFW /4wings/report param split (query vs body) — engineering contract.

    Does NOT assert HIGH vs LOW spatial-resolution (scientific arbitration pending).
    Asserts datasets[0], date-range, spatial-resolution, temporal-resolution, format
    are query params; geojson and limit are body params.
    """
    client, mock_req = mock_gfw_client
    mock_req.return_value = {"entries": []}

    client.gfw_get_ais_presence([-10.0, 32.0, -8.0, 34.0], "2024-01-01", "2024-01-02", limit=50)

    assert mock_req.called
    args = mock_req.call_args.args
    call_kwargs = mock_req.call_args.kwargs
    assert args[0] == "POST"
    assert args[1].endswith("/4wings/report")
    params = call_kwargs["params"]
    body = call_kwargs["json_body"]
    assert params["datasets[0]"] == "public-global-presence:latest"
    assert params["date-range"] == "2024-01-01,2024-01-02"
    assert "spatial-resolution" in params
    # HIGH vs LOW is a scientific arbitration (Partie 1) — only lock presence + valid value.
    assert params["spatial-resolution"] in ("LOW", "HIGH")
    assert "temporal-resolution" in params
    assert params["format"] == "JSON"
    assert "geojson" in body
    assert body["limit"] == 50
    assert "datasets[0]" not in body
    assert "date-range" not in body
