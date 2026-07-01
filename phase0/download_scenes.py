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
import httpx
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

# Scene selection criteria for Morocco 2025 only
# The dataset should cover Moroccan waters across all four quarters.
MOROCCO_BBOX = [-17, 27, -1, 36]  # [lon_min, lat_min, lon_max, lat_max]

SELECTION_CRITERIA = [
    {
        "bbox": MOROCCO_BBOX,
        "date_start": "2025-01-01",
        "date_end": "2025-03-31",
        "count": 3,
        "label": "Morocco_Q1_winter",
        "season": "Morocco Q1 Winter"
    },
    {
        "bbox": MOROCCO_BBOX,
        "date_start": "2025-04-01",
        "date_end": "2025-06-30",
        "count": 3,
        "label": "Morocco_Q2_spring",
        "season": "Morocco Q2 Spring"
    },
    {
        "bbox": MOROCCO_BBOX,
        "date_start": "2025-07-01",
        "date_end": "2025-09-30",
        "count": 3,
        "label": "Morocco_Q3_summer",
        "season": "Morocco Q3 Summer"
    },
    {
        "bbox": MOROCCO_BBOX,
        "date_start": "2025-10-01",
        "date_end": "2025-12-31",
        "count": 3,
        "label": "Morocco_Q4_autumn",
        "season": "Morocco Q4 Autumn"
    },
]
# Total target: 12 Morocco 2025 scenes only
# (replaces previous mixed-region selection)

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
            # Debug: list the contents of the zip
            logger.info(f"ZIP contains {len(zip_ref.namelist())} files. First 10: {zip_ref.namelist()[:10]}")
            
            zip_ref.extractall(output_path)
            
            # Find the .SAFE directory name (should be the top-level directory in the zip)
            safe_dirs = [name for name in zip_ref.namelist() if name.endswith(".SAFE/")]
            safe_dir_name = safe_dirs[0].rstrip("/") if safe_dirs else None
            
            # If no .SAFE/ directory found, check for .SAFE without trailing slash
            if not safe_dir_name:
                safe_dirs = [name for name in zip_ref.namelist() if name.endswith(".SAFE")]
                safe_dir_name = safe_dirs[0] if safe_dirs else None
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
        # List what was actually extracted
        extracted_files = list(output_path.iterdir())
        logger.warning(f"Extracted files: {[f.name for f in extracted_files]}")
        return str(output_path)


def get_scene_base_id(product_name: str) -> Optional[str]:
    """Extracts a stable base identifier for a Sentinel-1 scene name.

    The CDSE catalogue can return both standard and COG variants of the same
    product. We treat them as the same scene by using the orbit/mission suffix.
    """
    normalized_name = product_name.rstrip("/").replace(".SAFE", "")
    parts = normalized_name.split("_")

    if len(parts) >= 7:
        if parts[-1].upper() == "COG":
            return f"{parts[-4]}_{parts[-3]}_{parts[-2]}"
        return f"{parts[-3]}_{parts[-2]}_{parts[-1]}"

    return None


def is_scene_downloaded(
    scenes_dir: Path,
    product_name: str,
    existing_scene_ids: Optional[set] = None,
) -> bool:
    """Checks if a scene has already been downloaded.

    Args:
        scenes_dir (Path): Directory containing .SAFE folders.
        product_name (str): Product name to check.
        existing_scene_ids (Optional[set]): Known scene IDs to avoid duplicates.

    Returns:
        bool: True if scene exists, False otherwise.
    """
    base_id = get_scene_base_id(product_name)
    if existing_scene_ids is not None and base_id and base_id in existing_scene_ids:
        return True

    safe_path = scenes_dir / f"{product_name}.SAFE"
    return safe_path.exists() and safe_path.is_dir()


def get_existing_scene_ids(scenes_dir: Path) -> set:
    """Gets set of existing scene product IDs (base IDs without COG suffix).
    
    This helps avoid downloading duplicate scenes across different regions
    when a scene might overlap multiple bounding boxes.
    
    Args:
        scenes_dir (Path): Directory containing .SAFE folders.
    
    Returns:
        set: Set of base product IDs (without COG suffix).
    """
    existing_ids = set()
    
    for safe_dir in scenes_dir.glob("*.SAFE"):
        if safe_dir.is_dir():
            base_id = get_scene_base_id(safe_dir.stem)
            if base_id:
                existing_ids.add(base_id)
    
    logger.info(f"Found {len(existing_ids)} existing scene IDs in {scenes_dir}")
    return existing_ids


def select_scenes_for_criteria(
    token: str,
    bbox: List[float],
    criteria: Dict[str, Any],
    username: str,
    password: str,
    existing_scene_ids: Optional[set] = None,
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
    season = criteria["season"]
    label = criteria.get("label", season)
    
    logger.info(f"Searching scenes for {label} ({date_start} to {date_end})...")
    
    products = search_sentinel1_products(token, bbox, date_start, date_end, max_results=60, prefer_cog=True)
    
    if not products:
        logger.warning(f"No products found for {season}")
        return []

    filtered_products = []
    seen_base_ids = set()
    for product in products:
        base_id = get_scene_base_id(product.get("name", ""))
        if base_id and (base_id in seen_base_ids or (existing_scene_ids is not None and base_id in existing_scene_ids)):
            continue
        if base_id:
            seen_base_ids.add(base_id)
        filtered_products.append(product)

    if not filtered_products:
        logger.info(f"All products for {season} were already downloaded or duplicated")
        return []
    
    # Random selection from available products
    if len(filtered_products) > count:
        selected = random.sample(filtered_products, count)
    else:
        selected = filtered_products
        logger.warning(f"Only {len(filtered_products)} products available for {season}, requested {count}")
    
# Add selection metadata to each product
    for product in selected:
        product["season"] = season
        product["label"] = label
        product["bbox_used"] = bbox
        product["date_range"] = f"{date_start}/{date_end}"

    logger.info(f"Selected {len(selected)} scenes for {label}")
    return selected


def deduplicate_scenes(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keeps only the first occurrence of each scene, deduped by base ID.

    This helps avoid duplicate manifest entries when the same product is seen
    multiple times across regions or repeated runs.
    """
    seen_ids = set()
    deduped = []

    for record in records:
        name = record.get("name") or record.get("product_name") or ""
        base_id = get_scene_base_id(name)
        key = base_id or name
        if key and key in seen_ids:
            continue
        if key:
            seen_ids.add(key)
        deduped.append(record)

    return deduped


def save_manifest(scenes_dir: Path, manifest: Dict[str, Any]) -> None:
    """Saves the download manifest to a JSON file.

    Args:
        scenes_dir (Path): Directory containing scenes.
        manifest (Dict[str, Any]): Manifest data to save.
    """
    manifest_path = scenes_dir / "manifest.json"
    if "scenes" in manifest:
        manifest["scenes"] = deduplicate_scenes(manifest["scenes"])
    if "regions" in manifest:
        for region in manifest["regions"].values():
            if isinstance(region, dict) and "scenes" in region:
                region["scenes"] = deduplicate_scenes(region["scenes"])
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    logger.info(f"Manifest saved to {manifest_path}")


def clean_non_morocco_scenes(scenes_dir: Path) -> None:
    """
    Identifies and archives scenes not labelled as Morocco in the manifest.

    For each manifest entry without a label starting with "Morocco_":
      - move the .SAFE folder to scenes/archive/
      - remove the manifest entry
    """
    archive_dir = scenes_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = scenes_dir / "manifest.json"
    if not manifest_path.exists():
        logger.warning("No manifest found at %s", manifest_path)
        return

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    scenes = manifest.get("scenes", [])
    remaining_scenes = []
    archived_count = 0

    for scene in scenes:
        label = scene.get("label", "")
        if isinstance(label, str) and label.startswith("Morocco_"):
            remaining_scenes.append(scene)
            continue

        safe_path_str = scene.get("safe_path") or scene.get("path")
        if not safe_path_str:
            logger.warning("Skipping non-Morocco scene without safe_path: %s", scene.get("name"))
            continue

        safe_path = Path(safe_path_str)
        if safe_path.exists():
            destination = archive_dir / safe_path.name
            try:
                safe_path.rename(destination)
                logger.info("Archived non-Morocco scene %s -> %s", safe_path, destination)
                archived_count += 1
            except OSError as e:
                logger.error("Failed to archive %s: %s", safe_path, e)
                remaining_scenes.append(scene)
        else:
            logger.warning("SAFE path does not exist for scene %s: %s", scene.get("name"), safe_path)

    manifest["scenes"] = remaining_scenes
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    logger.info("Archived %s non-Morocco scenes and updated manifest", archived_count)


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
        bbox_str = os.getenv("REGION_BBOX", "-17,27,-1,36")
        bbox = [float(x) for x in bbox_str.split(",")]
        region_name = os.getenv("REGION_NAME", "Unknown Region")
        
        logger.info(f"Testing for region: {region_name}")
        logger.info(f"Bounding box: {bbox}")
        
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


def download_multi_region(
    token: str,
    username: str,
    password: str,
    scenes_dir: Path,
    max_scenes_per_region: int = 3
) -> Dict[str, Any]:
    """Downloads scenes from multiple regions defined in .env.
    
    Args:
        token: CDSE authentication token
        username: CDSE username
        password: CDSE password
        scenes_dir: Directory to save scenes
        max_scenes_per_region: Maximum scenes per region
    
    Returns:
        Summary dict with download results from all regions
    """
    regions = {
        "primary": {
            "bbox": [float(x) for x in os.getenv("REGION_BBOX", "-17,27,-1,36").split(",")],
            "name": os.getenv("REGION_NAME", "Unknown Region")
        }
    }
    
    # Add neighboring regions if defined
    if os.getenv("ALGERIA_MED_BBOX"):
        regions["algeria_med"] = {
            "bbox": [float(x) for x in os.getenv("ALGERIA_MED_BBOX").split(",")],
            "name": os.getenv("ALGERIA_MED_NAME", "Algeria Mediterranean")
        }
    
    if os.getenv("MAURITANIA_ATL_BBOX"):
        regions["mauritania_atl"] = {
            "bbox": [float(x) for x in os.getenv("MAURITANIA_ATL_BBOX").split(",")],
            "name": os.getenv("MAURITANIA_ATL_NAME", "Mauritania Atlantic")
        }
    
    if os.getenv("SPAIN_MED_BBOX"):
        regions["spain_med"] = {
            "bbox": [float(x) for x in os.getenv("SPAIN_MED_BBOX").split(",")],
            "name": os.getenv("SPAIN_MED_NAME", "Spain Mediterranean")
        }
    
    if os.getenv("PORTUGAL_ATL_BBOX"):
        regions["portugal_atl"] = {
            "bbox": [float(x) for x in os.getenv("PORTUGAL_ATL_BBOX").split(",")],
            "name": os.getenv("PORTUGAL_ATL_NAME", "Portugal Atlantic")
        }
    
    all_results = {}
    
    # Get existing scene IDs to avoid duplicates across regions
    existing_scene_ids = get_existing_scene_ids(scenes_dir)
    
    for region_key, region_config in regions.items():
        # Refresh token before processing each region
        token, expiry_time = refresh_token_if_needed(token, expiry_time, username, password)
        
        logger.info(f"=== Processing region: {region_config['name']} ===")
        bbox = region_config["bbox"]
        region_name = region_config["name"]
        
        # Use simplified criteria for multi-region (fewer scenes per region)
        simplified_criteria = [
            {"date_start": "2025-01-01", "date_end": "2025-12-31", "count": max_scenes_per_region, "season": f"{region_name} 2025"}
        ]
        
        region_scenes = []
        total_size = 0
        
        region_success = False
        for criteria in simplified_criteria:
            try:
                products = search_sentinel1_products(
                    token, bbox, criteria["date_start"], criteria["date_end"], 
                    max_results=20, prefer_cog=True
                )
                region_success = True
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    logger.warning(f"403 Forbidden for region {region_name} - likely not accessible or invalid bbox")
                    all_results[region_key] = {
                        "region_name": region_name,
                        "bbox": bbox,
                        "scenes": [],
                        "total_size_gb": 0,
                        "successful": 0,
                        "failed": 0,
                        "error": "403 Forbidden - region not accessible"
                    }
                    region_success = False
                    break  # Skip this region entirely
                else:
                    raise  # Re-raise other HTTP errors
        
        if not region_success:
            continue  # Skip to next region if this one failed
        
        if len(products) > criteria["count"]:
            selected = products[:criteria["count"]]
        else:
            selected = products
        
        for product in selected:
            product_id = product["id"]
            product_name = product["name"]
            base_id = get_scene_base_id(product_name)

            if is_scene_downloaded(scenes_dir, product_name, existing_scene_ids):
                logger.info(f"  Scene already exists (base ID: {base_id or 'n/a'}): {product_name}")
                region_scenes.append({
                    "name": product_name,
                    "region": region_name,
                    "date": product["date"],
                    "size": product["size"],
                    "status": "already_downloaded"
                })
                continue
            
            try:
                safe_path = download_product(
                    token, product_id, product_name, str(scenes_dir),
                    time.time() + 600, username, password
                )
                
                if base_id:
                    existing_scene_ids.add(base_id)
                
                region_scenes.append({
                    "name": product_name,
                    "region": region_name,
                    "date": product["date"],
                    "size": product["size"],
                    "status": "downloaded",
                    "path": safe_path
                })
                total_size += product["size"]
                
            except Exception as e:
                logger.error(f"  Failed to download {product_name}: {e}")
                region_scenes.append({
                    "name": product_name,
                    "region": region_name,
                    "date": product["date"],
                    "size": product["size"],
                    "status": "failed",
                    "error": str(e)
                })
        
        region_scenes = deduplicate_scenes(region_scenes)
        all_results[region_key] = {
            "region_name": region_name,
            "bbox": bbox,
            "scenes": region_scenes,
            "total_size_gb": total_size / (1024**3),
            "successful": len([s for s in region_scenes if s["status"] in ["downloaded", "already_downloaded"]]),
            "failed": len([s for s in region_scenes if s["status"] == "failed"])
        }
        
        logger.info(f"Region {region_name}: {all_results[region_key]['successful']} scenes downloaded")
    
    return all_results


def main() -> None:
    """Main orchestration for downloading diverse scene dataset."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Download diverse Sentinel-1 scenes for Phase 0")
    parser.add_argument("--test", action="store_true", help="Run connection test only")
    parser.add_argument("--max-scenes", type=int, default=10, help="Maximum number of scenes to download")
    parser.add_argument("--multi-region", action="store_true", help="Download from multiple regions defined in .env")
    parser.add_argument("--max-scenes-per-region", type=int, default=3, help="Maximum scenes per region (multi-region mode)")
    parser.add_argument("--clean-non-morocco", action="store_true", help="Archive non-Morocco scenes and remove them from manifest")
    args = parser.parse_args()
    
    if args.test:
        test_connection()
        return

    if args.clean_non_morocco:
        scenes_dir = Path(__file__).parent / "data" / "scenes"
        clean_non_morocco_scenes(scenes_dir)
        return

    if args.multi_region:
        # Multi-region download mode
        logger.info("=== Multi-Region Download Mode ===")
        load_dotenv()
        
        username = os.getenv("CDSE_USERNAME")
        password = os.getenv("CDSE_PASSWORD")
        
        if not username or not password:
            logger.error("CDSE_USERNAME and CDSE_PASSWORD must be set")
            return
        
        scenes_dir = Path(__file__).parent / "data" / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        
        token, expiry_time = get_cdse_token(username, password)
        
        results = download_multi_region(
            token, username, password, scenes_dir, args.max_scenes_per_region
        )
        
        # Display multi-region summary
        logger.info("=" * 60)
        logger.info("Multi-Region Download Summary")
        logger.info("=" * 60)
        
        total_scenes = 0
        total_size = 0
        
        for region_key, region_result in results.items():
            logger.info(f"\n{region_result['region_name']}:")
            logger.info(f"  Scenes: {region_result['successful']} (failed: {region_result['failed']})")
            logger.info(f"  Size: {region_result['total_size_gb']:.2f} GB")
            
            total_scenes += region_result['successful']
            total_size += region_result['total_size_gb']
        
        logger.info(f"\nTotal: {total_scenes} scenes, {total_size:.2f} GB")
        
        # Save multi-region manifest
        manifest = {
            "download_date": datetime.now().isoformat(),
            "mode": "multi_region",
            "regions": results,
            "total_scenes": total_scenes,
            "total_size_gb": total_size
        }
        
        save_manifest(scenes_dir, manifest)
        return
    
    load_dotenv()
    
    username = os.getenv("CDSE_USERNAME")
    password = os.getenv("CDSE_PASSWORD")
    
    if not username or not password:
        logger.error("CDSE_USERNAME and CDSE_PASSWORD must be set in the environment or .env file.")
        return

    # Configuration
    bbox_str = os.getenv("REGION_BBOX", "-17,27,-1,36")
    bbox = [float(x) for x in bbox_str.split(",")]
    region_name = os.getenv("REGION_NAME", "Unknown Region")
    
    logger.info(f"Processing region: {region_name}")
    logger.info(f"Bounding box: {bbox}")
    
    scenes_dir = Path(__file__).parent / "data" / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    
    # Get initial token
    token, expiry_time = get_cdse_token(username, password)
    
    # Select scenes based on criteria
    existing_scene_ids = get_existing_scene_ids(scenes_dir)
    all_selected_scenes = []
    for criteria in SELECTION_CRITERIA:
        selected = select_scenes_for_criteria(
            token,
            criteria["bbox"],
            criteria,
            username,
            password,
            existing_scene_ids=existing_scene_ids,
        )
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
        season = product["season"]
        
        logger.info(f"Processing: {product_name} ({season})")
        
        # Check if already downloaded
        safe_path_existing = str(scenes_dir / f"{product_name}.SAFE")
        if is_scene_downloaded(scenes_dir, product_name, existing_scene_ids):
            logger.info(f"  Scene already downloaded, skipping")
            downloaded_scenes.append({
                "name": product_name,
                "label": product.get("label", season),
                "season": season,
                "date": product["date"],
                "size": product["size"],
                "status": "already_downloaded",
                "safe_path": safe_path_existing,
                "bbox_used": product.get("bbox_used", bbox),
                "date_range": product.get("date_range", f"{product['date']}/{product['date']}")
            })
            continue
        
        try:
            safe_path = download_product(
                token, product_id, product_name, str(scenes_dir),
                expiry_time, username, password
            )
            
            base_id = get_scene_base_id(product_name)
            if base_id:
                existing_scene_ids.add(base_id)

            downloaded_scenes.append({
                "name": product_name,
                "label": product.get("label", season),
                "season": season,
                "date": product["date"],
                "size": product["size"],
                "status": "downloaded",
                "safe_path": safe_path,
                "path": safe_path,
                "bbox_used": product.get("bbox_used", bbox),
                "date_range": product.get("date_range", f"{product['date']}/{product['date']}")
            })
            total_size += product["size"]
            
        except Exception as e:
            logger.error(f"  Failed to download {product_name}: {e}")
            downloaded_scenes.append({
                "name": product_name,
                "season": season,
                "date": product["date"],
                "size": product["size"],
                "status": "failed",
                "error": str(e)
            })
    
    # Generate summary
    downloaded_scenes = deduplicate_scenes(downloaded_scenes)
    successful = [s for s in downloaded_scenes if s["status"] in ["downloaded", "already_downloaded"]]
    failed = [s for s in downloaded_scenes if s["status"] == "failed"]
    
    logger.info("=" * 60)
    logger.info(f"✓ Scènes téléchargées : {len(successful)}/{len(all_selected_scenes)}")
    logger.info(f"  Région : {region_name}")
    logger.info(f"  Bounding box : {bbox}")
    logger.info(f"  Dossier : {scenes_dir}")
    logger.info(f"  Taille totale : {total_size / (1024**3):.2f} GB")
    logger.info(f"  Réussis : {len([s for s in downloaded_scenes if s['status'] == 'downloaded'])}")
    logger.info(f"  Déjà présents : {len([s for s in downloaded_scenes if s['status'] == 'already_downloaded'])}")
    logger.info(f"  Échoués : {len(failed)}")
    
    if failed:
        logger.warning("Scènes échouées :")
        for scene in failed:
            logger.warning(f"  - {scene['name']} ({scene['season']}) : {scene.get('error', 'Unknown error')}")
    
    logger.info("Liste des scènes :")
    for scene in downloaded_scenes:
        status_symbol = "✓" if scene["status"] != "failed" else "✗"
        logger.info(f"  {status_symbol} {scene['name']} ({scene['season']})")
    
    # Save manifest
    manifest = {
        "download_date": datetime.now().isoformat(),
        "region_name": region_name,
        "bbox": bbox,
        "total_scenes": len(all_selected_scenes),
        "successful": len(successful),
        "failed": len(failed),
        "total_size_gb": total_size / (1024**3),
        "scenes": downloaded_scenes
    }
    save_manifest(scenes_dir, manifest)


if __name__ == "__main__":
    main()