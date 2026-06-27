# services/data-ingestor/sentinel_fetcher.py
"""Sentinel-1 SAFE Product Fetcher.

Helper interface containing download and API query functions to fetch files from Copernicus.
"""

from typing import List, Dict, Any


def search_cdse_odata(bbox: List[float], date_start: str, date_end: str) -> List[Dict[str, Any]]:
    """Runs OData query on CDSE catalog.

    Args:
        bbox (List[float]): Bounding box coordinates.
        date_start (str): Ingestion start datetime.
        date_end (str): Ingestion end datetime.

    Returns:
        List[Dict[str, Any]]: Catalog products list.
    """
    raise NotImplementedError("CDSE OData search is not implemented.")


def download_safe_product(product_id: str, download_path: str) -> str:
    """Downloads zip product from CDSE zipper service and unpacks it.

    Args:
        product_id (str): Copernicus unique UUID.
        download_path (str): target saving folder.

    Returns:
        str: absolute path to unpacked SAFE product directory.
    """
    raise NotImplementedError("CDSE download is not implemented.")
