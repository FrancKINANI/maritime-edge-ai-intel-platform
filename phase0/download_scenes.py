"""CDSE Sentinel-1 Product Downloader.

Purpose:
    Programmatically discover and download Sentinel-1 Ground Range Detected (GRD)
    Interferometric Wide (IW) swath mode products from the Copernicus Data Space Ecosystem (CDSE).

Inputs:
    Environment variables: CDSE_USERNAME, CDSE_PASSWORD
    Query parameters: bounding box, date range

Outputs:
    Downloaded and extracted .SAFE folders in phase0/data/scenes/

This module implements OData API interactions with CDSE, Keycloak authentication,
and robust streaming downloads with automatic ZIP extraction.
"""

import os
import zipfile
import logging
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any

import httpx
from tqdm import tqdm
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"


def get_cdse_token(username: str, password: str) -> str:
    """Authenticates with the CDSE Keycloak service to retrieve an access token.

    Args:
        username (str): CDSE account email address.
        password (str): CDSE account password.

    Returns:
        str: OAuth2 Bearer token string.

    Raises:
        ValueError: If username or password is not provided.
        httpx.HTTPStatusError: If authentication fails (e.g., wrong credentials).
    """
    if not username or not password:
        raise ValueError("CDSE_USERNAME and CDSE_PASSWORD must be provided.")

    logger.info("Requesting authentication token from CDSE...")
    data = {
        "client_id": "cdse-public",
        "username": username,
        "password": password,
        "grant_type": "password",
    }
    
    with httpx.Client() as client:
        response = client.post(CDSE_TOKEN_URL, data=data, timeout=30.0)
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise RuntimeError("Authentication succeeded but no access_token was returned.")
        logger.info("Authentication successful.")
        return token


def search_sentinel1_products(token: str, bbox: List[float], date_start: str, date_end: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Queries the CDSE OData API for Sentinel-1 GRD products matching parameters.

    Args:
        token (str): Bearer authentication token.
        bbox (List[float]): Geographic bounding box coordinates: [lon_min, lat_min, lon_max, lat_max].
        date_start (str): Start date string (ISO8601, e.g., '2023-01-01T00:00:00.000Z').
        date_end (str): End date string (ISO8601, e.g., '2023-01-31T23:59:59.000Z').
        max_results (int): Maximum number of products to return.

    Returns:
        List[Dict[str, Any]]: List of matching Sentinel-1 product metadata dictionaries.

    Raises:
        httpx.HTTPStatusError: If the OData API query fails.
    """
    logger.info(f"Searching Sentinel-1 products from {date_start} to {date_end} in bbox {bbox}...")
    lon_min, lat_min, lon_max, lat_max = bbox
    polygon = f"POLYGON(({lon_min} {lat_min}, {lon_max} {lat_min}, {lon_max} {lat_max}, {lon_min} {lat_max}, {lon_min} {lat_min}))"
    
    # Using contains to ensure we get IW_GRDH products
    filter_query = (
        f"Collection/Name eq 'SENTINEL-1' and "
        f"contains(Name,'IW_GRDH') and "
        f"OData.CSC.Intersects(area=geography'SRID=4326;{polygon}') and "
        f"ContentDate/Start ge {date_start} and ContentDate/End le {date_end}"
    )

    params = {
        "$filter": filter_query,
        "$top": max_results,
        "$orderby": "ContentDate/Start desc"
    }

    headers = {"Authorization": f"Bearer {token}"}
    
    with httpx.Client() as client:
        # Encode parameters properly
        query_string = urllib.parse.urlencode(params, safe="$,'")
        url = f"{CDSE_ODATA_URL}?{query_string}"
        
        response = client.get(url, headers=headers, timeout=60.0)
        response.raise_for_status()
        results = response.json().get("value", [])
        
        logger.info(f"Found {len(results)} matching Sentinel-1 products.")
        return results


def download_product(token: str, product_id: str, output_dir: str) -> str:
    """Downloads and extracts a Sentinel-1 SAFE product from CDSE.

    Streams the download to disk to handle massive file sizes safely, then extracts
    the ZIP archive, and deletes the temporary ZIP file.

    Args:
        token (str): Bearer authentication token.
        product_id (str): Unique CDSE UUID of the Sentinel-1 product.
        output_dir (str): Directory where the .SAFE directory should be placed.

    Returns:
        str: Path to the extracted .SAFE directory.

    Raises:
        httpx.HTTPStatusError: If the download fails.
        zipfile.BadZipFile: If the downloaded archive is corrupted.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    url = f"{CDSE_ODATA_URL}({product_id})/$value"
    headers = {"Authorization": f"Bearer {token}"}
    zip_path = output_path / f"{product_id}.zip"
    
    logger.info(f"Starting download for product {product_id}...")
    
    with httpx.Client() as client:
        with client.stream("GET", url, headers=headers, follow_redirects=True, timeout=120.0) as response:
            response.raise_for_status()
            total_size = int(response.headers.get("Content-Length", 0))
            
            with open(zip_path, "wb") as f, tqdm(
                total=total_size, unit="B", unit_scale=True, desc=product_id[:8]
            ) as progress:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):  # 1MB chunks
                    f.write(chunk)
                    progress.update(len(chunk))
                    
    logger.info(f"Download complete: {zip_path}. Extracting archive...")
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(output_path)
        # Find the .SAFE directory name (should be the top-level directory in the zip)
        safe_dirs = [name for name in zip_ref.namelist() if name.endswith(".SAFE/")]
        safe_dir_name = safe_dirs[0] if safe_dirs else None
    
    # Cleanup zip
    zip_path.unlink()
    
    if safe_dir_name:
        logger.info(f"Extraction complete and ZIP removed. Saved to {output_path / safe_dir_name}")
        return str(output_path / safe_dir_name)
    else:
        logger.warning("No .SAFE directory found in the extracted zip.")
        return str(output_path)


def main():
    """Orchestration block for testing download_scenes.py standalone."""
    load_dotenv()
    
    username = os.getenv("CDSE_USERNAME")
    password = os.getenv("CDSE_PASSWORD")
    
    if not username or not password:
        logger.error("CDSE_USERNAME and CDSE_PASSWORD must be set in the environment or .env file.")
        return

    # Configuration for Moroccan waters validation (Zone Z1/Z2 example)
    bbox = [-17.0, 27.0, -1.0, 36.0]  # Morocco bounding box
    date_start = "2024-01-01T00:00:00.000Z"
    date_end = "2024-01-07T23:59:59.000Z"
    scenes_dir = Path(__file__).parent / "data" / "scenes"
    
    try:
        token = get_cdse_token(username, password)
        products = search_sentinel1_products(token, bbox, date_start, date_end, max_results=2)
        
        for product in products:
            product_id = product["Id"]
            product_name = product["Name"]
            logger.info(f"Processing product: {product_name} ({product_id})")
            
            # Check if already downloaded
            expected_safe_dir = scenes_dir / f"{product_name}.SAFE"
            if expected_safe_dir.exists():
                logger.info(f"Product already exists at {expected_safe_dir}, skipping download.")
                continue
                
            download_product(token, product_id, str(scenes_dir))
            
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
