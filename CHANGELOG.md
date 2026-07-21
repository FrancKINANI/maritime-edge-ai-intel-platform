# Changelog

All notable changes to the Maritime Intelligence Platform will be documented in this file.

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
