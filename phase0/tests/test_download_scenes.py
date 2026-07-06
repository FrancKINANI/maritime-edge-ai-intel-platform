from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import download_scenes


def test_get_scene_base_id_normalizes_cog_and_standard_variants():
    standard_name = "S1A_IW_GRDH_1SDV_20240107T064657_20240107T064719_051997_06488E_B2F9"
    cog_name = "S1A_IW_GRDH_1SDV_20240107T064657_20240107T064719_051997_06488E_B2F9_COG"

    assert download_scenes.get_scene_base_id(standard_name) == "051997_06488E_B2F9"
    assert download_scenes.get_scene_base_id(cog_name) == "051997_06488E_B2F9"


def test_is_scene_downloaded_detects_existing_scene_by_base_id(tmp_path):
    existing_scene = tmp_path / "S1A_IW_GRDH_1SDV_20240107T064657_20240107T064719_051997_06488E_B2F9.SAFE"
    existing_scene.mkdir()

    assert download_scenes.is_scene_downloaded(
        tmp_path,
        "S1A_IW_GRDH_1SDV_20240107T064657_20240107T064719_051997_06488E_B2F9_COG",
        existing_scene_ids={"051997_06488E_B2F9"},
    )


def test_is_scene_downloaded_skips_duplicates_across_regions(tmp_path):
    existing_scene = tmp_path / "S1A_IW_GRDH_1SDV_20240107T064657_20240107T064719_051997_06488E_B2F9.SAFE"
    existing_scene.mkdir()

    assert download_scenes.is_scene_downloaded(
        tmp_path,
        "S1A_IW_GRDH_1SDV_20240107T064657_20240107T064719_051997_06488E_B2F9_COG",
        existing_scene_ids={"051997_06488E_B2F9"},
    )
    assert download_scenes.is_scene_downloaded(
        tmp_path,
        "S1A_IW_GRDH_1SDV_20240107T064657_20240107T064719_051997_06488E_B2F9",
        existing_scene_ids={"051997_06488E_B2F9"},
    )
