# phase0/gfw_annotations.py
"""Global Fishing Watch AIS Annotation Builder.

Interfaces with the GFW APIs to extract historical vessel AIS positions and
re-project them into Sentinel-1 pixel coordinates to auto-generate ground-truth annotations.
"""

from typing import List, Dict, Any


def get_ais_presence(token: str, bbox: List[float], start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Fetches AIS vessel presence data from the GFW API within target spatial-temporal window.

    Args:
        token (str): Global Fishing Watch API authorization token.
        bbox (List[float]): Search bounding box [lon_min, lat_min, lon_max, lat_max].
        start_date (str): ISO8601 start date.
        end_date (str): ISO8601 end date.

    Returns:
        List[Dict[str, Any]]: List of historical vessel presence records.

    Raises:
        NotImplementedError: As this is a skeleton structure.
    """
    raise NotImplementedError("GFW AIS query logic not implemented yet.")


def get_sar_detections(token: str, bbox: List[float], start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Retrieves GFW's archived SAR vessel detections (matched/unmatched to AIS).

    Args:
        token (str): Global Fishing Watch API authorization token.
        bbox (List[float]): Search bounding box [lon_min, lat_min, lon_max, lat_max].
        start_date (str): ISO8601 start date.
        end_date (str): ISO8601 end date.

    Returns:
        List[Dict[str, Any]]: List of GFW SAR detection records.

    Raises:
        NotImplementedError: As this is a skeleton structure.
    """
    raise NotImplementedError("GFW SAR detections query logic not implemented yet.")


def project_ais_to_image(ais_positions: List[Dict[str, Any]], scene_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Translates geographic lat/lon AIS coordinates to SAR image pixel coordinates (X, Y).

    Args:
        ais_positions (List[Dict[str, Any]]): List of AIS spatial positions.
        scene_metadata (Dict[str, Any]): Coordinate reference system (CRS) metadata of SAR image.

    Returns:
        List[Dict[str, Any]]: Projected pixel coordinates of vessels.

    Raises:
        NotImplementedError: As this is a skeleton structure.
    """
    raise NotImplementedError("Geospatial pixel projection logic not implemented yet.")


def export_cvat_annotations(projected_positions: List[Dict[str, Any]], output_path: str) -> None:
    """Exports pixel projected annotations to CVAT XML (YOLO-compatible ground truth format).

    Args:
        projected_positions (List[Dict[str, Any]]): List of projected vessel coordinates.
        output_path (str): File destination path.

    Raises:
        NotImplementedError: As this is a skeleton structure.
    """
    raise NotImplementedError("CVAT annotation exporter logic not implemented yet.")
