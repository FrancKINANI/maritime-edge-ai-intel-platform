# services/ground-dashboard/app.py
"""Ground Dashboard Streamlit Application.

Exposes a web UI containing three operational modes: Manual Image Upload,
Interactive Satellite Query, and Real-time Continuous Monitoring.
"""

import streamlit as st
import os
import httpx
import base64
from pathlib import Path
from datetime import datetime

st.set_page_config(
    page_title="Maritime Edge AI Intel Platform",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Defaults match host ports published in docker-compose.yml:
#   preprocessor 8000, aggregator 8002, detector 8003, satellite-monitor 8004
DETECTOR_URL = os.getenv("DETECTOR_URL", "http://localhost:8003")
SATMON_URL = os.getenv("SATMON_URL", "http://localhost:8004")
AGGREGATOR_URL = os.getenv("AGGREGATOR_URL", "http://localhost:8002")
PREPROCESSOR_URL = os.getenv("PREPROCESSOR_URL", "http://localhost:8000")


def render_upload_mode() -> None:
    st.header("Mode 1 — Upload Image / SAR Product")
    st.write("Upload a file for vessel detection. Supports multiple formats:")
    st.markdown("""
    - **`.npy`** — Preprocessed 512×512 tile, sent directly to the Detector
    - **`.zip` / `.SAFE`** — Raw Sentinel-1 GRD archive, preprocessed then detected
    - **`.tiff` / `.tif`** — Individual GeoTIFF scene, preprocessed then detected
    """)
    uploaded = st.file_uploader(
        "Choose file",
        type=["npy", "zip", "tiff", "tif"],
        help="Preprocessed .npy tiles skip preprocessing. Raw .zip/.SAFE/.tiff products are preprocessed first."
    )
    scene_id = st.text_input("Scene ID (optional)")
    tile_id = st.text_input("Tile ID (optional)")

    # Pipeline selection with explanations
    st.markdown("**Preprocessing Pipeline Selection:**")
    pipeline_help = """
    - **A: Raw** — Bare normalized image, no calibration or filtering (baseline, no SAR processing)
    - **B: Sigma0** — Radiometric calibration applied (backscatter coefficient conversion), no noise reduction
    - **C: Sigma0 + Lee** — Calibration AND adaptive speckle filtering (multiplicative noise characteristic of radar)
    - **D: Sigma0 + Lee + Log dB** — Full chain with logarithmic compression, main candidate undergoing scientific validation (Phase 0 — result not yet definitive)
    """
    st.markdown(pipeline_help)
    pipeline = st.selectbox("Select pipeline", options=["A", "B", "C", "D"], index=3)

    if uploaded is not None:
        data = uploaded.read()
        file_ext = Path(uploaded.name).suffix.lower()

        if file_ext == ".npy":
            # ---- Direct detection path (preprocessed tile) ----
            b64 = base64.b64encode(data).decode("utf-8")
            if st.button("Send to Detector"):
                payload = {
                    "tile_b64": b64,
                    "scene_id": scene_id or "uploaded",
                    "tile_id": tile_id or uploaded.name,
                    "preprocessing_pipeline": pipeline,
                }
                try:
                    with httpx.Client() as client:
                        r = client.post(f"{DETECTOR_URL}/detect", json=payload, timeout=60.0)
                        r.raise_for_status()
                        ev = r.json()
                    st.success(f"Detection returned {ev.get('vessel_count')} vessels (priority {ev.get('priority_level')})")
                    st.json(ev)
                except Exception as e:
                    st.error(f"Detector request failed: {e}")

        else:
            # ---- Preprocessing + detection path (raw SAR product) ----
            st.info("Raw SAR product detected — preprocessing before detection.")
            if st.button("Upload, Preprocess & Detect"):
                # Save to shared Docker volume so the sentinel-preprocessor
                # container can access the file (both mount ./shared:/app/shared)
                upload_dir = Path("/app/shared/uploads")
                upload_dir.mkdir(parents=True, exist_ok=True)
                local_path = upload_dir / uploaded.name
                try:
                    local_path.write_bytes(data)
                    st.info(f"Saved to {local_path}")

                    # Call sentinel-preprocessor
                    safe_path_arg = str(local_path)
                    if file_ext == ".zip":
                        safe_path_arg = str(local_path)  # preprocessor handles .zip detection

                    with httpx.Client() as client:
                        prep_resp = client.post(
                            f"{PREPROCESSOR_URL}/preprocess",
                            params={
                                "safe_path": safe_path_arg,
                                "pipeline": pipeline,
                            },
                            timeout=300.0,
                        )
                        prep_resp.raise_for_status()
                        prep_result = prep_resp.json()

                    st.success("Preprocessing complete")
                    st.json(prep_result)

                    # Detect on each generated tile
                    tiles = prep_result.get("tiles", [])
                    if tiles:
                        st.info(f"Running detection on {len(tiles)} tiles...")
                        all_detections = []
                        for tile_info in tiles:
                            tile_path = tile_info.get("npy_path")
                            if not tile_path:
                                continue
                            tile_id_val = tile_info.get("tile_id", Path(tile_path).stem)
                            try:
                                with open(tile_path, "rb") as fh:
                                    tile_data = fh.read()
                                tile_b64 = base64.b64encode(tile_data).decode("utf-8")
                                det_payload = {
                                    "tile_b64": tile_b64,
                                    "scene_id": scene_id or uploaded.name,
                                    "tile_id": tile_id_val,
                                    "preprocessing_pipeline": pipeline,
                                }
                                det_resp = client.post(
                                    f"{DETECTOR_URL}/detect",
                                    json=det_payload,
                                    timeout=60.0,
                                )
                                det_resp.raise_for_status()
                                all_detections.append(det_resp.json())
                            except Exception as tile_err:
                                st.warning(f"Detection failed for tile {tile_id_val}: {tile_err}")

                        st.success(f"Detection complete — {len(all_detections)} tiles processed")
                        st.json(all_detections[:5])  # Show first 5 results
                    else:
                        st.warning("No tiles were generated by the preprocessor.")

                except Exception as e:
                    st.error(f"Processing failed: {e}")


def render_query_mode() -> None:
    st.header("Mode 2 — Satellite Query")
    st.write("Query satellite position from Satellite Monitor service.")
    st.info("💡 **Tip**: Sentinel-1A NORAD ID is 39634. ISS (default) is 25544.")
    sat_id = st.text_input("Satellite NORAD ID or name", value="39634")
    ts = st.text_input("Timestamp (UTC, ISO)", value=datetime.utcnow().isoformat())
    if st.button("Get Position"):
        try:
            with httpx.Client() as client:
                r = client.get(f"{SATMON_URL}/position", params={"satellite_id": sat_id, "timestamp": ts}, timeout=20.0)
                r.raise_for_status()
                pos = r.json()
            st.success("Position retrieved")
            st.json(pos)
        except Exception as e:
            st.error(f"Satellite query failed: {e}")


def render_monitoring_mode() -> None:
    st.header("Mode 3 — Continuous Monitoring")
    st.write("Fetch aggregator statistics and recent events filtered by zone, priority, and time range.")

    # Geographic zone definition
    st.subheader("Geographic Zone Definition")
    col1, col2 = st.columns(2)
    with col1:
        lat_min = st.number_input("Latitude Min", value=27.0, min_value=-90.0, max_value=90.0)
        lon_min = st.number_input("Longitude Min", value=-17.0, min_value=-180.0, max_value=180.0)
    with col2:
        lat_max = st.number_input("Latitude Max", value=36.0, min_value=-90.0, max_value=90.0)
        lon_max = st.number_input("Longitude Max", value=-1.0, min_value=-180.0, max_value=180.0)

    zone_bbox = [lat_min, lon_min, lat_max, lon_max]
    st.info(f"Monitoring zone bbox: {zone_bbox}")

    # Zone and priority filters
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        zone_filter = st.selectbox(
            "Maritime Zone Filter",
            options=["all", "Z1 (Territorial Waters 12NM)", "Z2 (EEZ 200NM)", "Z3 (High Seas)"],
            index=0,
        )
    with col_f2:
        priority_filter = st.selectbox(
            "Priority Level Filter",
            options=["all", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
            index=0,
        )

    since_filter = st.text_input(
        "Since (ISO timestamp, optional)",
        value="",
        help="e.g. 2026-06-01T00:00:00 to filter events after this time",
    )

    if st.button("Refresh Stats"):
        try:
            with httpx.Client() as client:
                r = client.get(f"{AGGREGATOR_URL}/stats", timeout=10.0)
                r.raise_for_status()
                stats = r.json()

                # Build query params for /events
                events_params = {}
                if zone_filter != "all":
                    events_params["zone"] = zone_filter.split(" ")[0]  # Extract Z1/Z2/Z3
                if priority_filter != "all":
                    events_params["priority"] = priority_filter
                if since_filter:
                    events_params["since"] = since_filter

                r2 = client.get(
                    f"{AGGREGATOR_URL}/events",
                    params=events_params,
                    timeout=10.0,
                )
                r2.raise_for_status()
                events = r2.json()

            st.subheader("Stats by Zone & Priority")
            st.json(stats)

            st.subheader(f"Filtered Events ({len(events)} total)")
            if events:
                st.dataframe(
                    [
                        {
                            "event_id": e["event_id"][:8] + "...",
                            "zone": e.get("zone", "?"),
                            "priority": e.get("priority_level", "?"),
                            "vessels": e.get("vessel_count", 0),
                            "dark": e.get("dark_vessel_count", 0),
                            "time": e.get("timestamp", "")[:19],
                        }
                        for e in events[:100]
                    ]
                )
            else:
                st.info("No events match the current filter criteria.")

        except Exception as e:
            st.error(f"Aggregator request failed: {e}")


def main() -> None:
    st.sidebar.title("Operational Control")
    st.sidebar.markdown("---")

    mode = st.sidebar.radio(
        "Select Mode",
        options=[
            "1. Upload Image (Ad-hoc)",
            "2. Satellite Query (Historical/Targeted)",
            "3. Continuous Monitoring (Real-time)",
        ],
    )

    st.sidebar.markdown("---")
    st.sidebar.caption("Maritime Edge AI Intel Platform • Phase II")

    if "1." in mode:
        render_upload_mode()
    elif "2." in mode:
        render_query_mode()
    elif "3." in mode:
        render_monitoring_mode()


if __name__ == "__main__":
    main()
