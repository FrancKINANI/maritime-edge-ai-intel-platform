import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import download_scenes

SCENE_A = "S1A_IW_GRDH_1SDV_20240107T064657_20240107T064719_051997_06488E_B2F9"
SCENE_B = "S1D_IW_GRDH_1SDV_20260711T061903_20260711T061928_003622_00673D_224C"


def test_get_scene_base_id_normalizes_cog_and_standard_variants():
    standard_name = SCENE_A
    cog_name = f"{SCENE_A}_COG"

    assert download_scenes.get_scene_base_id(standard_name) == "051997_06488E_B2F9"
    assert download_scenes.get_scene_base_id(cog_name) == "051997_06488E_B2F9"


def test_is_scene_downloaded_detects_existing_scene_by_base_id(tmp_path):
    existing_scene = tmp_path / f"{SCENE_A}.SAFE"
    existing_scene.mkdir()

    assert download_scenes.is_scene_downloaded(
        tmp_path,
        f"{SCENE_A}_COG",
        existing_scene_ids={"051997_06488E_B2F9"},
    )


def test_is_scene_downloaded_skips_duplicates_across_regions(tmp_path):
    existing_scene = tmp_path / f"{SCENE_A}.SAFE"
    existing_scene.mkdir()

    assert download_scenes.is_scene_downloaded(
        tmp_path,
        f"{SCENE_A}_COG",
        existing_scene_ids={"051997_06488E_B2F9"},
    )
    assert download_scenes.is_scene_downloaded(
        tmp_path,
        SCENE_A,
        existing_scene_ids={"051997_06488E_B2F9"},
    )


def test_write_target_trace_is_colocated_with_scene_and_includes_scene_id(tmp_path):
    safe_dir = tmp_path / f"{SCENE_A}.SAFE"
    safe_dir.mkdir()
    cell_bbox = [-6.0, 35.5, -5.5, 36.0]

    trace_path = download_scenes.write_target_trace(
        safe_dir,
        cell_index=413,
        cell_bbox=cell_bbox,
        scene_id=SCENE_A,
        density_rank=1,
        ais_count=120,
    )

    assert trace_path == safe_dir / "target_trace.json"
    assert trace_path.exists()
    # Must NOT write a shared parent-level file
    assert not (tmp_path / "target_trace.json").exists()

    with open(trace_path, encoding="utf-8") as f:
        trace = json.load(f)

    assert trace["scene_id"] == SCENE_A
    assert trace["safe_dir"] == f"{SCENE_A}.SAFE"
    assert trace["target_density_cell_index"] == 413
    assert trace["target_cell_bbox"] == cell_bbox
    assert trace["density_rank"] == 1
    assert trace["ais_count"] == 120
    assert trace["protocol"] == "PH0-CORR-002_density_targeted"


def test_write_scene_target_trace_registers_index_per_scene(tmp_path):
    scenes_dir = tmp_path
    safe_a = scenes_dir / f"{SCENE_A}.SAFE"
    safe_b = scenes_dir / f"{SCENE_B}.SAFE"
    safe_a.mkdir()
    safe_b.mkdir()

    download_scenes.write_scene_target_trace(
        scenes_dir, safe_a, 10, [-10.0, 30.0, -9.5, 30.5], density_rank=1, ais_count=50
    )
    download_scenes.write_scene_target_trace(
        scenes_dir, safe_b, 20, [-6.0, 35.5, -5.5, 36.0], density_rank=2, ais_count=40
    )

    # Each scene has its own trace
    assert (safe_a / "target_trace.json").exists()
    assert (safe_b / "target_trace.json").exists()

    index_path = scenes_dir / download_scenes.TARGET_TRACES_INDEX_NAME
    assert index_path.exists()
    with open(index_path, encoding="utf-8") as f:
        index = json.load(f)

    assert set(index["scenes"].keys()) == {SCENE_A, SCENE_B}
    assert index["scenes"][SCENE_A]["trace_path"] == f"{SCENE_A}.SAFE/target_trace.json"
    assert index["scenes"][SCENE_A]["target_density_cell_index"] == 10
    assert index["scenes"][SCENE_B]["target_density_cell_index"] == 20
    # No ambiguity: different scenes map to different cells
    assert (
        index["scenes"][SCENE_A]["target_density_cell_index"] != index["scenes"][SCENE_B]["target_density_cell_index"]
    )


def test_resolve_safe_dir_finds_scene_by_base_id(tmp_path):
    safe_dir = tmp_path / f"{SCENE_A}.SAFE"
    safe_dir.mkdir()

    resolved = download_scenes.resolve_safe_dir(tmp_path, f"{SCENE_A}_COG")
    assert resolved == safe_dir

    resolved_exact = download_scenes.resolve_safe_dir(tmp_path, SCENE_A)
    assert resolved_exact == safe_dir
