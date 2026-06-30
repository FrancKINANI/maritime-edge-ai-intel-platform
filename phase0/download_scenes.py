"""CDSE Sentinel-1 Product Downloader.

Purpose:
    Programmatically discover and download Sentinel-1 Ground Range Detected (GRD)
    Interferometric Wide (IW) swath mode products from the Copernicus Data Space Ecosystem (CDSE).

Inputs:
    Environment variables: CDSE_USERNAME, CDSE_PASSWORD
    Query parameters: bounding box, date range

Outputs:
    Downloaded and extracted .SAFE folders in phase0/data/scenes/
    manifest.json with scene metadata

This module implements OData API interactions with CDSE, Keycloak authentication,
robust streaming downloads with automatic ZIP extraction, and intelligent scene selection.
"""

import os
import zipfile
import logging
import json
import random
import time
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

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
CDSE_DOWNLOAD_URL = "https://zipper.dataspace.copernicus.eu/odata/v1/Products"
TOKEN_EXPIRY_SECONDS = 600  # CDSE tokens expire after 10 minutes

# Scene selection criteria for diverse dataset
SELECTION_CRITERIA = [
    # Zone Z1 — Eaux territoriales (côte atlantique marocaine)
    {"date_start": "2024-01-01", "date_end": "2024-03-31", "count": 2, "zone": "Z1"},
    # Zone Z2 — ZEE (large)
    {"date_start": "2024-04-01", "date_end": "2024-06-30", "count": 2, "zone": "Z2"},
    # Zone Z3 — Haute mer + détroit de Gibraltar
    {"date_start": "2024-07-01", "date_end": "2024-09-30", "count": 3, "zone": "Z3"},
    # Conditions variées — automne/hiver (mer plus agitée)
    {"date_start": "2024-10-01", "date_end": "2024-12-31", "count": 3, "zone": "Z4"},
]

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # Exponential backoff multiplier


def retry_with_backoff(func):
    """Decorator for retrying HTTP requests with exponential backoff."""
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                last_exception = e
                wait_time = RETRY_BACKOFF ** attempt
                logger.warning(f"Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
        raise last_exception
    return wrapper


def get_cdse_token(username: str, password: str) -> Tuple[str, float]:
    """Authenticates with the CDSE Keycloak service to retrieve an access token.

    Args:
        username (str): CDSE account email address.
        password (str): CDSE account password.

    Returns:
        Tuple[str, float]: OAuth2 Bearer token string and expiry timestamp.

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
    
    @retry_with_backoff
    def _request_token():
        with httpx.Client() as client:
            response = client.post(CDSE_TOKEN_URL, data=data, timeout=30.0)
            response.raise_for_status()
            return response.json()
    
    response_data = _request_token()
    token = response_data.get("access_token")
    if not token:
        raise RuntimeError("Authentication succeeded but no access_token was returned.")
    
    expiry_time = time.time() + TOKEN_EXPIRY_SECONDS
    logger.info("Authentication successful. Token expires in 10 minutes.")
    return token, expiry_time


def refresh_token_if_needed(token: str, expiry_time: float, username: str, password: str) -> Tuple[str, float]:
    """Refreshes the CDSE token if it's about to expire.

    Args:
        token (str): Current bearer token.
        expiry_time (float): Token expiry timestamp.
        username (str): CDSE username.
        password (str): CDSE password.

    Returns:
        Tuple[str, float]: New token and expiry time.
    """
    if time.time() > expiry_time - 60:  # Refresh 1 minute before expiry
        logger.info("Token expired or about to expire. Refreshing...")
        return get_cdse_token(username, password)
    return token, expiry_time


def search_sentinel1_products(
    token: str,
    bbox: List[float],
    date_start: str,
    date_end: str,
    max_results: int = 50,
    prefer_cog: bool = True
) -> List[Dict[str, Any]]:
    """Queries the CDSE OData API for Sentinel-1 GRD products matching parameters.

    Args:
        token (str): Bearer authentication token.
        bbox (List[float]): Geographic bounding box coordinates: [lon_min, lat_min, lon_max, lat_max].
        date_start (str): Start date string (ISO8601, e.g., '2024-01-01').
        date_end (str): End date string (ISO8601, e.g., '2024-03-31').
        max_results (int): Maximum number of products to return.
        prefer_cog (bool): If True, prefer COG variants and filter out non-COG duplicates.

    Returns:
        List[Dict[str, Any]]: List of matching Sentinel-1 product metadata dictionaries.

    Raises:
        httpx.HTTPStatusError: If the OData API query fails.
    """
    logger.info(f"Searching Sentinel-1 products from {date_start} to {date_end} in bbox {bbox}...")
    lon_min, lat_min, lon_max, lat_max = bbox
    polygon = f"POLYGON(({lon_min} {lat_min}, {lon_max} {lat_min}, {lon_max} {lat_max}, {lon_min} {lat_max}, {lon_min} {lat_min}))"
    
    # Enhanced OData filter with productType specification
    filter_query = (
        f"Collection/Name eq 'SENTINEL-1' and "
        f"Attributes/OData.CSC.StringAttribute/any(att: att/Name eq 'productType' and att/OData.CSC.StringAttribute/Value eq 'IW_GRDH_1S') and "
        f"OData.CSC.Intersects(area=geography'SRID=4326;{polygon}') and "
        f"ContentDate/Start ge {date_start}T00:00:00.000Z and "
        f"ContentDate/Start le {date_end}T23:59:59.000Z"
    )

    params = {
        "$filter": filter_query,
        "$top": max_results,
        "$orderby": "ContentDate/Start desc"
    }

    headers = {"Authorization": f"Bearer {token}"}
    
    @retry_with_backoff
    def _search_request():
        with httpx.Client() as client:
            query_string = urllib.parse.urlencode(params, safe="$,'")
            url = f"{CDSE_ODATA_URL}?{query_string}"
            response = client.get(url, headers=headers, timeout=60.0)
            response.raise_for_status()
            return response.json()
    
    response_data = _search_request()
    results = response_data.get("value", [])
    
    # Extract and normalize metadata
    normalized_results = []
    for product in results:
        normalized_results.append({
            "id": product.get("Id"),
            "name": product.get("Name"),
            "date": product.get("ContentDate", {}).get("Start"),
            "size": product.get("ContentLength", 0),
            "footprint": product.get("ContentGeometry", ""),
        })
    
    # Filter for COG variants if requested
    if prefer_cog:
        logger.info("Filtering for COG variants and removing duplicates...")
        cog_results = []
        product_groups = {}  # Group by base identifier
        
        for product in normalized_results:
            name = product["name"]
            # Extract base identifier (timestamp and mission info)
            # Format: S1A_IW_GRDH_1SDV_YYYYMMDDTHHMMSS_YYYYMMDDTHHMMSS_...
            parts = name.split("_")
            if len(parts) >= 8:
                # Base identifier includes mission, mode, polarization, and timestamp
                base_id = "_".join(parts[:7])  # S1A_IW_GRDH_1SDV_20240107T064657_20240107T064719
            else:
                base_id = name
            
            # Group products by base identifier
            if base_id not in product_groups:
                product_groups[base_id] = []
            product_groups[base_id].append(product)
        
        # For each group, prefer COG variant, otherwise keep standard
        for base_id, group in product_groups.items():
            # Check for COG variant
            cog_variants = [p for p in group if "_COG" in p["name"] or p["name"].endswith("_COG.SAFE")]
            
            if cog_variants:
                # Use COG variant
                cog_results.extend(cog_variants)
                logger.debug(f"Using COG variant for {base_id}")
            else:
                # Use standard variant (first one)
                cog_results.append(group[0])
                logger.debug(f"Using standard variant for {base_id}")
        
        logger.info(f"Filtered to {len(cog_results)} products (COG preferred, duplicates removed)")
        normalized_results = cog_results
    
    logger.info(f"Found {len(normalized_results)} matching Sentinel-1 products.")
    return normalized_results


def download_product(
    token: str,
    product_id: str,
    product_name: str,
    output_dir: str,
    expiry_time: float,
    username: str,
    password: str
) -> str:
    """Downloads and extracts a Sentinel-1 SAFE product from CDSE.

    Streams the download to disk to handle massive file sizes safely, then extracts
    the ZIP archive, and deletes the temporary ZIP file.

    Args:
        token (str): Bearer authentication token.
        product_id (str): Unique CDSE UUID of the Sentinel-1 product.
        product_name (str): Product name for naming the output file.
        output_dir (str): Directory where the .SAFE directory should be placed.
        expiry_time (float): Token expiry timestamp.
        username (str): CDSE username for token refresh.
        password (str): CDSE password for token refresh.

    Returns:
        str: Path to the extracted .SAFE directory.

    Raises:
        httpx.HTTPStatusError: If the download fails.
        zipfile.BadZipFile: If the downloaded archive is corrupted.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Refresh token if needed
    token, expiry_time = refresh_token_if_needed(token, expiry_time, username, password)
    
    url = f"{CDSE_DOWNLOAD_URL}({product_id})/$value"
    headers = {"Authorization": f"Bearer {token}"}
    zip_path = output_path / f"{product_name}.zip"
    
    logger.info(f"Starting download for product {product_name}...")
    
    @retry_with_backoff
    def _download_request():
        with httpx.Client() as client:
            response = client.get(url, headers=headers, timeout=120.0, follow_redirects=True)
            response.raise_for_status()
            return response
    
    response = _download_request()
    total_size = int(response.headers.get("Content-Length", 0))
    
    # Stream download with 8192 byte chunks
    with open(zip_path, "wb") as f, tqdm(
        total=total_size, unit="B", unit_scale=True, desc=product_name[:20]
    ) as progress:
        for chunk in response.iter_bytes(chunk_size=8192):
            f.write(chunk)
            progress.update(len(chunk))
                    
    logger.info(f"Download complete: {zip_path}. Extracting archive...")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(output_path)
            # Find the .SAFE directory name
            safe_dirs = [name for name in zip_ref.namelist() if name.endswith(".SAFE/")]
            safe_dir_name = safe_dirs[0].rstrip("/") if safe_dirs else None
    except zipfile.BadZipFile as e:
        logger.error(f"Corrupted ZIP file: {e}")
        zip_path.unlink()
        raise
    
    # Cleanup zip
    zip_path.unlink()
    
    if safe_dir_name:
        safe_path = output_path / safe_dir_name
        logger.info(f"Extraction complete and ZIP removed. Saved to {safe_path}")
        return str(safe_path)
    else:
        logger.warning("No .SAFE directory found in the extracted zip.")
        return str(output_path)


def is_scene_downloaded(scenes_dir: Path, product_name: str) -> bool:
    """Checks if a scene has already been downloaded.

    Args:
        scenes_dir (Path): Directory containing .SAFE folders.
        product_name (str): Product name to check.

    Returns:
        bool: True if scene exists, False otherwise.
    """
    safe_path = scenes_dir / f"{product_name}.SAFE"
    return safe_path.exists() and safe_path.is_dir()


def select_scenes_for_criteria(
    token: str,
    bbox: List[float],
    criteria: Dict[str, Any],
    username: str,
    password: str
) -> List[Dict[str, Any]]:
    """Selects scenes for a specific criterion with random sampling.

    Args:
        token (str): CDSE authentication token.
        bbox (List[float]): Geographic bounding box.
        criteria (Dict[str, Any]): Selection criterion dict.
        username (str): CDSE username.
        password (str): CDSE password.

    Returns:
        List[Dict[str, Any]]: Selected scene metadata.
    """
    date_start = criteria["date_start"]
    date_end = criteria["date_end"]
    count = criteria["count"]
    zone = criteria["zone"]
    
    logger.info(f"Searching scenes for {zone} ({date_start} to {date_end})...")
    
    products = search_sentinel1_products(token, bbox, date_start, date_end, max_results=50, prefer_cog=True)
    
    if not products:
        logger.warning(f"No products found for {zone}")
        return []
    
    # Random selection from available products
    if len(products) > count:
        selected = random.sample(products, count)
    else:
        selected = products
        logger.warning(f"Only {len(products)} products available for {zone}, requested {count}")
    
    # Add zone information to metadata
    for product in selected:
        product["zone"] = zone
    
    logger.info(f"Selected {len(selected)} scenes for {zone}")
    return selected


def save_manifest(scenes_dir: Path, manifest: Dict[str, Any]) -> None:
    """Saves the download manifest to a JSON file.

    Args:
        scenes_dir (Path): Directory containing scenes.
        manifest (Dict[str, Any]): Manifest data to save.
    """
    manifest_path = scenes_dir / "manifest.json"
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    logger.info(f"Manifest saved to {manifest_path}")


def test_connection() -> None:
    """Tests CDSE connection and API functionality.

    Verifies that:
    - Token can be obtained
    - Search returns results for Moroccan bbox
    - First 3 products are displayed with metadata
    """
    logger.info("=== CDSE Connection Test ===")
    
    load_dotenv()
    username = os.getenv("CDSE_USERNAME")
    password = os.getenv("CDSE_PASSWORD")
    
    if not username or not password:
        logger.error("CDSE_USERNAME and CDSE_PASSWORD must be set in .env file.")
        return
    
    try:
        # Test authentication
        logger.info("Testing authentication...")
        token, _ = get_cdse_token(username, password)
        logger.info("✓ Authentication successful")
        
        # Test search
        logger.info("Testing product search with COG filtering...")
        bbox = [-17.0, 27.0, -1.0, 36.0]  # Morocco bbox
        products = search_sentinel1_products(token, bbox, "2024-01-01", "2024-01-31", max_results=10, prefer_cog=True)
        
        if products:
            logger.info(f"✓ Search successful - found {len(products)} products")
            logger.info("First 3 products:")
            for i, product in enumerate(products[:3], 1):
                is_cog = "COG" in product['name']
                cog_status = " [COG]" if is_cog else " [Standard]"
                logger.info(f"  {i}. {product['name']}{cog_status}")
                logger.info(f"     Date: {product['date']}")
                logger.info(f"     Size: {product['size'] / (1024**3):.2f} GB")
        else:
            logger.warning("✓ Search successful but no products found")
        
        logger.info("=== All tests passed ===")
        
    except Exception as e:
        logger.error(f"✗ Test failed: {e}")


def main() -> None:
    """Main orchestration for downloading diverse scene dataset."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Download diverse Sentinel-1 scenes for Phase 0")
    parser.add_argument("--test", action="store_true", help="Run connection test only")
    parser.add_argument("--max-scenes", type=int, default=10, help="Maximum number of scenes to download")
    args = parser.parse_args()
    
    if args.test:
        test_connection()
        return
    
    load_dotenv()
    
    username = os.getenv("CDSE_USERNAME")
    password = os.getenv("CDSE_PASSWORD")
    
    if not username or not password:
        logger.error("CDSE_USERNAME and CDSE_PASSWORD must be set in the environment or .env file.")
        return

    # Configuration
    bbox = [-17.0, 27.0, -1.0, 36.0]  # Morocco bounding box
    scenes_dir = Path(__file__).parent / "data" / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    
    # Get initial token
    token, expiry_time = get_cdse_token(username, password)
    
    # Select scenes based on criteria
    all_selected_scenes = []
    for criteria in SELECTION_CRITERIA:
        selected = select_scenes_for_criteria(token, bbox, criteria, username, password)
        all_selected_scenes.extend(selected)
    
    # Limit to max scenes if specified
    if len(all_selected_scenes) > args.max_scenes:
        all_selected_scenes = all_selected_scenes[:args.max_scenes]
        logger.info(f"Limited selection to {args.max_scenes} scenes")
    
    logger.info(f"Total scenes selected: {len(all_selected_scenes)}")
    
    # Download scenes
    downloaded_scenes = []
    total_size = 0
    
    for product in all_selected_scenes:
        product_id = product["id"]
        product_name = product["name"]
        zone = product["zone"]
        
        logger.info(f"Processing: {product_name} ({zone})")
        
        # Check if already downloaded
        if is_scene_downloaded(scenes_dir, product_name):
            logger.info(f"  Scene already downloaded, skipping")
            downloaded_scenes.append({
                "name": product_name,
                "zone": zone,
                "date": product["date"],
                "size": product["size"],
                "status": "already_downloaded"
            })
            continue
        
        try:
            safe_path = download_product(
                token, product_id, product_name, str(scenes_dir),
                expiry_time, username, password
            )
            
            downloaded_scenes.append({
                "name": product_name,
                "zone": zone,
                "date": product["date"],
                "size": product["size"],
                "status": "downloaded",
                "path": safe_path
            })
            total_size += product["size"]
            
        except Exception as e:
            logger.error(f"  Failed to download {product_name}: {e}")
            downloaded_scenes.append({
                "name": product_name,
                "zone": zone,
                "date": product["date"],
                "size": product["size"],
                "status": "failed",
                "error": str(e)
            })
    
    # Generate summary
    successful = [s for s in downloaded_scenes if s["status"] in ["downloaded", "already_downloaded"]]
    failed = [s for s in downloaded_scenes if s["status"] == "failed"]
    
    logger.info("=" * 60)
    logger.info(f"✓ Scènes téléchargées : {len(successful)}/{len(all_selected_scenes)}")
    logger.info(f"  Dossier : {scenes_dir}")
    logger.info(f"  Taille totale : {total_size / (1024**3):.2f} GB")
    logger.info(f"  Réussis : {len([s for s in downloaded_scenes if s['status'] == 'downloaded'])}")
    logger.info(f"  Déjà présents : {len([s for s in downloaded_scenes if s['status'] == 'already_downloaded'])}")
    logger.info(f"  Échoués : {len(failed)}")
    
    if failed:
        logger.warning("Scènes échouées :")
        for scene in failed:
            logger.warning(f"  - {scene['name']} ({scene['zone']}) : {scene.get('error', 'Unknown error')}")
    
    logger.info("Liste des scènes :")
    for scene in downloaded_scenes:
        status_symbol = "✓" if scene["status"] != "failed" else "✗"
        logger.info(f"  {status_symbol} {scene['name']} ({scene['zone']})")
    
    # Save manifest
    manifest = {
        "download_date": datetime.now().isoformat(),
        "total_scenes": len(all_selected_scenes),
        "successful": len(successful),
        "failed": len(failed),
        "total_size_gb": total_size / (1024**3),
        "scenes": downloaded_scenes
    }
    save_manifest(scenes_dir, manifest)


if __name__ == "__main__":
    main()