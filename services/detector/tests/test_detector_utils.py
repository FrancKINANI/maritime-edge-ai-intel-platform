"""Unit tests for detector utility functions (nms, xywh2xyxy).

These are pure functions testable without ONNX Runtime or any external dependency.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np

# Load detector main.py by absolute path so concurrent pytest collection of
# other services/*/main.py modules cannot shadow the name "main".
_DETECTOR_MAIN = Path(__file__).resolve().parents[1] / "main.py"
_spec = importlib.util.spec_from_file_location("detector_main", _DETECTOR_MAIN)
_detector_main = importlib.util.module_from_spec(_spec)
sys.modules["detector_main"] = _detector_main
assert _spec.loader is not None
_spec.loader.exec_module(_detector_main)
nms = _detector_main.nms
xywh2xyxy = _detector_main.xywh2xyxy


def test_xywh2xyxy_center_box():
    """Test conversion of center-formatted box to corner format."""
    # Box centered at (50, 50) with width=20, height=40
    result = xywh2xyxy((50.0, 50.0, 20.0, 40.0))
    # Expected: x1=50-10=40, y1=50-20=30, x2=50+10=60, y2=50+20=70
    assert len(result) == 4
    assert np.isclose(result[0], 40.0)  # x1
    assert np.isclose(result[1], 30.0)  # y1
    assert np.isclose(result[2], 60.0)  # x2
    assert np.isclose(result[3], 70.0)  # y2


def test_xywh2xyxy_origin_box():
    """Test conversion for a box at the origin."""
    result = xywh2xyxy((0.0, 0.0, 10.0, 10.0))
    assert np.isclose(result[0], -5.0)
    assert np.isclose(result[1], -5.0)
    assert np.isclose(result[2], 5.0)
    assert np.isclose(result[3], 5.0)


def test_nms_basic():
    """Test NMS with overlapping boxes — highest score should be kept."""
    boxes = [[0, 0, 100, 100], [10, 10, 90, 90], [200, 200, 300, 300]]
    scores = [0.9, 0.8, 0.7]
    keep = nms(boxes, scores, iou_threshold=0.45)
    # Box 0 (score 0.9) and box 1 (score 0.8) overlap heavily — one should be suppressed
    # Box 2 (score 0.7) is far away — should be kept
    assert len(keep) == 2
    assert 0 in keep  # Highest score box always kept
    assert 2 in keep  # Non-overlapping box kept
    # Box 1 should be suppressed (IoU with box 0 is high)
    assert 1 not in keep


def test_nms_no_overlap():
    """Test NMS with non-overlapping boxes — all should be kept."""
    boxes = [[0, 0, 10, 10], [100, 100, 110, 110], [200, 200, 210, 210]]
    scores = [0.5, 0.7, 0.9]
    keep = nms(boxes, scores, iou_threshold=0.5)
    assert len(keep) == 3
    assert 0 in keep and 1 in keep and 2 in keep


def test_nms_empty():
    """Test NMS with empty inputs."""
    keep = nms([], [], iou_threshold=0.5)
    assert keep == []


def test_nms_single_box():
    """Test NMS with a single box."""
    boxes = [[0, 0, 100, 100]]
    scores = [0.95]
    keep = nms(boxes, scores)
    assert keep == [0]


def test_nms_iou_threshold():
    """Test NMS with different IoU thresholds."""
    boxes = [[0, 0, 100, 100], [10, 10, 90, 90]]
    scores = [0.9, 0.8]
    # With strict IoU (0.1), almost any overlap suppresses — box 1 suppressed
    keep_strict = nms(boxes, scores, iou_threshold=0.1)
    assert len(keep_strict) == 1
    # With lenient IoU (0.9), overlap is below threshold — both kept
    keep_lenient = nms(boxes, scores, iou_threshold=0.9)
    assert len(keep_lenient) == 2
