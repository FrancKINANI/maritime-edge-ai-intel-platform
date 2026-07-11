"""Global Fishing Watch annotation pipeline for phase0.

This module builds scene-level annotations by querying the Global Fishing
Watch API for SAR detections, AIS vessel presence, and AIS-off / dark vessel
events. It projects geographic detections onto Sentinel-1 tile metadata,
exports CVAT XML and YOLO label files, and writes scene-level reports.
"""

import csv
import json
import logging
import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# GFW API endpoints and dataset IDs
GFW_BASE_URL = "https://gateway.api.globalfishingwatch.org/v3"
GFW_VESSELS_SEARCH = f"{GFW_BASE_URL}/vessels/search"
GFW_EVENTS = f"{GFW_BASE_URL}/events"
GFW_4WINGS_REPORT = f"{GFW_BASE_URL}/4wings/report"
GFW_4WINGS_LAST_REPORT = f"{GFW_BASE_URL}/4wings/last-report"
GFW_REPORT = GFW_4WINGS_REPORT

AIS_PRESENCE_DATASET = "public-global-presence:latest"
# DEPRECATED per PH0-CORR-002: SAR_VESSEL_DETECTIONS_DATASET = "public-global-sar-vessel-detections:latest"
# This dataset returns grid cell aggregates, not individual vessel positions
AIS_OFF_DATASET = "public-global-gaps-events:latest"
FISHING_EVENTS_DATASET = "public-global-fishing-events:latest"

REQUEST_DELAY_SECONDS = 0.4
MAX_RETRIES = 3
BACKOFF_FACTOR = 2

ANNOTATION_LABELS = {
    "AIS_confirmed": 0,
    "visual_only": 1,
    "dark_vessel_candidate": 2,
}

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _get_headers(api_token: str) -> Dict[str, str]:
    if not api_token:
        raise ValueError("GFW API token is required")
    return {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _request_with_retry(
    method: str,
    url: str,
    headers: Dict[str, str],
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                if method.upper() == "GET":
                    response = client.get(url, headers=headers, params=params)
                else:
                    response = client.post(url, headers=headers, params=params, json=json_body)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            last_error = exc
            if status == 429 or status >= 500:
                wait = BACKOFF_FACTOR ** (attempt - 1)
                logger.warning(
                    "GFW request failed (%s). Retrying in %ss... (%s/%s)",
                    status,
                    wait,
                    attempt,
                    MAX_RETRIES,
                )
                time.sleep(wait)
                continue
            raise
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            last_error = exc
            wait = BACKOFF_FACTOR ** (attempt - 1)
            logger.warning(
                "GFW request error: %s. Retrying in %ss... (%s/%s)",
                exc,
                wait,
                attempt,
                MAX_RETRIES,
            )
            time.sleep(wait)
    raise RuntimeError(f"GFW request to {url} failed after {MAX_RETRIES} retries") from last_error


def _bbox_polygon(bbox: List[float]) -> Dict[str, Any]:
    lon_min, lat_min, lon_max, lat_max = bbox
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon_min, lat_min],
            [lon_max, lat_min],
            [lon_max, lat_max],
            [lon_min, lat_max],
            [lon_min, lat_min],
        ]],
    }


def _normalize_response_entries(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Normalize GFW API responses to a flat list of entry dicts.

    Handles these response formats (empirically verified):

    1. Standard flat list:
       {"entries": [{"lat": 33.0, ...}, {"lat": 34.0, ...}]}
       Used by /events, /vessels/search.

    2. Nested grouped (4wings/report AIS Presence):
       {"entries": [{"public-global-presence:v4.0": [{"lat": 33.0, ...}, ...]}]}
       The top-level "entries" is a list of one dict, where each key is a dataset
       identifier and the value is the actual list of vessel entries.
       This function flattens it by collecting all nested lists.

    3. Top-level grouped (less common):
       {"public-global-presence:v4.0": [{"lat": 33.0, ...}, ...]}
    """
    if response is None:
        return []
    # Try standard fields first (entries, results, data, rows, features)
    for field in ("entries", "results", "data", "rows", "features"):
        if field in response and isinstance(response[field], list):
            raw_list = response[field]
            # Check if this is a nested grouped format:
            # entries = [{dataset_key: [entry1, entry2, ...]}, ...]
            # Each element is a dict with a single key whose value is a list of dicts
            if (len(raw_list) > 0 and isinstance(raw_list[0], dict)
                    and any(isinstance(v, list) for v in raw_list[0].values())):
                flattened: List[Dict[str, Any]] = []
                for wrapper in raw_list:
                    if not isinstance(wrapper, dict):
                        continue
                    for sublist in wrapper.values():
                        if isinstance(sublist, list):
                            flattened.extend(sublist)
                if flattened:
                    return flattened
            return raw_list
    # Fallback: handle top-level grouped format {dataset_key: [entry, ...]}
    grouped_entries: List[Dict[str, Any]] = []
    for key, value in response.items():
        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
            grouped_entries.extend(value)
    if grouped_entries:
        return grouped_entries
    return []


def _extract_lat_lon(event: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    if event is None:
        return None, None
    if "lat" in event and "lon" in event:
        return float(event["lat"]), float(event["lon"])
    if "latitude" in event and "longitude" in event:
        return float(event["latitude"]), float(event["longitude"])
    geometry = event.get("geometry")
    if isinstance(geometry, dict):
        coords = geometry.get("coordinates")
        if isinstance(coords, list) and len(coords) >= 2:
            return float(coords[1]), float(coords[0])
    position = event.get("position") or event.get("location") or {}
    if isinstance(position, dict):
        if "lat" in position and "lon" in position:
            return float(position["lat"]), float(position["lon"])
        if "latitude" in position and "longitude" in position:
            return float(position["latitude"]), float(position["longitude"])
    return None, None

# ---------------------------------------------------------------------------
# GFW client
# ---------------------------------------------------------------------------


class GFWClient:
    """Global Fishing Watch API client."""

    def __init__(self, api_token: str) -> None:
        self.api_token = api_token
        self.headers = _get_headers(api_token)

    def _paginate_get(self, url: str, params: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        offset = 0
        while True:
            params["offset"] = offset
            response = _request_with_retry("GET", url, self.headers, params=params)
            page = _normalize_response_entries(response)
            if not page:
                break
            results.extend(page)
            if len(page) < limit:
                break
            offset += limit
            time.sleep(REQUEST_DELAY_SECONDS)
        return results

    def search_vessels(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        logger.info("Searching GFW vessels for query=%s", query)
        # GFW v3 API requires datasets[0] format (bracket notation) for query params
        params = {
            "query": query,
            "datasets[0]": AIS_PRESENCE_DATASET,
            "limit": min(limit, 50),
        }
        return _request_with_retry("GET", GFW_VESSELS_SEARCH, self.headers, params=params).get("entries", [])

    # DELETED: get_sar_detections() and related SAR functions per PH0-CORR-002
    # The SAR Vessel Detections dataset (public-global-sar-presence:latest) returns
    # grid cell aggregates, not individual vessel positions, making it structurally
    # unusable for this project. Replaced by AIS Vessel Presence + manual CVAT annotation.

    def get_ais_vessels(
        self,
        bbox: List[float],
        acquisition_time: str,
        window_hours: float = 1.0,
    ) -> List[Dict[str, Any]]:
        logger.info("Fetching GFW AIS presence for acquisition_time=%s", acquisition_time)
        acquisition_time = acquisition_time.rstrip("Z")
        dt = datetime.fromisoformat(acquisition_time)
        start_dt = dt - timedelta(hours=window_hours)
        end_dt = dt + timedelta(hours=window_hours)

        # GFW v3 /4wings/report POST: datasets[0], date-range, spatial-resolution,
        # temporal-resolution, and format go as query params. geojson and group-by go in the body.
        # Verified empirically — see data/QA.md for full verification report.
        query_params = {
            "datasets[0]": AIS_PRESENCE_DATASET,
            "date-range": f"{start_dt.date().isoformat()},{end_dt.date().isoformat()}",
            "spatial-resolution": "LOW",
            "temporal-resolution": "HOURLY",
            "format": "JSON",
        }
        body_params = {
            "geojson": _bbox_polygon(bbox),
            "group-by": "MMSI",
        }

        response = _request_with_retry("POST", GFW_REPORT, self.headers, params=query_params, json_body=body_params)
        return _normalize_response_entries(response)

    def gfw_get_ais_presence(
        self,
        bbox: List[float],
        date_start: str,
        date_end: str,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Fetch AIS Vessel Presence positions via the GFW API.

        NOTE: The exact endpoint for this specific dataset must be verified
        against the official GFW documentation. Do NOT assume it is the same
        endpoint as the gaps/AIS-off events endpoint — verify explicitly.

        Each returned position becomes an ANNOTATION SEED, not a final
        Ground Truth. It will be presented to the human annotator in CVAT
        as a suggestion to validate, not inserted directly into the final
        set of bounding boxes.

        Returns a list of dicts:
        {
          "lat": float, "lon": float,
          "timestamp": str,
          "mmsi": str | None,
          "vessel_name": str | None,
          "vessel_type": str | None,
          "source": "ais_presence_amorce",
          "requires_human_validation": True,
        }
        """
        logger.info("Fetching GFW AIS Vessel Presence for bbox=%s %s->%s", bbox, date_start, date_end)

        # GFW v3 API requires datasets and date-range as query params, not in POST body
        # Verified empirically: datasets[0] as query param passes validation
        # date-range format: YYYY-MM-DD,YYYY-MM-DD (also as query param per official docs)
        geometry = _bbox_polygon(bbox)
        # GFW v3 /4wings/report POST: datasets[0], date-range, spatial-resolution,
        # temporal-resolution, and format go as query params. geojson and limit go in the body.
        # Verified empirically — see data/QA.md for full verification report.
        query_params = {
            "datasets[0]": AIS_PRESENCE_DATASET,
            "date-range": f"{date_start},{date_end}",
            "spatial-resolution": "LOW",
            "temporal-resolution": "DAILY",
            "format": "JSON",
        }
        body_params = {
            "geojson": geometry,
            "limit": limit,
        }

        try:
            response = _request_with_retry("POST", GFW_REPORT, self.headers, params=query_params, json_body=body_params)
            entries = _normalize_response_entries(response)
            
            # Normalize entries to the expected format
            normalized = []
            for entry in entries:
                lat, lon = _extract_lat_lon(entry)
                if lat is None or lon is None:
                    continue
                    
                normalized.append({
                    "lat": lat,
                    "lon": lon,
                    "timestamp": entry.get("timestamp") or entry.get("date") or "",
                    "mmsi": entry.get("mmsi") or entry.get("MMSI"),
                    "vessel_name": entry.get("vessel_name") or entry.get("name"),
                    "vessel_type": entry.get("vessel_type") or entry.get("type"),
                    "source": "ais_presence_amorce",
                    "requires_human_validation": True,
                })
            
            logger.info(f"Retrieved {len(normalized)} AIS presence entries as annotation seeds")
            return normalized
            
        except Exception as e:
            logger.error(f"Failed to fetch AIS Vessel Presence: {e}")
            logger.warning("The endpoint for AIS Vessel Presence may need verification against GFW documentation")
            return []

    def get_dark_vessel_events(
        self,
        bbox: List[float],
        start_date: str,
        end_date: str,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        logger.info("Fetching GFW dark vessel events for bbox=%s %s->%s", bbox, start_date, end_date)
        params: Dict[str, Any] = {
            "datasets[0]": AIS_OFF_DATASET,
            "start-date": start_date,
            "end-date": end_date,
            "limit": limit,
            "geometry": json.dumps(_bbox_polygon(bbox)),
        }
        return self._paginate_get(GFW_EVENTS, params, limit)

# ---------------------------------------------------------------------------
# Scene metadata and projection helpers
# ---------------------------------------------------------------------------


def load_scene_metadata(scene_path: Union[str, Path], polarization: str = "vv") -> Dict[str, Any]:
    scene_path = Path(scene_path)
    if scene_path.is_file() and scene_path.name == "metadata.json":
        with open(scene_path, "r", encoding="utf-8") as f:
            return json.load(f)

    measurement_dir = scene_path / "measurement"
    if not measurement_dir.exists():
        raise FileNotFoundError(f"Scene measurement directory not found: {measurement_dir}")

    patterns = [
        f"*-{polarization.lower()}-*.tiff",
        f"*-{polarization.lower()}*.tiff",
        f"*{polarization.lower()}*.tiff",
        f"*.{polarization.lower()}*.tiff",
    ]
    tiff_files = []
    for pattern in patterns:
        tiff_files = sorted(measurement_dir.glob(pattern))
        if tiff_files:
            break

    if not tiff_files:
        raise FileNotFoundError("No GeoTIFF found for polarization '%s' in %s" % (polarization, scene_path))

    tiff_path = tiff_files[0]
    import rasterio

    with rasterio.open(tiff_path) as dataset:
        return {
            "scene_path": str(scene_path),
            "tiff_path": str(tiff_path),
            "width": dataset.width,
            "height": dataset.height,
            "transform": dataset.transform,
            "crs": str(dataset.crs) if dataset.crs else None,
        }


def load_tile_metadata(metadata_path: Union[str, Path]) -> Dict[str, Any]:
    metadata_path = Path(metadata_path)
    with open(metadata_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_scene_acquisition_time(scene_id: str) -> str:
    match = re.search(r"_(\d{8}T\d{6})_", scene_id)
    if not match:
        raise ValueError(f"Unable to parse acquisition time from scene_id '{scene_id}'")
    dt = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_scene_bbox(scene_metadata: Dict[str, Any]) -> List[float]:
    lat_min = float("inf")
    lon_min = float("inf")
    lat_max = float("-inf")
    lon_max = float("-inf")
    for tile in scene_metadata.get("tiles", []):
        geo = tile.get("geo_bbox")
        if not geo or len(geo) != 4:
            continue
        t_lat_min, t_lon_min, t_lat_max, t_lon_max = map(float, geo)
        lat_min = min(lat_min, t_lat_min)
        lon_min = min(lon_min, t_lon_min)
        lat_max = max(lat_max, t_lat_max)
        lon_max = max(lon_max, t_lon_max)
    if lat_min == float("inf"):
        raise ValueError("No valid tile geo_bbox found in metadata")
    return [lon_min, lat_min, lon_max, lat_max]


def point_in_tile(lat: float, lon: float, tile: Dict[str, Any]) -> bool:
    geo = tile.get("geo_bbox")
    if not geo or len(geo) != 4:
        return False
    lat_min, lon_min, lat_max, lon_max = map(float, geo)
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def latlon_to_tile_pixel(lat: float, lon: float, tile: Dict[str, Any], tile_size: int = 512) -> Tuple[float, float]:
    geo = tile.get("geo_bbox")
    if not geo or len(geo) != 4:
        raise ValueError("Tile metadata is missing geo_bbox")
    lat_min, lon_min, lat_max, lon_max = map(float, geo)

    if lon_max == lon_min or lat_max == lat_min:
        raise ValueError("Invalid tile geo_bbox with zero width or height")

    x = (lon - lon_min) / (lon_max - lon_min) * tile_size
    y = (lat_max - lat) / (lat_max - lat_min) * tile_size
    return x, y


def estimate_bbox_yolo(
    center_x: float,
    center_y: float,
    tile_size: int = 512,
    vessel_type: Optional[str] = None,
) -> Tuple[float, float, float, float]:
    length_m = 50.0
    if vessel_type:
        vt = vessel_type.lower()
        if any(keyword in vt for keyword in ["tanker", "cargo", "container"]):
            length_m = 150.0
        elif any(keyword in vt for keyword in ["fishing", "trawler", "longliner"]):
            length_m = 40.0
        elif any(keyword in vt for keyword in ["passenger", "pleasure", "yacht"]):
            length_m = 80.0

    approx_size_px = min(tile_size, max(8.0, length_m / 10.0))
    width = approx_size_px / tile_size
    height = max(0.02, approx_size_px / tile_size * 0.5)
    x_center = max(0.0, min(1.0, center_x / tile_size))
    y_center = max(0.0, min(1.0, center_y / tile_size))
    return x_center, y_center, width, height


def project_detections_to_tiles(
    detections: List[Dict[str, Any]],
    tiles: List[Dict[str, Any]],
    tile_size: Optional[int] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    if tile_size is None:
        tile_size = 512

    tile_annotations: Dict[str, List[Dict[str, Any]]] = {}
    projected = 0
    ignored = 0

    for detection in detections:
        lat, lon = _extract_lat_lon(detection)
        if lat is None or lon is None:
            ignored += 1
            continue
        matched_tile = False
        for tile in tiles:
            if not point_in_tile(lat, lon, tile):
                continue
            matched_tile = True
            tile_id = tile.get("tile_id")
            if not tile_id:
                continue
            try:
                px, py = latlon_to_tile_pixel(lat, lon, tile, tile_size=tile_size)
            except ValueError:
                continue
            vessel_type = None
            if isinstance(detection.get("vessel_info"), dict):
                vessel_type = detection["vessel_info"].get("type")
            vessel_type = vessel_type or detection.get("vessel_type") or detection.get("type")
            bbox = estimate_bbox_yolo(px, py, tile_size=tile_size, vessel_type=vessel_type)

            if detection.get("source") == "sar_detection":
                label = "AIS_confirmed" if detection.get("matched_to_ais") else "visual_only"
            elif detection.get("source") == "ais_presence":
                label = "AIS_confirmed"
            elif detection.get("source") == "ais_off":
                label = "dark_vessel_candidate"
            else:
                label = "visual_only"

            annotation = {
                "tile_id": tile_id,
                "lat": lat,
                "lon": lon,
                "pixel_x": px,
                "pixel_y": py,
                "bbox_yolo": [round(v, 6) for v in bbox],
                "label": label,
                "source": detection.get("source"),
                "timestamp": detection.get("timestamp") or detection.get("timestamp_off") or detection.get("start") or "",
                "confidence": detection.get("confidence") or detection.get("score"),
                "vessel_info": detection.get("vessel_info") or detection.get("vessel") or {},
            }
            tile_annotations.setdefault(tile_id, []).append(annotation)
            projected += 1
        if not matched_tile:
            ignored += 1

    logger.info("Projected %s detections to tiles, ignored %s detections outside tile coverage", projected, ignored)
    return tile_annotations

# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def export_csv(records: List[Dict[str, Any]], output_path: Union[str, Path]) -> str:
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        logger.warning("No records to export to CSV: %s", out_path)
        return str(out_path)
    fieldnames = list(records[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    logger.info("Exported %s records to CSV: %s", len(records), out_path)
    return str(out_path)


def export_geojson(records: List[Dict[str, Any]], output_path: Union[str, Path]) -> str:
    features: List[Dict[str, Any]] = []
    for record in records:
        lat, lon = _extract_lat_lon(record)
        if lat is None or lon is None:
            continue
        properties = {k: v for k, v in record.items() if k not in ("lat", "lon", "latitude", "longitude", "geometry")}
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat],
            },
            "properties": properties,
        })
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump({"type": "FeatureCollection", "features": features}, handle, indent=2, default=str)
    logger.info("Exported %s GeoJSON features to %s", len(features), out_path)
    return str(out_path)


def export_json(records: List[Dict[str, Any]], output_path: Union[str, Path]) -> str:
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2, default=str)
    logger.info("Exported %s JSON records to %s", len(records), out_path)
    return str(out_path)


def export_to_cvat_xml(
    scene_id: str,
    tile_annotations: Dict[str, List[Dict[str, Any]]],
    tiles: List[Dict[str, Any]],
    output_path: Union[str, Path],
) -> str:
    root = ET.Element("annotations")
    version = ET.SubElement(root, "version")
    version.text = "1.1"
    meta = ET.SubElement(root, "meta")
    task = ET.SubElement(meta, "task")
    ET.SubElement(task, "name").text = scene_id
    labels = ET.SubElement(task, "labels")
    for label_name in ["vessel_AIS_confirmed", "vessel_visual_only", "dark_vessel_candidate"]:
        label = ET.SubElement(labels, "label")
        ET.SubElement(label, "name").text = label_name
        ET.SubElement(label, "color").text = "#FF0000"

    tile_lookup = {tile.get("tile_id"): tile for tile in tiles}
    image_id = 0
    for tile_id, annotations in tile_annotations.items():
        if not annotations:
            continue
        tile = tile_lookup.get(tile_id, {})
        width = int(tile.get("tile_size", 512))
        height = int(tile.get("tile_size", 512))
        image_elem = ET.SubElement(
            root,
            "image",
            id=str(image_id),
            name=f"{tile_id}.npy",
            width=str(width),
            height=str(height),
        )
        for z, ann in enumerate(annotations):
            x_center, y_center, w, h = ann["bbox_yolo"]
            xtl = max(0.0, (x_center - w / 2) * width)
            ytl = max(0.0, (y_center - h / 2) * height)
            xbr = min(width, (x_center + w / 2) * width)
            ybr = min(height, (y_center + h / 2) * height)
            ET.SubElement(
                image_elem,
                "box",
                label=f"vessel_{ann['label']}",
                source="generated",
                xtl=f"{xtl:.1f}",
                ytl=f"{ytl:.1f}",
                xbr=f"{xbr:.1f}",
                ybr=f"{ybr:.1f}",
                occluded="0",
                z_order=str(z),
            )
        image_id += 1

    tree = ET.ElementTree(root)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(str(out_path), encoding="unicode", xml_declaration=True)
    logger.info("Exported CVAT XML with %s images to %s", image_id, out_path)
    return str(out_path)


def export_to_yolo_format(
    scene_id: str,
    tile_annotations: Dict[str, List[Dict[str, Any]]],
    tiles: List[Dict[str, Any]],
    output_dir: Union[str, Path],
) -> None:
    output_path = Path(output_dir)
    labels_dir = output_path / "labels"
    images_dir = output_path / "images"
    labels_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    tile_lookup = {tile.get("tile_id"): tile for tile in tiles}
    for tile_id, annotations in tile_annotations.items():
        if not annotations:
            continue
        label_path = labels_dir / f"{tile_id}.txt"
        with open(label_path, "w", encoding="utf-8") as handle:
            for ann in annotations:
                class_id = ANNOTATION_LABELS.get(ann["label"], 1)
                x_center, y_center, w, h = ann["bbox_yolo"]
                handle.write(f"{class_id} {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}\n")

        tile = tile_lookup.get(tile_id, {})
        npy_path = tile.get("npy_path")
        if not npy_path:
            continue
        npy_source = Path(npy_path)
        if not npy_source.exists():
            continue
        symlink_target = images_dir / f"{tile_id}.npy"
        try:
            if symlink_target.exists() or symlink_target.is_symlink():
                symlink_target.unlink()
            symlink_target.symlink_to(npy_source)
        except OSError:
            shutil.copy2(npy_source, symlink_target)

    logger.info("Exported YOLO labels for %s tiles to %s", len(tile_annotations), labels_dir)

# ---------------------------------------------------------------------------
# Annotation pipeline
# ---------------------------------------------------------------------------


def annotate_scene(
    metadata_path: Union[str, Path],
    gfw_client: GFWClient,
    output_dir: Union[str, Path],
    pipeline: str = "D",
) -> Dict[str, Any]:
    """
    Annotate a scene using the hybrid protocol per PH0-CORR-002:
    - Level 1: GFW AIS Vessel Presence as annotation seeds (amorce)
    - Level 2: AIS-off events as dark vessel candidates
    - All annotations require human validation in CVAT before becoming Ground Truth
    
    NOTE: SAR Vessel Detections dataset is NOT used as it returns grid cell
    aggregates, not individual vessel positions, making it structurally unusable.
    """
    metadata = load_tile_metadata(metadata_path)
    scene_id = metadata.get("scene_id")
    if not scene_id:
        raise ValueError("Tile metadata is missing scene_id")

    acquisition_time = metadata.get("acquisition_time")
    if not acquisition_time:
        acquisition_time = get_scene_acquisition_time(scene_id)

    bbox = get_scene_bbox(metadata)
    date_start = acquisition_time[:10]
    date_end = (datetime.fromisoformat(acquisition_time.rstrip("Z")) + timedelta(days=1)).date().isoformat()

    # Per PH0-CORR-002: Replace SAR detections with AIS Vessel Presence (Level 1)
    ais_presence_seeds = gfw_client.gfw_get_ais_presence(bbox, date_start, date_end)
    dark_vessel_candidates = gfw_client.get_dark_vessel_events(bbox, date_start, date_end)

    # Combine both sources with distinct labels for CVAT
    detections: List[Dict[str, Any]] = []
    detections.extend({**event, "source": "ais_presence_amorce", "label": "ais_presence_amorce"} for event in ais_presence_seeds)
    detections.extend({**event, "source": "ais_off_candidate", "label": "ais_off_candidate"} for event in dark_vessel_candidates)

    tile_size = metadata.get("tile_size", 512)
    tile_annotations = project_detections_to_tiles(detections, metadata.get("tiles", []), tile_size=tile_size)

    scene_output = Path(output_dir) / scene_id
    scene_output.mkdir(parents=True, exist_ok=True)

    cvat_path = scene_output / "cvat_annotation.xml"
    export_to_cvat_xml(scene_id, tile_annotations, metadata.get("tiles", []), cvat_path)
    export_to_yolo_format(scene_id, tile_annotations, metadata.get("tiles", []), scene_output)

    report = {
        "scene_id": scene_id,
        "pipeline": metadata.get("pipeline", pipeline),
        "acquisition_time": acquisition_time,
        "tile_count": len(metadata.get("tiles", [])),
        "annotated_tiles": len([tile_id for tile_id, anns in tile_annotations.items() if anns]),
        "ais_presence_seeds": len(ais_presence_seeds),
        "dark_vessel_candidates": len(dark_vessel_candidates),
        "total_annotations": sum(len(anns) for anns in tile_annotations.values()),
        "class_counts": {
            "ais_presence_amorce": sum(1 for anns in tile_annotations.values() for ann in anns if ann["label"] == "ais_presence_amorce"),
            "ais_off_candidate": sum(1 for anns in tile_annotations.values() for ann in anns if ann["label"] == "ais_off_candidate"),
        },
        "protocol": "PH0-CORR-002_hybrid",
        "note": "All annotations require human validation in CVAT before becoming Ground Truth",
    }
    report_path = scene_output / "annotation_report.json"
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    logger.info("Saved annotation report to %s", report_path)
    return report


def annotate_all_scenes(
    tiles_root: Union[str, Path],
    gfw_client: GFWClient,
    output_dir: Union[str, Path],
    pipeline: str = "D",
) -> Dict[str, Any]:
    tiles_root = Path(tiles_root)
    metadata_paths = sorted(tiles_root.glob("**/metadata.json"))
    summary = {
        "scenes": [],
        "global_counts": {"ais_presence_amorce": 0, "ais_off_candidate": 0},
        "total_annotations": 0,
        "protocol": "PH0-CORR-002_hybrid",
    }
    logger.info("Found %s metadata files under %s", len(metadata_paths), tiles_root)
    for metadata_path in metadata_paths:
        try:
            report = annotate_scene(metadata_path, gfw_client, output_dir, pipeline=pipeline)
        except Exception as exc:
            logger.error("Failed to annotate %s: %s", metadata_path, exc)
            continue
        summary["scenes"].append(report)
        for label, count in report["class_counts"].items():
            summary["global_counts"][label] += count
        summary["total_annotations"] += report["total_annotations"]

    summary_path = Path(output_dir) / "global_summary.json"
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    logger.info("Saved global summary to %s", summary_path)
    return summary


def test_gfw_connection(client: GFWClient) -> None:
    logger.info("Running GFW connectivity test (PH0-CORR-002 protocol)")
    bbox = [-17.0, 27.0, -1.0, 36.0]
    end = datetime.utcnow().date()
    start = end - timedelta(days=2)
    try:
        # Test AIS Vessel Presence (Level 1)
        ais_seeds = client.gfw_get_ais_presence([bbox[0], bbox[1], bbox[2], bbox[3]], start.isoformat(), end.isoformat(), limit=10)
        logger.info("Connectivity OK, retrieved %s AIS presence seeds", len(ais_seeds))
        
        # Test Dark vessel events (Level 2)
        dark_candidates = client.get_dark_vessel_events([bbox[0], bbox[1], bbox[2], bbox[3]], start.isoformat(), end.isoformat(), limit=10)
        logger.info("Connectivity OK, retrieved %s dark vessel candidates", len(dark_candidates))
    except Exception as exc:
        logger.error("GFW connectivity test failed: %s", exc)
        raise

def test_sar_endpoint(token: str) -> None:
    """
    DEPRECATED per PH0-CORR-002.
    
    The SAR Vessel Detections dataset (public-global-sar-presence:latest) returns
    grid cell aggregates, not individual vessel positions, making it structurally
    unusable for this project. Use test_gfw_connection() instead to test the
    new hybrid protocol (AIS Vessel Presence + Dark Vessel Events).
    """
    logger.warning("test_sar_endpoint() is DEPRECATED per PH0-CORR-002")
    logger.warning("SAR Vessel Detections dataset returns grid aggregates, not individual positions")
    logger.warning("Use test_gfw_connection() to test the new hybrid protocol")
    raise NotImplementedError("SAR endpoint testing deprecated per PH0-CORR-002")



# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    load_dotenv()
    parser = argparse.ArgumentParser(description="Global Fishing Watch annotation builder")
    parser.add_argument("--tiles-root", default=None, help="Root folder for tile metadata search")
    parser.add_argument("--output-dir", default=None, help="Output folder for annotations")
    parser.add_argument("--metadata", default=None, help="Path to a scene metadata.json file")
    parser.add_argument("--pipeline", default="D", help="Pipeline name to use when annotating")
    parser.add_argument("--all", action="store_true", help="Annotate all scenes under tiles root")
    parser.add_argument("--test", action="store_true", help="Run a GFW API connectivity test")
    parser.add_argument("--test-sar", action="store_true", help="Run isolated SAR endpoint test")

    args = parser.parse_args()

    token = os.getenv("GFW_API_TOKEN")
    if not token:
        logger.error("GFW_API_TOKEN must be set in the environment or .env file.")
        return

    tiles_root = Path(args.tiles_root or Path(__file__).parent / "data" / "tiles")
    output_dir = Path(args.output_dir or Path(__file__).parent / "data" / "annotations")
    output_dir.mkdir(parents=True, exist_ok=True)

    client = GFWClient(token)

    if args.test_sar:
        test_sar_endpoint(token)
        return

    if args.test:
        test_gfw_connection(client)
        return

    if args.all:
        annotate_all_scenes(tiles_root, client, output_dir, pipeline=args.pipeline)
        return

    if not args.metadata:
        logger.error("Either --metadata or --all must be provided")
        return

    annotate_scene(Path(args.metadata), client, output_dir, pipeline=args.pipeline)


if __name__ == "__main__":
    main()
