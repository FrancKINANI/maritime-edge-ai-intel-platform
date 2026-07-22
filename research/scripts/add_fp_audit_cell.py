#!/usr/bin/env python3
"""Add Cell 13 — False Positive Visual Audit to the traceability notebook."""

import json
from pathlib import Path

NOTEBOOK_PATH = Path("research/notebooks/colab_traceability_check_v2.ipynb")

# Read the cell code from an external file to avoid escaping nightmares
CELL_CODE_PATH = Path("research/scripts/fp_audit_cell_code.py")

MD_CELL = {
    "cell_type": "markdown",
    "id": "fp_audit_intro",
    "metadata": {},
    "source": [
        "## Cell 13 — False Positive Visual Audit\n",
        "\n",
        "**Purpose:** Systematically inspect individual model predictions that were counted\n",
        "as **false positives** (no overlap with any AIS GT box) to determine whether they\n",
        "correspond to real, visually identifiable vessels (suggesting GT misalignment)\n",
        "or are genuine noise/artifacts.\n",
        "\n",
        "**Protocol:**\n",
        "1. Generate AIS annotations via GFW for the processed scene (YOLO labels)\n",
        "2. Load the Phase I ONNX model (`shared/models/yolov8n_mrssd_int8.onnx`)\n",
        "3. Run inference at very low confidence threshold (`conf=0.001`) to capture\n",
        "   any prediction — even those below the standard 0.25 threshold\n",
        "4. For each prediction with **no GT match** (IoU < 0.5), generate a visualization\n",
        "   with the GT box in **green** and the prediction box in **red**\n",
        "5. Open the generated HTML gallery and classify each FP as:\n",
        "   - **A** — Clearly a vessel (elongated, high contrast, looks like a ship)\n",
        "   - **B** — Not a vessel (noise, artifact, normal sea texture)\n",
        "   - **C** — Ambiguous / uncertain\n",
        "\n",
        "**Interpretation of results:**\n",
        "- If >20-30% of FPs are category **A**: the model may actually detect real\n",
        "  vessels, but GT AIS positions are misaligned (spatial/temporal offset).\n",
        "  The fix would be improving GT precision, not more fine-tuning.\n",
        "- If >90% are category **B**: the FPs are genuine noise, confirming the\n",
        "  model truly has zero detection capability on this domain.\n",
        "\n",
        "**Prerequisite:** Cells 1-12 must have completed successfully (scene downloaded,\n",
        "processed into tiles). Variables `scene_id`, `pipeline`, `TILES_DIR`, `GFW_API_TOKEN`\n",
        "must be in scope.\n",
    ],
}


def read_code_cell() -> dict:
    """Read the external code file and wrap it as a notebook code cell."""
    code = CELL_CODE_PATH.read_text()
    # Split into lines, add trailing newline to each (notebook format)
    source_lines = [line + "\n" for line in code.split("\n")]
    return {
        "cell_type": "code",
        "execution_count": None,
        "id": "fp_audit_code",
        "metadata": {},
        "outputs": [],
        "source": source_lines,
    }


def main():
    with open(NOTEBOOK_PATH) as f:
        nb = json.load(f)

    cells = nb["cells"]

    # Check if Cell 13 already exists
    for i, c in enumerate(cells):
        if c.get("id", "").startswith("fp_audit"):
            print(f"Cell 13 already exists at index {i}. Removing it first.")
            cells.pop(i)
            # Re-check after pop
            break

    # Append markdown cell
    md_cell_copy = dict(MD_CELL)
    md_cell_copy["id"] = f"fp_audit_intro_{len(cells)}"
    cells.append(md_cell_copy)

    # Append code cell from external file
    code_cell = read_code_cell()
    code_cell["id"] = f"fp_audit_code_{len(cells)}"
    cells.append(code_cell)

    with open(NOTEBOOK_PATH, "w") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)

    print(f"Added Cell 13 to {NOTEBOOK_PATH}")
    print(f"  Cell index: {len(cells)-2} (markdown)")
    print(f"  Cell index: {len(cells)-1} (code — from {CELL_CODE_PATH})")


if __name__ == "__main__":
    main()
