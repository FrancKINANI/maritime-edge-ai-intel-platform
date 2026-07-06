# services/ground-dashboard/app.py
"""Ground Dashboard Streamlit Application.

Exposes a web UI containing three operational modes: Manual Image Upload,
Interactive Satellite Query, and Real-time Continuous Monitoring.
"""

import streamlit as st
import os
import httpx
import base64
from datetime import datetime

st.set_page_config(
    page_title="Maritime Edge AI Intel Platform",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded",
)

DETECTOR_URL = os.getenv("DETECTOR_URL", "http://localhost:8001")
SATMON_URL = os.getenv("SATMON_URL", "http://localhost:8010")
AGGREGATOR_URL = os.getenv("AGGREGATOR_URL", "http://localhost:8020")


def render_upload_mode() -> None:
    st.header("Mode 1 — Upload Image")
    st.write("Upload a preprocessed .npy tile (512x512) to run detection via the Detector service.")
    uploaded = st.file_uploader("Choose .npy tile file", type=["npy"])
    scene_id = st.text_input("Scene ID (optional)")
    tile_id = st.text_input("Tile ID (optional)")
    pipeline = st.selectbox("Preprocessing pipeline", options=["A", "B", "C", "D"], index=3)
    if uploaded is not None:
        data = uploaded.read()
        b64 = base64.b64encode(data).decode("utf-8")
        if st.button("Send to Detector"):
            payload = {"tile_b64": b64, "scene_id": scene_id or "uploaded", "tile_id": tile_id or uploaded.name, "preprocessing_pipeline": pipeline}
            try:
                with httpx.Client() as client:
                    r = client.post(f"{DETECTOR_URL}/detect", json=payload, timeout=60.0)
                    r.raise_for_status()
                    ev = r.json()
                st.success(f"Detection returned {ev.get('vessel_count')} vessels (priority {ev.get('priority_level')})")
                st.json(ev)
            except Exception as e:
                st.error(f"Detector request failed: {e}")


def render_query_mode() -> None:
    st.header("Mode 2 — Satellite Query")
    st.write("Query satellite position from Satellite Monitor service.")
    sat_id = st.text_input("Satellite NORAD ID or name", value="25544")
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
    st.write("Fetch aggregator statistics and recent events.")
    if st.button("Refresh Stats"):
        try:
            with httpx.Client() as client:
                r = client.get(f"{AGGREGATOR_URL}/stats", timeout=10.0)
                r.raise_for_status()
                stats = r.json()
                r2 = client.get(f"{AGGREGATOR_URL}/events", timeout=10.0)
                r2.raise_for_status()
                events = r2.json()
            st.subheader("Stats")
            st.json(stats)
            st.subheader("Recent events (up to 1000)")
            st.write(f"Showing {len(events)} events")
            st.json(events[:20])
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
