"""CDSE Sentinel-1 Product Downloader.

Purpose:
    Programmatically discover and download Sentinel-1 Ground Range Detected (GRD)
    Interferometric Wide (IW) swath mode products from the Copernicus Data Space Ecosystem (CDSE).

Inputs:
    Environment variables: CDSE_USERNAME, CDSE_PASSWORD
    Query parameters: bounding box, date range

Outputs:
    Downloaded and extracted .SAFE folders in research/data/scenes/
    manifest.json with scene metadata

This module implements OData API interactions with CDSE, Keycloak authentication,
robust streaming downloads with automatic ZIP extraction, and intelligent scene selection.
"""

import json
import logging
import os
import random
import time
import urllib.parse
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from tqdm import tqdm

# GFW API configuration
GFW_BASE_URL = "https://gateway.api.globalfishingwatch.org/v3"
GFW_EVENTS = f"{GFW_BASE_URL}/events"
GFW_REPORT = f"{GFW_BASE_URL}/4wings/report"
# DEPRECATED per PH0-CORR-002: SAR_VESSEL_DETECTIONS_DATASET = "public-global-sar-vessel-detections:latest"
# This dataset returns grid cell aggregates, not individual vessel positions
AIS_PRESENCE_DATASET = "public-global-presence:latest"

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# Constants
CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"  # noqa: S105
)
CDSE_ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
CDSE_DOWNLOAD_URL = "https://zipper.dataspace.copernicus.eu/odata/v1/Products"
TOKEN_EXPIRY_SECONDS = 600  # CDSE tokens expire after 10 minutes

# Scene selection criteria for Morocco 2025 only
# The dataset should cover Moroccan waters across all four quarters.
# Per PH0-CORR-002: Coastal targeting optimized for GFW coverage
#
# NOTE -- Two selection methods coexist:
#   PRIMARY METHOD: build_ais_density_map() + select_and_download_scenes_from_density()
#   targets the highest AIS density zones (maximizes annotations).
#   DOCUMENTED FALLBACK: SELECTION_CRITERIA (seasonal criteria) kept
#   for comparison with density-targeted scenes.
MOROCCO_BBOX = [-17, 27, -1, 36]  # [lon_min, lat_min, lon_max, lat_max] - Full reference bbox

# AIS density map parameters (PRIMARY method)
DENSITY_CELL_SIZE_DEG = 0.5  # ~55 km density map granularity
DENSITY_LOOKBACK_DAYS = 30  # recent period for AIS query
N_TARGET_ZONES = 5  # number of high-density zones to target
MAX_TEST_SCENES = 5  # strict test batch size

# Minimum scene age (days): avoids downloading scenes too recent for GFW AIS processing
# GFW typically needs 48-72h to ingest AIS data. Scenes < MIN_SCENE_AGE_DAYS old
# are unlikely to have AIS annotations and would waste bandwidth.
MIN_SCENE_AGE_DAYS = 3

# Targeting traceability (Part B of the protocol)
# Fields recorded in target_trace.json for each downloaded scene:
#   - target_density_cell_index (int, position in dmap['cells'])
#   - target_cell_bbox (exact bbox of the targeted cell)
# These fields are propagated into metadata.json during SAR processing.

# Configurable parameters (Part C -- via environment variables)
# Allows adjusting memory constraints without modifying the code.
# Default values correspond to the Colab environment (16 GB RAM).
# For a more powerful machine, these values can be increased.
_N_EMPTY_TILES_PER_SCENE = int(os.getenv("N_EMPTY_TILES_PER_SCENE", "80"))
_MAX_TILES_PER_SCENE_HARD_CAP = int(os.getenv("MAX_TILES_PER_SCENE_HARD_CAP", "600"))


def generate_coastal_search_bboxes(
    full_bbox: list[float], coastal_width_km: float = 50.0
) -> list[list[float]]:
    """
    Generate coastal search bounding boxes along the Moroccan coastline.

    This function creates band-like search areas centered on the coastal region
    rather than using the full land/sea bbox. This is motivated by GFW coverage
    optimization, not operational constraints.

    Args:
        full_bbox: Full geographic bounding box [lon_min, lat_min, lon_max, lat_max]
        coastal_width_km: Width of the coastal band in kilometers

    Returns:
        List of coastal bounding boxes for CDSE search

    Note:
        This is a simplified implementation. A production version would use
        actual coastline geometry from Marine Regions v12 or similar source.
    """
    lon_min, lat_min, lon_max, lat_max = full_bbox

    # Approximate conversion: 1 degree ≈ 111 km at equator
    # coastal_width_deg = coastal_width_km / 111.0  # kept for reference

    # Generate coastal bands (simplified - actual coastline geometry would be better)
    # Morocco has both Atlantic and Mediterranean coasts
    coastal_bboxes = [
        # Atlantic coast bands (north to south)
        [lon_min, lat_min, lon_max, lat_max],  # Full bbox as fallback
        # Future enhancement: Use actual coastline geometry from Marine Regions v12
    ]

    logger.info(
        f"Generated {len(coastal_bboxes)} coastal search boxes (width: {coastal_width_km}km)"
    )
    logger.warning(
        "NOTE: This uses simplified coastal targeting. Production should use Marine Regions v12 coastline geometry."
    )

    return coastal_bboxes


# Generate coastal search boxes for Morocco
COASTAL_SEARCH_BBOXES = generate_coastal_search_bboxes(MOROCCO_BBOX)

SELECTION_CRITERIA = [
    {
        "bbox": COASTAL_SEARCH_BBOXES[0],  # Use coastal targeting
        "date_start": "2025-01-01",
        "date_end": "2025-03-31",
        "count": 3,
        "label": "Morocco_Q1_winter",
        "season": "Morocco Q1 Winter",
        "targeting_rationale": "coastal_gfw_coverage_optimization",
    },
    {
        "bbox": COASTAL_SEARCH_BBOXES[0],  # Use coastal targeting
        "date_start": "2025-04-01",
        "date_end": "2025-06-30",
        "count": 3,
        "label": "Morocco_Q2_spring",
        "season": "Morocco Q2 Spring",
        "targeting_rationale": "coastal_gfw_coverage_optimization",
    },
    {
        "bbox": COASTAL_SEARCH_BBOXES[0],  # Use coastal targeting
        "date_start": "2025-07-01",
        "date_end": "2025-09-30",
        "count": 3,
        "label": "Morocco_Q3_summer",
        "season": "Morocco Q3 Summer",
        "targeting_rationale": "coastal_gfw_coverage_optimization",
    },
    {
        "bbox": COASTAL_SEARCH_BBOXES[0],  # Use coastal targeting
        "date_start": "2025-10-01",
        "date_end": "2025-12-31",
        "count": 3,
        "label": "Morocco_Q4_autumn",
        "season": "Morocco Q4 Autumn",
        "targeting_rationale": "coastal_gfw_coverage_optimization",
    },
]
# Total target: 12 Morocco 2025 scenes only
# Coastal targeting motivated by GFW coverage optimization per PH0-CORR-002

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # Exponential backoff multiplier


def check_ais_coverage_before_download(
    bbox: list[float], date_start: str, date_end: str, gfw_token: str | None = None
) -> bool:
    """
    Query GFW AIS Vessel Presence BEFORE launching the full CDSE download.
    If zero AIS results for the candidate bbox/date, log explicitly and skip to the
    next candidate WITHOUT downloading.

    Does not replace final human verification -- only reduces bandwidth waste on
    non-exploitable candidates.

    Args:
        bbox: Geographic bounding box [lon_min, lat_min, lon_max, lat_max]
        date_start: Start date string (ISO8601)
        date_end: End date string (ISO8601)
        gfw_token: Optional GFW API token (if not provided, will not check GFW)

    Returns:
        bool: True if AIS coverage exists, False otherwise
    """
    if not gfw_token:
        logger.warning(
            "GFW_API_TOKEN not provided - skipping AIS coverage check, allowing download"
        )
        return True

    headers = {"Authorization": f"Bearer {gfw_token}"}
    lon_min, lat_min, lon_max, lat_max = bbox
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [lon_min, lat_min],
                [lon_max, lat_min],
                [lon_max, lat_max],
                [lon_min, lat_max],
                [lon_min, lat_min],
            ]
        ],
    }

    # GFW v3 /4wings/report POST: datasets[0], date-range, spatial-resolution,
    # temporal-resolution, and format go as query params. geojson and limit go in the body.
    query_params = {
        "datasets[0]": AIS_PRESENCE_DATASET,
        "date-range": f"{date_start},{date_end}",
        "spatial-resolution": "HIGH",
        "temporal-resolution": "DAILY",
        "format": "JSON",
    }
    body_params = {
        "geojson": geometry,
        "limit": 1,  # Only need to know if there's any coverage
    }

    try:
        response = httpx.post(
            GFW_REPORT, headers=headers, params=query_params, json=body_params, timeout=30.0
        )
        if response.status_code == 200:
            data = response.json()
            # USE _normalize_response_entries() for coverage check (fix audit S1.8)
            # The residual bug was that the len(data[field]) > 0 check could produce
            # a false positive on a nested empty response (entries[0][dataset_key] structure).
            # By normalizing first, we correctly handle the nested structure.
            from research.scripts.gfw_annotations import _normalize_response_entries

            normalized = _normalize_response_entries(data)
            if normalized and len(normalized) > 0:
                logger.info("AIS coverage confirmed for this zone/date")
                return True
    except Exception as e:
        logger.warning(f"GFW AIS coverage check failed: {e}")
        # On failure, allow download to proceed (conservative approach)
        return True

    logger.warning(
        "No GFW AIS coverage for this zone/date -- scene NOT downloaded, invalid test corpus without Ground Truth"
    )
    logger.warning(f"  Zone: {bbox}, Period: {date_start} to {date_end}")
    logger.warning(
        "  This safeguard saves bandwidth but does NOT solve the root issue if GFW structurally has no coverage"
    )
    return False


def retry_with_backoff(func):
    """Decorator for retrying HTTP requests with exponential backoff."""

    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                last_exception = e
                wait_time = RETRY_BACKOFF**attempt
                logger.warning(
                    f"Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}. Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
        raise last_exception

    return wrapper


def get_cdse_token(username: str, password: str) -> tuple[str, float]:
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


def refresh_token_if_needed(
    token: str, expiry_time: float, username: str, password: str
) -> tuple[str, float]:
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
    bbox: list[float],
    date_start: str,
    date_end: str,
    max_results: int = 50,
    prefer_cog: bool = True,
) -> list[dict[str, Any]]:
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

    params = {"$filter": filter_query, "$top": max_results, "$orderby": "ContentDate/Start desc"}

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
        normalized_results.append(
            {
                "id": product.get("Id"),
                "name": product.get("Name"),
                "date": product.get("ContentDate", {}).get("Start"),
                "size": product.get("ContentLength", 0),
                "footprint": product.get("ContentGeometry", ""),
            }
        )

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
            # Base identifier includes mission, mode, polarization, and timestamp
            base_id = (
                "_".join(parts[:7]) if len(parts) >= 8 else name
            )  # S1A_IW_GRDH_1SDV_20240107T064657_20240107T064719

            # Group products by base identifier
            if base_id not in product_groups:
                product_groups[base_id] = []
            product_groups[base_id].append(product)

        # For each group, prefer COG variant, otherwise keep standard
        for base_id, group in product_groups.items():
            # Check for COG variant
            cog_variants = [
                p for p in group if "_COG" in p["name"] or p["name"].endswith("_COG.SAFE")
            ]

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
    password: str,
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
    with (
        open(zip_path, "wb") as f,
        tqdm(total=total_size, unit="B", unit_scale=True, desc=product_name[:20]) as progress,
    ):
        for chunk in response.iter_bytes(chunk_size=8192):
            f.write(chunk)
            progress.update(len(chunk))

    logger.info(f"Download complete: {zip_path}. Extracting archive...")

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            # Debug: list the contents of the zip
            logger.info(
                f"ZIP contains {len(zip_ref.namelist())} files. First 10: {zip_ref.namelist()[:10]}"
            )

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


def get_scene_base_id(product_name: str) -> str | None:
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
    existing_scene_ids: set | None = None,
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
    bbox: list[float],
    criteria: dict[str, Any],
    username: str,
    password: str,
    existing_scene_ids: set | None = None,
) -> list[dict[str, Any]]:
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

    products = search_sentinel1_products(
        token, bbox, date_start, date_end, max_results=60, prefer_cog=True
    )

    if not products:
        logger.warning(f"No products found for {season}")
        return []

    filtered_products = []
    seen_base_ids = set()
    for product in products:
        base_id = get_scene_base_id(product.get("name", ""))
        if base_id and (
            base_id in seen_base_ids
            or (existing_scene_ids is not None and base_id in existing_scene_ids)
        ):
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
        logger.warning(
            f"Only {len(filtered_products)} products available for {season}, requested {count}"
        )

    # Add selection metadata to each product
    for product in selected:
        product["season"] = season
        product["label"] = label
        product["bbox_used"] = bbox
        product["date_range"] = f"{date_start}/{date_end}"

    logger.info(f"Selected {len(selected)} scenes for {label}")
    return selected


def deduplicate_scenes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def save_manifest(scenes_dir: Path, manifest: dict[str, Any]) -> None:
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
    with open(manifest_path, "w") as f:
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

    with open(manifest_path, encoding="utf-8") as f:
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
            logger.warning(
                "SAFE path does not exist for scene %s: %s", scene.get("name"), safe_path
            )

    manifest["scenes"] = remaining_scenes
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    logger.info("Archived %s non-Morocco scenes and updated manifest", archived_count)


# ---------------------------------------------------------------------------
# AIS Density Map (ported from notebook, cells 7-8)
# PRIMARY scene selection method
# ---------------------------------------------------------------------------


def build_ais_density_map(
    bbox: list[float],
    cell_size_deg: float = DENSITY_CELL_SIZE_DEG,
    lookback_days: int = DENSITY_LOOKBACK_DAYS,
    gfw_token: str | None = None,
) -> dict[str, Any]:
    """
    Queries GFW AIS Presence over the full bbox, aggregates positions by grid cell,
    returns a density ranking. Ported from notebook cell 7.

    Args:
        bbox: Geographic bounding box [lon_min, lat_min, lon_max, lat_max]
        cell_size_deg: Grid cell size in degrees (~55 km at 0.5 deg)
        lookback_days: Number of days to look back for AIS data
        gfw_token: GFW API token

    Returns:
        Dict with 'cells' (sorted by count descending), 'total_positions', etc.
    """
    from research.scripts.gfw_annotations import _extract_lat_lon, _normalize_response_entries

    lon_min, lat_min, lon_max, lat_max = bbox
    end = datetime.now(UTC).date()
    start = end - timedelta(days=lookback_days)

    if not gfw_token:
        gfw_token = os.getenv("GFW_API_TOKEN")
    if not gfw_token:
        logger.warning("No GFW token available -- cannot build density map.")
        return {"cells": [], "total_positions": 0, "error": "no_token"}

    logger.info(f"Querying AIS density over {bbox}, {start} -> {end}")

    headers = {"Authorization": f"Bearer {gfw_token}"}
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [lon_min, lat_min],
                [lon_max, lat_min],
                [lon_max, lat_max],
                [lon_min, lat_max],
                [lon_min, lat_min],
            ]
        ],
    }

    query_params = {
        "datasets[0]": AIS_PRESENCE_DATASET,
        "date-range": f"{start.isoformat()},{end.isoformat()}",
        "spatial-resolution": "HIGH",
        "temporal-resolution": "DAILY",
        "format": "JSON",
    }
    body_params = {"geojson": geometry, "limit": 500}

    try:
        response = httpx.post(
            GFW_REPORT, headers=headers, params=query_params, json=body_params, timeout=60.0
        )
        if response.status_code != 200:
            logger.warning(f"GFW density query failed ({response.status_code})")
            return {"cells": [], "total_positions": 0}

        entries = _normalize_response_entries(response.json())
        positions = []
        for entry in entries:
            lat, lon = _extract_lat_lon(entry)
            if lat is not None and lon is not None:
                positions.append({"lat": lat, "lon": lon})

        if not positions:
            logger.warning("No AIS positions returned -- cannot build density map.")
            return {"cells": [], "total_positions": 0}

        n_lon_cells = max(1, int((lon_max - lon_min) / cell_size_deg))
        n_lat_cells = max(1, int((lat_max - lat_min) / cell_size_deg))

        density = {}
        for p in positions:
            ci = min(n_lon_cells - 1, int((p["lon"] - lon_min) / cell_size_deg))
            cj = min(n_lat_cells - 1, int((p["lat"] - lat_min) / cell_size_deg))
            key = (ci, cj)
            density[key] = density.get(key, 0) + 1

        cells = []
        for (ci, cj), count in density.items():
            cell_lon_min = lon_min + ci * cell_size_deg
            cell_lat_min = lat_min + cj * cell_size_deg
            cells.append(
                {
                    "cell_index": ci * n_lat_cells + cj,  # unique index for traceability
                    "cell_bbox": [
                        cell_lon_min,
                        cell_lat_min,
                        cell_lon_min + cell_size_deg,
                        cell_lat_min + cell_size_deg,
                    ],
                    "count": count,
                }
            )
        cells.sort(key=lambda c: c["count"], reverse=True)

        result = {
            "total_positions": len(positions),
            "n_cells_with_data": len(cells),
            "cells": cells,
            "period": f"{start.isoformat()}/{end.isoformat()}",
        }

        # Save the density map
        density_dir = Path(__file__).parent / "data" / "density"
        density_dir.mkdir(parents=True, exist_ok=True)
        path = density_dir / "ais_density_map.json"
        with open(path, "w") as f:
            json.dump(result, f, indent=2)

        logger.info(f"Density map: {len(positions)} positions -> {len(cells)} non-empty cells")
        return result

    except Exception as e:
        logger.error(f"Density map query failed: {e}")
        return {"cells": [], "total_positions": 0}


# ---------------------------------------------------------------------------
# AIS density-targeted selection and download (ported from notebook cells 9-10)
# Part B: traceability via target_trace.json
#
# Layout (one trace per scene, never a shared parent-level file):
#
#   research/data/scenes/
#     <SCENE_ID>.SAFE/
#       manifest.safe
#       target_trace.json          ← always INSIDE the .SAFE folder
#       measurement/ ...
#     target_traces_index.json     ← maps scene_id → trace path + cell info
#
# target_trace.json fields:
#   - scene_id                   : product name without .SAFE (explicit link)
#   - safe_dir                   : directory name of the .SAFE folder
#   - target_density_cell_index  : unique cell id from the density map
#   - target_cell_bbox           : exact AIS cell bbox that motivated download
#   - density_rank               : 1-based rank among high-density zones
#   - ais_count                  : AIS positions counted in that cell
#   - protocol                   : PH0-CORR-002_density_targeted
# ---------------------------------------------------------------------------

TARGET_TRACES_INDEX_NAME = "target_traces_index.json"


def _normalize_scene_id(product_name: str) -> str:
    """Strip .SAFE / trailing slash so scene_id is stable across path forms."""
    return product_name.rstrip("/").replace(".SAFE", "")


def resolve_safe_dir(scenes_dir: Path, product_name: str) -> Path | None:
    """Locate the on-disk .SAFE directory for a product name (handles COG variants)."""
    scene_id = _normalize_scene_id(product_name)
    candidates = [
        scenes_dir / f"{scene_id}.SAFE",
        scenes_dir / f"{product_name}.SAFE"
        if not product_name.endswith(".SAFE")
        else scenes_dir / product_name,
        scenes_dir / product_name,
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    # Fallback: match by base orbit/mission id (standard vs COG)
    base_id = get_scene_base_id(product_name)
    if base_id:
        for safe_dir in scenes_dir.glob("*.SAFE"):
            if safe_dir.is_dir() and get_scene_base_id(safe_dir.stem) == base_id:
                return safe_dir
    return None


def write_target_trace(
    scene_dir: Path,
    cell_index: int,
    cell_bbox: list[float],
    *,
    scene_id: str | None = None,
    density_rank: int | None = None,
    ais_count: int | None = None,
    protocol: str = "PH0-CORR-002_density_targeted",
) -> Path:
    """
    Write target_trace.json **inside** the given .SAFE directory.

    The file is always co-located with the scene so there is never ambiguity
    about which scene a trace belongs to. ``scene_id`` / ``safe_dir`` make the
    link explicit even if the JSON is copied elsewhere.

    Returns:
        Path to the written target_trace.json
    """
    scene_dir = Path(scene_dir)
    scene_dir.mkdir(parents=True, exist_ok=True)

    resolved_scene_id = scene_id or _normalize_scene_id(scene_dir.name)
    trace = {
        "scene_id": resolved_scene_id,
        "safe_dir": scene_dir.name
        if scene_dir.name.endswith(".SAFE")
        else f"{scene_dir.name}.SAFE",
        "target_density_cell_index": cell_index,
        "target_cell_bbox": list(cell_bbox),
        "density_rank": density_rank,
        "ais_count": ais_count,
        "protocol": protocol,
    }
    # Drop None optionals for cleaner JSON when callers omit them
    trace = {k: v for k, v in trace.items() if v is not None}

    trace_path = scene_dir / "target_trace.json"
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2)
    logger.info(
        f"Target trace written: {trace_path} (scene_id={resolved_scene_id}, cell={cell_index})"
    )
    return trace_path


def update_target_traces_index(
    scenes_dir: Path,
    scene_id: str,
    safe_dir_name: str,
    trace: dict[str, Any],
) -> Path:
    """
    Update (or create) scenes_dir/target_traces_index.json.

    This index is the single place to look up which target_trace.json belongs
    to which scene without scanning every .SAFE folder.
    """
    scenes_dir = Path(scenes_dir)
    index_path = scenes_dir / TARGET_TRACES_INDEX_NAME

    if index_path.exists():
        try:
            with open(index_path, encoding="utf-8") as f:
                index = json.load(f)
        except (json.JSONDecodeError, OSError):
            index = {}
    else:
        index = {}

    if "scenes" not in index or not isinstance(index["scenes"], dict):
        index["scenes"] = {}

    index["protocol"] = "PH0-CORR-002_density_targeted"
    index["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    index["scenes"][scene_id] = {
        "safe_dir": safe_dir_name,
        "trace_path": f"{safe_dir_name}/target_trace.json",
        "target_density_cell_index": trace.get("target_density_cell_index"),
        "target_cell_bbox": trace.get("target_cell_bbox"),
        "density_rank": trace.get("density_rank"),
        "ais_count": trace.get("ais_count"),
        "protocol": trace.get("protocol"),
    }

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    logger.info(f"Target traces index updated: {index_path} (+ {scene_id})")
    return index_path


def write_scene_target_trace(
    scenes_dir: Path,
    safe_path: Path,
    cell_index: int,
    cell_bbox: list[float],
    *,
    density_rank: int | None = None,
    ais_count: int | None = None,
    protocol: str = "PH0-CORR-002_density_targeted",
) -> dict[str, Any]:
    """
    Write target_trace.json inside a scene and register it in the index.

    Returns the trace dict that was written.
    """
    scenes_dir = Path(scenes_dir)
    safe_path = Path(safe_path)
    scene_id = _normalize_scene_id(safe_path.name)

    trace_path = write_target_trace(
        safe_path,
        cell_index,
        cell_bbox,
        scene_id=scene_id,
        density_rank=density_rank,
        ais_count=ais_count,
        protocol=protocol,
    )
    with open(trace_path, encoding="utf-8") as f:
        trace = json.load(f)

    update_target_traces_index(
        scenes_dir,
        scene_id=scene_id,
        safe_dir_name=safe_path.name,
        trace=trace,
    )
    return trace


def select_and_download_scenes_from_density(
    token: str,
    density_map: dict[str, Any],
    n_scenes: int = MAX_TEST_SCENES,
    output_dir: Path | None = None,
    username: str = "",
    password: str = "",
    expiry_time: float | None = None,
) -> list[str]:
    """
    Select and download CDSE scenes targeting the highest AIS density zones.
    Ported from notebook cell 10.

    For each scene (newly downloaded **or** already on disk), writes:
      - ``<scene>.SAFE/target_trace.json``  (per-scene, co-located)
      - updates ``target_traces_index.json`` (scene_id → trace mapping)

    Args:
        token: CDSE authentication token
        density_map: Result of build_ais_density_map()
        n_scenes: Maximum number of scenes to download
        output_dir: Output directory (default: research/data/scenes/)
        username: CDSE username (for token refresh during long downloads)
        password: CDSE password

    Returns:
        List of paths to downloaded/existing .SAFE scenes (density-ordered)
    """
    if output_dir is None:
        output_dir = Path(__file__).parent / "data" / "scenes"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cells = density_map.get("cells", [])
    if not cells:
        logger.error("Density map has no cells -- cannot select scenes.")
        return []

    # Search from MIN_SCENE_AGE_DAYS ago backwards (avoid today's/yesterday's scenes
    # that GFW may not have processed AIS data for yet)
    end = datetime.now(UTC).date() - timedelta(days=MIN_SCENE_AGE_DAYS)
    start = end - timedelta(days=90)
    downloaded: list[str] = []
    existing_ids = get_existing_scene_ids(output_dir)

    for i, cell in enumerate(cells[:n_scenes]):
        bbox = cell["cell_bbox"]
        cell_index = cell.get("cell_index", i)
        density_rank = i + 1  # 1 = highest density zone targeted
        ais_count = cell.get("count")
        logger.info(
            f"Targeting Zone {density_rank}/{n_scenes}: cell_index={cell_index}, bbox={bbox}, AIS count={ais_count}"
        )

        # Refresh token before each search (CDSE tokens expire in 10 min)
        if expiry_time is not None:
            token, expiry_time = refresh_token_if_needed(token, expiry_time, username, password)
        else:
            if username:
                token, expiry_time = get_cdse_token(username, password)

        try:
            products = search_sentinel1_products(
                token, bbox, start.isoformat(), end.isoformat(), max_results=5
            )
        except Exception as e:
            logger.warning(f"Search failed for zone {density_rank}: {e}")
            # Retry once with fresh token in case of auth failure
            if username:
                try:
                    new_token, expiry_time = get_cdse_token(username, password)
                    products = search_sentinel1_products(
                        new_token, bbox, start.isoformat(), end.isoformat(), max_results=5
                    )
                    token = new_token
                    logger.info(f"  Retry succeeded for zone {density_rank} with fresh token")
                except Exception as e2:
                    logger.warning(f"  Retry also failed for zone {density_rank}: {e2}")
                    continue
            else:
                continue

        if not products:
            logger.warning(f"No products found for zone {density_rank}: {bbox}")
            continue

        # Prefer a product that is not already in this download batch
        product = None
        for candidate in products:
            base_id = get_scene_base_id(candidate.get("name", ""))
            # Skip only if already selected in this run (allow re-using on disk)
            already_in_batch = False
            if base_id:
                for path_str in downloaded:
                    if get_scene_base_id(Path(path_str).name) == base_id:
                        already_in_batch = True
                        break
            if not already_in_batch:
                product = candidate
                break
        if product is None:
            product = products[0]

        product_name = product["name"]

        # --- Case A: scene already on disk — still ensure target_trace exists ---
        if is_scene_downloaded(output_dir, product_name, existing_ids):
            safe_path = resolve_safe_dir(output_dir, product_name)
            if safe_path is None:
                logger.warning(f"Scene marked as downloaded but .SAFE not found: {product_name}")
                continue
            logger.info(f"Scene already downloaded: {safe_path.name}")
            write_scene_target_trace(
                output_dir,
                safe_path,
                cell_index,
                bbox,
                density_rank=density_rank,
                ais_count=ais_count,
            )
            downloaded.append(str(safe_path))
            base_id = get_scene_base_id(product_name)
            if base_id:
                existing_ids.add(base_id)
            continue

        # --- AIS coverage check before downloading ---
        gfw_token = os.getenv("GFW_API_TOKEN")
        if gfw_token:
            # Query GFW for AIS data around the product's acquisition date
            product_date = product.get("date", "")
            if product_date:
                try:
                    dt = datetime.fromisoformat(product_date.replace("Z", "+00:00"))
                    ais_date = dt.strftime("%Y-%m-%d")
                    has_ais = check_ais_coverage_before_download(
                        bbox, ais_date, ais_date, gfw_token
                    )
                    if not has_ais:
                        logger.info(
                            f"  Skipping {product_name} — no GFW AIS coverage for {ais_date}"
                        )
                        continue
                except Exception as e:
                    logger.warning(f"  AIS coverage check failed: {e} — proceeding anyway")

        # --- Case B: fresh download ---
        try:
            dl_username = username if username else os.getenv("CDSE_USERNAME", "")
            dl_password = password if password else os.getenv("CDSE_PASSWORD", "")
            safe_path_str = download_product(
                token,
                product["id"],
                product_name,
                str(output_dir),
                time.time() + 600,
                dl_username,
                dl_password,
            )
            safe_path = Path(safe_path_str)
            # download_product can return output_dir on extraction edge-cases
            if not safe_path.name.endswith(".SAFE") or not safe_path.is_dir():
                resolved = resolve_safe_dir(output_dir, product_name)
                if resolved is not None:
                    safe_path = resolved
                else:
                    logger.error(f"Could not resolve .SAFE path after download: {product_name}")
                    continue

            write_scene_target_trace(
                output_dir,
                safe_path,
                cell_index,
                bbox,
                density_rank=density_rank,
                ais_count=ais_count,
            )

            base_id = get_scene_base_id(product_name)
            if base_id:
                existing_ids.add(base_id)

            downloaded.append(str(safe_path))
            logger.info(
                f"Downloaded: {safe_path.name} (zone {density_rank}, cell_index={cell_index}, AIS count={ais_count})"
            )

        except Exception as e:
            logger.error(f"Failed to download {product_name}: {e}")

    logger.info(f"Density-targeted download: {len(downloaded)}/{n_scenes} scenes")
    if downloaded:
        logger.info(
            f"Per-scene target_trace.json files are inside each .SAFE; index at {output_dir / TARGET_TRACES_INDEX_NAME}"
        )
    return downloaded


# ---------------------------------------------------------------------------
# End of AIS density functions
# ---------------------------------------------------------------------------


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

        products = search_sentinel1_products(
            token, bbox, "2024-01-01", "2024-01-31", max_results=10, prefer_cog=True
        )

        if products:
            logger.info(f"✓ Search successful - found {len(products)} products")
            logger.info("First 3 products:")
            for i, product in enumerate(products[:3], 1):
                is_cog = "COG" in product["name"]
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
    token: str, username: str, password: str, scenes_dir: Path, max_scenes_per_region: int = 3
) -> dict[str, Any]:
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
            "name": os.getenv("REGION_NAME", "Unknown Region"),
        }
    }

    # Add neighboring regions if defined
    if os.getenv("ALGERIA_MED_BBOX"):
        regions["algeria_med"] = {
            "bbox": [float(x) for x in os.getenv("ALGERIA_MED_BBOX").split(",")],
            "name": os.getenv("ALGERIA_MED_NAME", "Algeria Mediterranean"),
        }

    if os.getenv("MAURITANIA_ATL_BBOX"):
        regions["mauritania_atl"] = {
            "bbox": [float(x) for x in os.getenv("MAURITANIA_ATL_BBOX").split(",")],
            "name": os.getenv("MAURITANIA_ATL_NAME", "Mauritania Atlantic"),
        }

    if os.getenv("SPAIN_MED_BBOX"):
        regions["spain_med"] = {
            "bbox": [float(x) for x in os.getenv("SPAIN_MED_BBOX").split(",")],
            "name": os.getenv("SPAIN_MED_NAME", "Spain Mediterranean"),
        }

    if os.getenv("PORTUGAL_ATL_BBOX"):
        regions["portugal_atl"] = {
            "bbox": [float(x) for x in os.getenv("PORTUGAL_ATL_BBOX").split(",")],
            "name": os.getenv("PORTUGAL_ATL_NAME", "Portugal Atlantic"),
        }

    all_results = {}
    expiry_time = 0.0

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
            {
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
                "count": max_scenes_per_region,
                "season": f"{region_name} 2025",
            }
        ]

        region_scenes = []
        total_size = 0

        region_success = False
        for criteria in simplified_criteria:
            try:
                products = search_sentinel1_products(
                    token,
                    bbox,
                    criteria["date_start"],
                    criteria["date_end"],
                    max_results=20,
                    prefer_cog=True,
                )
                region_success = True
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    logger.warning(
                        f"403 Forbidden for region {region_name} - likely not accessible or invalid bbox"
                    )
                    all_results[region_key] = {
                        "region_name": region_name,
                        "bbox": bbox,
                        "scenes": [],
                        "total_size_gb": 0,
                        "successful": 0,
                        "failed": 0,
                        "error": "403 Forbidden - region not accessible",
                    }
                    region_success = False
                    break  # Skip this region entirely
                else:
                    raise  # Re-raise other HTTP errors

        if not region_success:
            continue  # Skip to next region if this one failed

        selected = products[: criteria["count"]] if len(products) > criteria["count"] else products

        for product in selected:
            product_id = product["id"]
            product_name = product["name"]
            base_id = get_scene_base_id(product_name)
            product_date = product["date"]

            if is_scene_downloaded(scenes_dir, product_name, existing_scene_ids):
                logger.info(f"  Scene already exists (base ID: {base_id or 'n/a'}): {product_name}")
                region_scenes.append(
                    {
                        "name": product_name,
                        "region": region_name,
                        "date": product["date"],
                        "size": product["size"],
                        "status": "already_downloaded",
                    }
                )
                continue

            # Check GFW coverage before downloading
            gfw_token = os.getenv("GFW_API_TOKEN")
            if gfw_token:
                # Extract date range from product date (assume single day for now)
                try:
                    dt = datetime.fromisoformat(product_date.replace("Z", "+00:00"))
                    date_start = dt.strftime("%Y-%m-%d")
                    date_end = dt.strftime("%Y-%m-%d")

                    # Use AIS coverage check per PH0-CORR-002
                    has_ais_coverage = check_ais_coverage_before_download(
                        bbox, date_start, date_end, gfw_token
                    )

                    if not has_ais_coverage:
                        logger.info(f"  Skipping {product_name} - no AIS coverage")
                        region_scenes.append(
                            {
                                "name": product_name,
                                "region": region_name,
                                "date": product["date"],
                                "size": product["size"],
                                "status": "skipped_no_ais",
                                "reason": "No GFW AIS coverage",
                            }
                        )
                        continue
                except Exception as e:
                    logger.warning(
                        f"  AIS coverage check failed for {product_name}: {e} - proceeding with download"
                    )

            try:
                safe_path = download_product(
                    token,
                    product_id,
                    product_name,
                    str(scenes_dir),
                    time.time() + 600,
                    username,
                    password,
                )

                if base_id:
                    existing_scene_ids.add(base_id)

                region_scenes.append(
                    {
                        "name": product_name,
                        "region": region_name,
                        "date": product["date"],
                        "size": product["size"],
                        "status": "downloaded",
                        "path": safe_path,
                        "targeting_rationale": criteria.get(
                            "targeting_rationale", "coastal_gfw_coverage_optimization"
                        ),
                    }
                )
                total_size += product["size"]

            except Exception as e:
                logger.error(f"  Failed to download {product_name}: {e}")
                region_scenes.append(
                    {
                        "name": product_name,
                        "region": region_name,
                        "date": product["date"],
                        "size": product["size"],
                        "status": "failed",
                        "error": str(e),
                    }
                )

        region_scenes = deduplicate_scenes(region_scenes)
        all_results[region_key] = {
            "region_name": region_name,
            "bbox": bbox,
            "scenes": region_scenes,
            "total_size_gb": total_size / (1024**3),
            "successful": len(
                [s for s in region_scenes if s["status"] in ["downloaded", "already_downloaded"]]
            ),
            "failed": len([s for s in region_scenes if s["status"] == "failed"]),
        }

        logger.info(
            f"Region {region_name}: {all_results[region_key]['successful']} scenes downloaded"
        )

    return all_results


def main() -> None:
    """Main orchestration for downloading diverse scene dataset."""
    import argparse

    parser = argparse.ArgumentParser(description="Download diverse Sentinel-1 scenes for Phase 0")
    parser.add_argument("--test", action="store_true", help="Run connection test only")
    parser.add_argument(
        "--max-scenes", type=int, default=10, help="Maximum number of scenes to download"
    )
    parser.add_argument(
        "--multi-region", action="store_true", help="Download from multiple regions defined in .env"
    )
    parser.add_argument(
        "--max-scenes-per-region",
        type=int,
        default=3,
        help="Maximum scenes per region (multi-region mode)",
    )
    parser.add_argument(
        "--clean-non-morocco",
        action="store_true",
        help="Archive non-Morocco scenes and remove them from manifest",
    )
    parser.add_argument(
        "--density",
        action="store_true",
        help="Use AIS density map for targeted scene selection (PRIMARY METHOD)",
    )
    parser.add_argument(
        "--density-n-scenes",
        type=int,
        default=MAX_TEST_SCENES,
        help="Number of density-targeted scenes to download",
    )
    args = parser.parse_args()

    if args.test:
        test_connection()
        return

    if args.density:
        logger.info("=== AIS Density-Targeted Download Mode ===")
        load_dotenv()

        username = os.getenv("CDSE_USERNAME")
        password = os.getenv("CDSE_PASSWORD")
        if not username or not password:
            logger.error("CDSE_USERNAME and CDSE_PASSWORD must be set")
            return

        gfw_token = os.getenv("GFW_API_TOKEN")
        scenes_dir = Path(__file__).parent / "data" / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        # 1. Build AIS density map
        logger.info("Building AIS density map...")
        density_map = build_ais_density_map(MOROCCO_BBOX, gfw_token=gfw_token)
        if not density_map.get("cells"):
            logger.error("Density map empty -- cannot proceed with density-targeted download.")
            return

        # 2. CDSE authentication
        token, expiry_time = get_cdse_token(username, password)

        # 3. Targeted download
        downloaded = select_and_download_scenes_from_density(
            token, density_map, args.density_n_scenes, scenes_dir, username, password
        )

        logger.info(f"Density-targeted download complete: {len(downloaded)} scenes")
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

        for _region_key, region_result in results.items():
            logger.info(f"\n{region_result['region_name']}:")
            logger.info(
                f"  Scenes: {region_result['successful']} (failed: {region_result['failed']})"
            )
            logger.info(f"  Size: {region_result['total_size_gb']:.2f} GB")

            total_scenes += region_result["successful"]
            total_size += region_result["total_size_gb"]

        logger.info(f"\nTotal: {total_scenes} scenes, {total_size:.2f} GB")

        # Save multi-region manifest
        manifest = {
            "download_date": datetime.now().isoformat(),
            "mode": "multi_region",
            "regions": results,
            "total_scenes": total_scenes,
            "total_size_gb": total_size,
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
        all_selected_scenes = all_selected_scenes[: args.max_scenes]
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
            logger.info("  Scene already downloaded, skipping")
            downloaded_scenes.append(
                {
                    "name": product_name,
                    "label": product.get("label", season),
                    "season": season,
                    "date": product["date"],
                    "size": product["size"],
                    "status": "already_downloaded",
                    "safe_path": safe_path_existing,
                    "bbox_used": product.get("bbox_used", bbox),
                    "date_range": product.get("date_range", f"{product['date']}/{product['date']}"),
                }
            )
            continue

        try:
            safe_path = download_product(
                token, product_id, product_name, str(scenes_dir), expiry_time, username, password
            )

            base_id = get_scene_base_id(product_name)
            if base_id:
                existing_scene_ids.add(base_id)

            downloaded_scenes.append(
                {
                    "name": product_name,
                    "label": product.get("label", season),
                    "season": season,
                    "date": product["date"],
                    "size": product["size"],
                    "status": "downloaded",
                    "safe_path": safe_path,
                    "path": safe_path,
                    "bbox_used": product.get("bbox_used", bbox),
                    "date_range": product.get("date_range", f"{product['date']}/{product['date']}"),
                }
            )
            total_size += product["size"]

        except Exception as e:
            logger.error(f"  Failed to download {product_name}: {e}")
            downloaded_scenes.append(
                {
                    "name": product_name,
                    "season": season,
                    "date": product["date"],
                    "size": product["size"],
                    "status": "failed",
                    "error": str(e),
                }
            )

    # Generate summary
    downloaded_scenes = deduplicate_scenes(downloaded_scenes)
    successful = [
        s for s in downloaded_scenes if s["status"] in ["downloaded", "already_downloaded"]
    ]
    failed = [s for s in downloaded_scenes if s["status"] == "failed"]

    logger.info("=" * 60)
    logger.info(f"✓ Scenes downloaded: {len(successful)}/{len(all_selected_scenes)}")
    logger.info(f"  Region: {region_name}")
    logger.info(f"  Bounding box: {bbox}")
    logger.info(f"  Directory: {scenes_dir}")
    logger.info(f"  Total size: {total_size / (1024**3):.2f} GB")
    logger.info(
        f"  Successful: {len([s for s in downloaded_scenes if s['status'] == 'downloaded'])}"
    )
    logger.info(
        f"  Already present: {len([s for s in downloaded_scenes if s['status'] == 'already_downloaded'])}"
    )
    logger.info(f"  Failed: {len(failed)}")

    if failed:
        logger.warning("Failed scenes:")
        for scene in failed:
            logger.warning(
                f"  - {scene['name']} ({scene['season']}) : {scene.get('error', 'Unknown error')}"
            )

    logger.info("Scene list:")
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
        "scenes": downloaded_scenes,
    }
    save_manifest(scenes_dir, manifest)


if __name__ == "__main__":
    main()
