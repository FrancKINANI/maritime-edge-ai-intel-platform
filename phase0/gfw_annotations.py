"""Global Fishing Watch AIS Annotation Builder.

Purpose:
    Retrieve historical AIS vessel positions and SAR detections from the
    Global Fishing Watch API v3, then project them onto Sentinel-1 image
    coordinates for ground-truth annotation seeding.

Inputs:
    - GFW_API_TOKEN (from environment or .env)
    - Bounding box and date range for the region of interest
    - Optional: scene metadata (rasterio profile) for pixel projection

Outputs:
    - AIS records as CSV, GeoJSON, and JSON
    - Projected annotations for CVAT (XML format)

API Reference:
    - Base URL: https://gateway.api.globalfishingwatch.org/v3
    - Authentication: Bearer token (JWT)
    - Vessel search: /v3/vessels/search
    - Events: /v3/events (fishing, loitering, encounters, port visits, gaps)
    - Array params use bracket notation: datasets[0]=..., datasets[1]=...
"""

import csv
import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Constants
GFW_BASE_URL = "https://gateway.api.globalfishingwatch.org/v3"
GFW_VESSELS_SEARCH = f"{GFW_BASE_URL}/vessels/search"
GFW_EVENTS = f"{GFW_BASE_URL}/events"

# Default dataset IDs for GFW API v3
DEFAULT_AIS_DATASET = "public-global-vessel-identity:latest"
DEFAULT_FISHING_EVENTS_DATASET = "public-global-fishing-events:latest"
DEFAULT_SAR_DATASET = "public-global-sar-vessel-detections:latest"

# Rate limiting: GFW recommends max ~2 requests/second
REQUEST_DELAY_SECONDS = 0.5


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _get_headers(token: str) -> Dict[str, str]:
    """Builds standard authorization headers for GFW API requests.

    Args:
        token: GFW API Bearer token (JWT).

    Returns:
        Dict with Authorization and User-Agent headers.
    """
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": "maritime-edge-ai-platform/1.0",
        "Accept": "application/json",
    }


def _request_with_retry(
    method: str,
    url: str,
    headers: Dict[str, str],
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """Makes an HTTP request with exponential backoff retry logic.

    Args:
        method: HTTP method ('GET' or 'POST').
        url: Target URL.
        headers: Request headers.
        params: Query parameters.
        json_body: JSON body for POST requests.
        max_retries: Maximum number of retry attempts.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        httpx.HTTPStatusError: After exhausting all retries.
    """
    for attempt in range(max_retries):
        try:
            with httpx.Client() as client:
                if method.upper() == "GET":
                    response = client.get(
                        url, headers=headers, params=params, timeout=timeout
                    )
                else:
                    response = client.post(
                        url,
                        headers=headers,
                        params=params,
                        json=json_body,
                        timeout=timeout,
                    )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = 2 ** attempt * 2
                logger.warning(
                    f"Rate limited (429). Retrying in {wait}s... "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait)
            elif e.response.status_code >= 500:
                wait = 2 ** attempt
                logger.warning(
                    f"Server error {e.response.status_code}. Retrying in {wait}s..."
                )
                time.sleep(wait)
            else:
                raise
        except httpx.TimeoutException:
            wait = 2 ** attempt
            logger.warning(f"Request timed out. Retrying in {wait}s...")
            time.sleep(wait)

    raise RuntimeError(f"Request to {url} failed after {max_retries} retries.")


# ---------------------------------------------------------------------------
# GFW API functions
# ---------------------------------------------------------------------------


def search_vessels(
    token: str,
    query: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Searches for vessels in the GFW identity database.

    Args:
        token: GFW API Bearer token.
        query: Search string (MMSI, IMO, vessel name).
        limit: Maximum number of results (max 50 per GFW docs).

    Returns:
        List of vessel identity records.
    """
    logger.info(f"Searching GFW vessels: query='{query}', limit={limit}")
    params = {
        "query": query,
        "datasets[0]": DEFAULT_AIS_DATASET,
        "limit": limit,
    }
    headers = _get_headers(token)
    data = _request_with_retry("GET", GFW_VESSELS_SEARCH, headers, params=params)
    entries = data.get("entries", [])
    logger.info(f"Found {len(entries)} vessel(s) matching '{query}'")
    return entries


def get_ais_presence(
    token: str,
    bbox: List[float],
    start_date: str,
    end_date: str,
    event_types: Optional[List[str]] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Fetches AIS-based events from GFW within a spatial-temporal window.

    Uses the /v3/events endpoint to retrieve fishing events, encounters,
    loitering, port visits, or AIS gap events.

    Args:
        token: GFW API Bearer token.
        bbox: Geographic bounding box [lon_min, lat_min, lon_max, lat_max].
        start_date: ISO8601 start date (e.g., '2024-01-01').
        end_date: ISO8601 end date (e.g., '2024-01-07').
        event_types: List of event types to query. Defaults to ['FISHING'].
            Valid values: FISHING, LOITERING, ENCOUNTER, PORT_VISIT, GAP.
        limit: Maximum number of events to return per request.

    Returns:
        List of AIS event records.
    """
    if event_types is None:
        event_types = ["FISHING"]

    logger.info(
        f"Fetching AIS events from GFW: bbox={bbox}, "
        f"dates={start_date}→{end_date}, types={event_types}"
    )

    lon_min, lat_min, lon_max, lat_max = bbox

    # Build params with v3 array notation
    params: Dict[str, Any] = {
        "datasets[0]": DEFAULT_FISHING_EVENTS_DATASET,
        "start-date": start_date,
        "end-date": end_date,
        "limit": limit,
    }

    # Add event types with array notation
    for i, et in enumerate(event_types):
        params[f"event-types[{i}]"] = et.upper()

    # Spatial filter as geometry (GFW expects this format)
    # For bounding box, we pass as a polygon in the geometry parameter
    params["geometry"] = json.dumps({
        "type": "Polygon",
        "coordinates": [[
            [lon_min, lat_min],
            [lon_max, lat_min],
            [lon_max, lat_max],
            [lon_min, lat_max],
            [lon_min, lat_min],
        ]],
    })

    headers = _get_headers(token)

    all_events: List[Dict[str, Any]] = []
    offset = 0

    # Paginate through results
    while True:
        params["offset"] = offset
        time.sleep(REQUEST_DELAY_SECONDS)

        data = _request_with_retry("GET", GFW_EVENTS, headers, params=params)
        entries = data.get("entries", [])

        if not entries:
            break

        all_events.extend(entries)
        logger.info(f"  Fetched {len(entries)} events (total: {len(all_events)})")

        if len(entries) < limit:
            break
        offset += limit

    logger.info(f"Total AIS events retrieved: {len(all_events)}")
    return all_events


def get_sar_detections(
    token: str,
    bbox: List[float],
    start_date: str,
    end_date: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Retrieves GFW's archived SAR vessel detections (matched/unmatched to AIS).

    These are detections from GFW's own SAR processing pipeline, which can
    serve as supplementary ground truth.

    Args:
        token: GFW API Bearer token.
        bbox: Geographic bounding box [lon_min, lat_min, lon_max, lat_max].
        start_date: ISO8601 start date.
        end_date: ISO8601 end date.
        limit: Maximum number of results.

    Returns:
        List of SAR detection event records.
    """
    logger.info(f"Fetching GFW SAR detections: bbox={bbox}, {start_date}→{end_date}")

    lon_min, lat_min, lon_max, lat_max = bbox

    params: Dict[str, Any] = {
        "datasets[0]": DEFAULT_SAR_DATASET,
        "start-date": start_date,
        "end-date": end_date,
        "limit": limit,
    }

    params["geometry"] = json.dumps({
        "type": "Polygon",
        "coordinates": [[
            [lon_min, lat_min],
            [lon_max, lat_min],
            [lon_max, lat_max],
            [lon_min, lat_max],
            [lon_min, lat_min],
        ]],
    })

    headers = _get_headers(token)
    data = _request_with_retry("GET", GFW_EVENTS, headers, params=params)
    entries = data.get("entries", [])
    logger.info(f"Retrieved {len(entries)} SAR detection records")
    return entries


# ---------------------------------------------------------------------------
# Projection & annotation
# ---------------------------------------------------------------------------


def project_ais_to_image(
    ais_positions: List[Dict[str, Any]],
    scene_metadata: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Projects geographic lat/lon AIS positions to SAR image pixel coordinates.

    Uses the rasterio affine transform from the scene metadata to convert
    WGS84 coordinates to (row, col) pixel positions.

    Args:
        ais_positions: List of dicts, each containing at minimum 'lat' and 'lon' keys.
        scene_metadata: Dict containing a rasterio-compatible 'transform' and
            'width'/'height' keys.

    Returns:
        List of dicts with added 'pixel_x', 'pixel_y' fields.
        Only positions that fall within the image bounds are returned.
    """
    from rasterio.transform import AffineTransformer

    transform = scene_metadata.get("transform")
    width = scene_metadata.get("width")
    height = scene_metadata.get("height")

    if transform is None or width is None or height is None:
        raise ValueError(
            "scene_metadata must contain 'transform', 'width', and 'height'."
        )

    transformer = AffineTransformer(transform)
    projected = []

    for pos in ais_positions:
        lat = pos.get("lat") or pos.get("latitude")
        lon = pos.get("lon") or pos.get("longitude")
        if lat is None or lon is None:
            continue

        # Convert geo coords to pixel coords
        col, row = transformer.rowcol(lon, lat)

        # Keep only positions within the image bounds
        if 0 <= row < height and 0 <= col < width:
            proj = dict(pos)
            proj["pixel_x"] = int(col)
            proj["pixel_y"] = int(row)
            projected.append(proj)

    logger.info(
        f"Projected {len(projected)}/{len(ais_positions)} AIS positions to image pixels"
    )
    return projected


# ---------------------------------------------------------------------------
# Export functions
# ---------------------------------------------------------------------------


def export_csv(records: List[Dict[str, Any]], output_path: str) -> str:
    """Exports AIS records to a CSV file.

    Args:
        records: List of AIS record dicts.
        output_path: Output file path.

    Returns:
        Absolute path to the saved CSV file.
    """
    if not records:
        logger.warning("No records to export to CSV.")
        return output_path

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(records[0].keys())
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

    logger.info(f"Exported {len(records)} records to CSV: {out}")
    return str(out)


def export_geojson(records: List[Dict[str, Any]], output_path: str) -> str:
    """Exports AIS records to a GeoJSON FeatureCollection file.

    Args:
        records: List of AIS record dicts with 'lat'/'lon' keys.
        output_path: Output file path.

    Returns:
        Absolute path to the saved GeoJSON file.
    """
    features = []
    for rec in records:
        lat = rec.get("lat") or rec.get("latitude")
        lon = rec.get("lon") or rec.get("longitude")
        if lat is None or lon is None:
            continue

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(lon), float(lat)],
            },
            "properties": {
                k: v
                for k, v in rec.items()
                if k not in ("lat", "lon", "latitude", "longitude")
            },
        }
        features.append(feature)

    geojson = {"type": "FeatureCollection", "features": features}

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2, default=str)

    logger.info(f"Exported {len(features)} features to GeoJSON: {out}")
    return str(out)


def export_json(records: List[Dict[str, Any]], output_path: str) -> str:
    """Exports raw AIS records to a JSON file.

    Args:
        records: List of AIS record dicts.
        output_path: Output file path.

    Returns:
        Absolute path to the saved JSON file.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, default=str)

    logger.info(f"Exported {len(records)} records to JSON: {out}")
    return str(out)


def export_cvat_annotations(
    projected_positions: List[Dict[str, Any]],
    output_path: str,
    image_name: str = "sentinel1_scene",
    image_width: int = 0,
    image_height: int = 0,
    box_size: int = 32,
) -> str:
    """Exports projected pixel positions to CVAT XML format.

    Creates approximate bounding box annotations centered on each projected
    AIS position. These serve as annotation seeds to be refined manually
    in CVAT.

    Args:
        projected_positions: List of dicts with 'pixel_x', 'pixel_y' keys.
        output_path: Output XML file path.
        image_name: Name of the image in CVAT.
        image_width: Image width in pixels.
        image_height: Image height in pixels.
        box_size: Side length of the generated bounding boxes in pixels.

    Returns:
        Absolute path to the saved CVAT XML file.
    """
    annotations = ET.Element("annotations")
    version = ET.SubElement(annotations, "version")
    version.text = "1.1"

    meta = ET.SubElement(annotations, "meta")
    task = ET.SubElement(meta, "task")
    ET.SubElement(task, "name").text = "AIS_annotations"
    ET.SubElement(task, "size").text = str(len(projected_positions))

    # Image element
    image_elem = ET.SubElement(
        annotations,
        "image",
        id="0",
        name=image_name,
        width=str(image_width),
        height=str(image_height),
    )

    half = box_size // 2
    for idx, pos in enumerate(projected_positions):
        px = pos.get("pixel_x", 0)
        py = pos.get("pixel_y", 0)

        xtl = max(0, px - half)
        ytl = max(0, py - half)
        xbr = min(image_width, px + half) if image_width > 0 else px + half
        ybr = min(image_height, py + half) if image_height > 0 else py + half

        ET.SubElement(
            image_elem,
            "box",
            label="vessel",
            source="AIS",
            xtl=f"{xtl:.1f}",
            ytl=f"{ytl:.1f}",
            xbr=f"{xbr:.1f}",
            ybr=f"{ybr:.1f}",
            occluded="0",
            z_order=str(idx),
        )

    tree = ET.ElementTree(annotations)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    ET.indent(tree, space="  ")
    tree.write(str(out), encoding="unicode", xml_declaration=True)

    logger.info(
        f"Exported {len(projected_positions)} CVAT annotations to: {out}"
    )
    return str(out)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Command-line entry point for standalone AIS data retrieval."""
    import argparse

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Global Fishing Watch AIS Annotation Builder"
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        default=[-17.0, 27.0, -1.0, 36.0],
        metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX"),
        help="Bounding box (default: Morocco)",
    )
    parser.add_argument(
        "--start", required=True, help="Start date (ISO8601, e.g. 2024-01-01)"
    )
    parser.add_argument(
        "--end", required=True, help="End date (ISO8601, e.g. 2024-01-07)"
    )
    parser.add_argument(
        "--event-types",
        nargs="+",
        default=["FISHING"],
        help="Event types to query (default: FISHING)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: phase0/data/annotations/)",
    )

    args = parser.parse_args()

    token = os.getenv("GFW_API_TOKEN")
    if not token:
        logger.error("GFW_API_TOKEN must be set in the environment or .env file.")
        return

    output_dir = args.output_dir or str(
        Path(__file__).parent / "data" / "annotations"
    )

    try:
        # Fetch AIS events
        events = get_ais_presence(
            token=token,
            bbox=args.bbox,
            start_date=args.start,
            end_date=args.end,
            event_types=args.event_types,
        )

        # Flatten events to simple records with lat/lon
        records = []
        for event in events:
            position = event.get("position", {})
            record = {
                "event_id": event.get("id", ""),
                "type": event.get("type", ""),
                "start": event.get("start", ""),
                "end": event.get("end", ""),
                "lat": position.get("lat"),
                "lon": position.get("lon"),
                "vessel_id": event.get("vessel", {}).get("id", ""),
                "vessel_name": event.get("vessel", {}).get("name", ""),
                "mmsi": event.get("vessel", {}).get("ssvid", ""),
            }
            records.append(record)

        logger.info(f"Extracted {len(records)} AIS records from events")

        # Export in multiple formats
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_csv(records, f"{output_dir}/ais_events_{timestamp}.csv")
        export_geojson(records, f"{output_dir}/ais_events_{timestamp}.geojson")
        export_json(records, f"{output_dir}/ais_events_{timestamp}.json")

        # Also fetch SAR detections
        sar = get_sar_detections(
            token=token,
            bbox=args.bbox,
            start_date=args.start,
            end_date=args.end,
        )
        if sar:
            export_json(sar, f"{output_dir}/sar_detections_{timestamp}.json")

    except Exception as e:
        logger.error(f"GFW annotation pipeline failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()

