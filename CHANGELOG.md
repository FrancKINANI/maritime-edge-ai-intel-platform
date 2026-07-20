# Changelog

All notable changes to the Maritime Intelligence Platform will be documented in this file.

## [0.2.0] — 2026-07-21

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

### Fixed
- 36 ruff linting errors (unused imports, variables, f-strings)
- Broken symlinks in phase_post0 directory
- Ground-dashboard test file location

## [0.1.0] — 2026-07-19

### Added
- Phase 0 closure document with 8-hypothesis analysis
- Zero-shot domain transfer evaluation (all 4 pipelines + FP32)
- Fine-tuning dataset builder for Sentinel-1 real data
- CVAT fallback annotation validator (HTML-based)
- Colab notebooks for fine-tuning YOLOv8n detector
- Platform-stratified dataset split (S1C vs S1D balanced)
