"""
test_sentinel_fetcher.py
------------------------
Unit tests for the Sentinel-1 fetcher helper functions.

Tests cover:
  - Credential resolution (args vs env vars)
  - Error handling for missing credentials
  - Function signatures and type contracts

NOTE: Uses importlib to load the module because the directory name
'data-ingestor' contains a hyphen (invalid for Python imports).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Load via importlib (hyphen-proof)
_FETCHER_PATH = Path(__file__).resolve().parents[1] / "sentinel_fetcher.py"
_spec = importlib.util.spec_from_file_location("data_ingestor_fetcher", _FETCHER_PATH)
_fetcher_module = importlib.util.module_from_spec(_spec)
sys.modules["data_ingestor_fetcher"] = _fetcher_module
assert _spec.loader is not None
try:
    _spec.loader.exec_module(_fetcher_module)
except ModuleNotFoundError as exc:
    pytest.skip(f"data-ingestor deps unavailable: {exc}", allow_module_level=True)
search_cdse_odata = _fetcher_module.search_cdse_odata
download_safe_product = _fetcher_module.download_safe_product


class TestSearchCdseOdata:
    """Tests for search_cdse_odata function."""

    def test_missing_credentials_raises(self):
        """No credentials at all should raise ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="CDSE credentials"):
                search_cdse_odata(
                    bbox=[-10.0, 32.0, -8.0, 34.0],
                    date_start="2024-01-01",
                    date_end="2024-01-02",
                )

    def test_credentials_from_args(self):
        """Credentials passed as args should be used."""
        with patch("data_ingestor_fetcher.get_cdse_token") as mock_token, \
             patch("data_ingestor_fetcher.search_sentinel1_products") as mock_search:
            mock_token.return_value = ("fake_token", "2025-01-01T00:00:00")
            mock_search.return_value = []

            result = search_cdse_odata(
                bbox=[-10.0, 32.0, -8.0, 34.0],
                date_start="2024-01-01",
                date_end="2024-01-02",
                username="test_user",
                password="test_pass",
            )
            assert result == []
            mock_token.assert_called_once_with("test_user", "test_pass")

    def test_credentials_from_env(self):
        """Credentials from env vars should be used."""
        with patch.dict(os.environ, {"CDSE_USERNAME": "env_user", "CDSE_PASSWORD": "env_pass"}), \
             patch("data_ingestor_fetcher.get_cdse_token") as mock_token, \
             patch("data_ingestor_fetcher.search_sentinel1_products") as mock_search:
            mock_token.return_value = ("fake_token", "2025-01-01")
            mock_search.return_value = []

            result = search_cdse_odata(
                bbox=[-10.0, 32.0, -8.0, 34.0],
                date_start="2024-01-01",
                date_end="2024-01-02",
            )
            assert result == []
            mock_token.assert_called_once_with("env_user", "env_pass")


class TestDownloadSafeProduct:
    """Tests for download_safe_product function."""

    def test_missing_credentials_raises(self):
        """No credentials should raise ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="CDSE credentials"):
                download_safe_product(
                    product_id="test-product",
                    download_path="/tmp/downloads",
                )

    def test_credentials_from_args(self):
        """Credentials from args should be used."""
        with patch("data_ingestor_fetcher.get_cdse_token") as mock_token:
            mock_token.return_value = ("fake_token", "2025-01-01")

            with patch("data_ingestor_fetcher.download_product") as mock_dl:
                mock_dl.return_value = "/tmp/downloads/test.SAFE"

                result = download_safe_product(
                    product_id="test-uuid",
                    download_path="/tmp/downloads",
                    username="dl_user",
                    password="dl_pass",
                )
                assert result == "/tmp/downloads/test.SAFE"
                mock_token.assert_called_once_with("dl_user", "dl_pass")
