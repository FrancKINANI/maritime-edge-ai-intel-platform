# phase0/download_scenes.py
"""CDSE Sentinel-1 Product Downloader.

Provides a skeleton interface for authenticating with the Copernicus Data Space Ecosystem (CDSE)
Keycloak service and performing OData searches and downloads of Sentinel-1 SAFE products.
"""

from typing import List, Dict, Any


def get_cdse_token(username: str, password: str) -> str:
    """Authenticates with the Keycloak service of the Copernicus Data Space Ecosystem (CDSE).

    Args:
        username (str): The CDSE account email address.
        password (str): The CDSE account password.

    Returns:
        str: OAuth2 Bearer token string.

    Raises:
        NotImplementedError: As this is a skeleton structure.
    """
    raise NotImplementedError("CDSE token authentication logic not implemented yet.")


def search_sentinel1_products(token: str, bbox: List[float], date_start: str, date_end: str) -> List[Dict[str, Any]]:
    """Queries the CDSE OData API for Sentinel-1 GRD products matching the query parameters.

    Args:
        token (str): Bearer authentication token.
        bbox (List[float]): Geographic bounding box coordinates: [lon_min, lat_min, lon_max, lat_max].
        date_start (str): Start date string (ISO8601).
        date_end (str): End date string (ISO8601).

    Returns:
        List[Dict[str, Any]]: List of matching Sentinel-1 product metadata dicts.

    Raises:
        NotImplementedError: As this is a skeleton structure.
    """
    raise NotImplementedError("CDSE OData search query logic not implemented yet.")


def download_product(token: str, product_id: str, output_dir: str) -> str:
    """Downloads the target Sentinel-1 SAFE product zip file from CDSE zipper service.

    Args:
        token (str): Bearer authentication token.
        product_id (str): Unique CDSE UUID of the Sentinel-1 product.
        output_dir (str): Directory where the zip/.SAFE file should be saved.

    Returns:
        str: Path to the downloaded and extracted .SAFE directory.

    Raises:
        NotImplementedError: As this is a skeleton structure.
    """
    raise NotImplementedError("CDSE downloader logic not implemented yet.")
