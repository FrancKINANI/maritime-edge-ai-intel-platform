from pathlib import Path
import shutil
import sys

import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.append(str(Path(__file__).resolve().parents[1]))

import gfw_annotations


def test_load_scene_metadata_reads_geotiff_dimensions(tmp_path):
    scene_dir = tmp_path / "scene.SAFE"
    measurement_dir = scene_dir / "measurement"
    measurement_dir.mkdir(parents=True)

    tiff_path = measurement_dir / "S1A_IW_GRDH_1SDV_test-vv.tiff"
    with rasterio.open(
        tiff_path,
        "w",
        driver="GTiff",
        height=2,
        width=3,
        count=1,
        dtype="uint8",
        transform=from_origin(0, 1, 1, 1),
    ) as ds:
        ds.write(np.arange(6, dtype=np.uint8).reshape(2, 3), 1)

    metadata = gfw_annotations.load_scene_metadata(scene_dir, polarization="vv")

    assert metadata["width"] == 3
    assert metadata["height"] == 2
    assert metadata["scene_path"] == str(scene_dir)
