# Changelog

All notable changes to the Maritime Intelligence Platform will be documented in this file.

## [2.1.0] — 2026-08-02

### Added
- **Pipeline E (MVSSD-enhanced)** in `sentinel-preprocessor`: CLAHE + Gaussian Blur +
  Median Blur applied on top of pipeline D — selectable from the dashboard (`A/B/C/D/E`)
- **`GET /products`** in `data-ingestor`: real CDSE catalogue search (bbox + date range),
  no download — resolves the previous 501 Not Implemented
- `LICENSE` (MIT), `SECURITY.md`, `DEPLOYMENT.md` at project root
- `docs/TESTING_MODES.md`: validation report of the 3 operational modes (kept local)

### Changed
- **Project restructuring:** research scripts moved into the services they serve —
  `download_scenes.py`/`gfw_annotations.py` → `services/data_ingestor/tools/`;
  `sar_preprocessing.py`/`process_all_scenes.py`/`apply_mvssd_ops.py` →
  `services/sentinel_preprocessor/tools/`; `fix_bbox_sizes.py` → `tools/maintenance/`
- Imports re-wired from the removed `research.scripts.*` module paths to the new
  `services.*.tools.*` paths (sentinel_fetcher, sar_preprocessing_module, tests,
  diagnostics, traceability notebook) — fixes 501s in containers
- Detector fixes: NCHW tensor layout for non-640 tiles, output parsing for the
  single-class MRSSD format `(1, 5, 8400)`, correct pixel rescaling (w/MODEL_INPUT_SIZE),
  nearest-neighbor resize replacing `np.resize` mosaicing
- `docs/` is now local-only (removed from git tracking, kept on disk)
- One-off research scripts pruned (FP audit, CVAT annotation, domain analysis);
  reproduction pipeline kept (dataset builder, traceability, Colab export, benchmark)

### Fixed
- Broken imports after the research → services reorg (production 501s)
- Detector crash on 512×640 tiles (`INVALID_ARGUMENT` from ONNX)
- Aberrant detection confidence (output format mismatch)
- Missing `tqdm`/`psutil` dependencies in service requirements
- Invalid Python syntax residue in `download_scenes.py` (notebook leftover)

## [2.0.1] — 2026-07-21

### Fixed
- 24 ruff CI errors across 10+ files (S112, E501, S314, S105, S106, S108, S608)
- High-severity CVE: pillow bumped 12.2.0 → 12.3.0
- Dependabot alerts: regen all requirements.txt via `uv pip compile --upgrade`
- CI action versions fixed (checkout@v7→v4, setup-python@v7→v5)
- Trivy scanner `skip-dirs` added for large data directories
- `docker/base/requirements.in` restored with open-ended version ranges
- `uv.lock` regenerated to match updated dependencies

## [2.0.0] — 2026-07-21

### Added
- `pyproject.toml` with project metadata and Python 3.11+ target
- `.pre-commit-config.yaml` for automated linting/formatting
- `.dockerignore` for optimized Docker builds
- `.github/dependabot.yml` for automatic dependency updates
- `CONTRIBUTING.md` and `CHANGELOG.md`
- S1C vs S1D platform comparison script and analysis
- Dataset traceability script for fine-tuning splits
- Trivy security scanning in CI workflow
- Non-privileged `appuser` in all Dockerfiles
- HEALTHCHECK instructions in all Dockerfiles

### Changed
- Upgraded Ruff configuration with comprehensive rule set
- Replaced all `datetime.utcnow()` with `datetime.now(timezone.utc)`
- Renamed `sar_preprocessing.py` to `sar_preprocessing_module.py`
- Added secret validation at startup for all microservices
- Improved dataset builder with `--stratify` and `--satellites` flags
- Fixed dry-run estimation for stratified splits
- Ground-dashboard env var defaults point to Docker service names
- **Project restructuring:** Fixed all Dockerfile paths (hyphens → underscores),
  unified Ruff configuration in pyproject.toml, removed stale .ruff.toml,
  cleaned project root (removed egg-info, moved data/ → docs/),
  updated .pre-commit versions, fixed broken Makefile paths,
  fixed pytest collection crash on missing secrets
- 223 Ruff lint errors fixed across codebase

### Fixed
- 36 ruff linting errors (unused imports, variables, f-strings)
- Broken symlinks in phase_post0 directory
- Ground-dashboard test file location
- Dockerfile COPY paths using hyphens instead of underscores
- Makefile test targets referencing non-existent paths
- Pytest SystemExit crash due to module-level secrets validation
- Obsolete gitignore entries referencing deleted directories
- .env.example extraneous [TEMPLATE] markers
- CI workflow test matrix invalid path

## [0.1.0] — 2026-07-19

### Added
- Phase 0 closure document with 8-hypothesis analysis
- Zero-shot domain transfer evaluation (all 4 pipelines + FP32)
- Fine-tuning dataset builder for Sentinel-1 real data
- CVAT fallback annotation validator (HTML-based)
- Colab notebooks for fine-tuning YOLOv8n detector
- Platform-stratified dataset split (S1C vs S1D balanced)
