"""
test_main.py
------------
Unit tests for the Data Ingestor FastAPI service.

Tests coverage:
  - /health endpoint
  - /ingest endpoint (501 Not Implemented)
  - /status/{job_id} endpoint (501 Not Implemented)
  - /products endpoint (501 Not Implemented)
  - Request validation

NOTE: Uses importlib to load the module because the directory name
'data-ingestor' contains a hyphen (invalid for Python imports).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Load via importlib (hyphen-proof) — same pattern as test_aggregator_utils.py
_INGESTOR_MAIN = Path(__file__).resolve().parents[1] / "main.py"
_spec = importlib.util.spec_from_file_location("data_ingestor_main", _INGESTOR_MAIN)
_ingestor_main = importlib.util.module_from_spec(_spec)
sys.modules["data_ingestor_main"] = _ingestor_main
assert _spec.loader is not None
_spec.loader.exec_module(_ingestor_main)
app = _ingestor_main.app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_returns_healthy(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    def test_health_content_type(self, client):
        response = client.get("/health")
        assert response.headers["content-type"] == "application/json"


class TestIngestEndpoint:
    """Tests for the /ingest endpoint."""

    def test_ingest_returns_501(self, client):
        response = client.post(
            "/ingest",
            json={
                "bbox": [-10.0, 32.0, -8.0, 34.0],
                "date_start": "2024-01-01",
                "date_end": "2024-01-02",
            },
        )
        assert response.status_code == 501
        assert "not yet implemented" in response.json()["detail"].lower()

    def test_ingest_invalid_bbox(self, client):
        response = client.post(
            "/ingest",
            json={
                "bbox": [-10.0, 32.0],  # Only 2 values
                "date_start": "2024-01-01",
                "date_end": "2024-01-02",
            },
        )
        assert response.status_code == 422  # Validation error

    def test_ingest_missing_fields(self, client):
        response = client.post(
            "/ingest",
            json={"bbox": [-10.0, 32.0, -8.0, 34.0]},  # Missing dates
        )
        assert response.status_code == 422


class TestStatusEndpoint:
    """Tests for the /status/{job_id} endpoint."""

    def test_status_returns_501(self, client):
        response = client.get("/status/test-job-123")
        assert response.status_code == 501
        assert "not yet implemented" in response.json()["detail"].lower()


class TestProductsEndpoint:
    """Tests for the /products endpoint."""

    def test_products_returns_501(self, client):
        response = client.get(
            "/products",
            params={
                "bbox": "-10.0,32.0,-8.0,34.0",
                "date_start": "2024-01-01",
                "date_end": "2024-01-02",
            },
        )
        assert response.status_code == 501

    def test_products_missing_params(self, client):
        response = client.get("/products")
        assert response.status_code == 422
