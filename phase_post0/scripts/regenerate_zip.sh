#!/usr/bin/env bash
# Regenerate the Colab dataset ZIP
# Run from the project root:  bash phase_post0/regenerate_zip.sh

set -e
cd "$(dirname "$0")/.."
echo "Regenerating maritime_dataset.zip..."
uv run python phase0/scripts/export_colab_dataset.py
echo "Done. ZIP ready at phase0/data/colab_export/maritime_dataset.zip"
