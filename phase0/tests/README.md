# Phase 0 Tests

Unit tests for the Phase 0 scientific validation scripts.

## Test Files

| File | Tests | Description |
|------|-------|-------------|
| `test_gfw_annotations.py` | 9 | GFW API client, AIS presence, dark vessels, normalized entries, retry logic |
| `test_download_scenes.py` | 3 | Scene ID normalization, duplicate detection |
| `test_gcp_interpolation.py` | 2 | GCP zero-error property, boundary behavior |
| `test_gcp_cross_implementation.py` | — | Cross-validation between local and Colab GCP implementations |

## Run

```bash
uv run python -m pytest phase0/tests/ -v
```
