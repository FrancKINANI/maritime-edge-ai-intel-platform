# services/data_ingestor/sentinel_fetcher.py
"""Sentinel-1 SAFE Product Fetcher.

Helper interface containing download and API query functions to fetch files from Copernicus.
"""

import os
from typing import Any

from research.scripts.download_scenes import (
    download_product,
    get_cdse_token,
    search_sentinel1_products,
)


def search_cdse_odata(
    bbox: list[float],
    date_start: str,
    date_end: str,
    username: str | None = None,
    password: str | None = None,
) -> list[dict[str, Any]]:
    """Runs OData query on CDSE catalog by leveraging research implementation.

    Requires CDSE credentials provided either as arguments or via environment variables.
    """
    if username is None or password is None:
        username = os.getenv("CDSE_USERNAME")
        password = os.getenv("CDSE_PASSWORD")
    if not username or not password:
        raise ValueError("CDSE credentials must be provided via args or environment variables")
    token, expiry = get_cdse_token(username, password)
    return search_sentinel1_products(token, bbox, date_start, date_end)


def download_safe_product(
    product_id: str, download_path: str, username: str | None = None, password: str | None = None
) -> str:
    """Downloads a Sentinel-1 product using CDSE zipper via research helper.

    Returns the path to the extracted .SAFE directory.
    """
    if username is None or password is None:
        username = os.getenv("CDSE_USERNAME")
        password = os.getenv("CDSE_PASSWORD")
    if not username or not password:
        raise ValueError("CDSE credentials must be provided via args or environment variables")
    token, expiry = get_cdse_token(username, password)
    # product_id is the CDSE UUID; use product_id as name when product_name unknown
    return download_product(
        token, product_id, product_id, download_path, expiry, username, password
    )
