# services/ground-dashboard/app.py
"""Ground Dashboard Streamlit Application.

Exposes a web UI containing three operational modes: Manual Image Upload,
Interactive Satellite Query, and Real-time Continuous Monitoring.
"""

import streamlit as st

st.set_page_config(
    page_title="Maritime Edge AI Intel Platform",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded",
)


def render_upload_mode() -> None:
    """Renders Mode 1: Manual Upload and Local Preprocessing/Detection."""
    st.header("Mode 1 — Upload Image")
    st.info("Mode 1 (Manual Image Upload) — Coming soon")


def render_query_mode() -> None:
    """Renders Mode 2: Custom Geographic/Constellation Query."""
    st.header("Mode 2 — Satellite Query")
    st.info("Mode 2 (Satellite Query) — Coming soon")


def render_monitoring_mode() -> None:
    """Renders Mode 3: Persistent Real-time Continuous Monitoring."""
    st.header("Mode 3 — Continuous Monitoring")
    st.info("Mode 3 (Continuous Monitoring) — Coming soon")


def main() -> None:
    """Coordinates dashboard page routing based on user sidebar selection."""
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
