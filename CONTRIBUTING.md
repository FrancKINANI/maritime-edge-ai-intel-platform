# Contributing

Thank you for your interest in the Maritime Intelligence Platform!

## Development Setup

1. **Prerequisites**: Python 3.11+, Docker (optional, for microservices)

2. **Clone and install**:
   ```bash
   git clone https://github.com/ksf-space-foundation/maritime-intelligence-platform.git
   cd maritime-intelligence-platform
   cp .env.example .env  # Fill in your API keys
   pip install -r docker/base/requirements.txt
   ```

3. **Pre-commit hooks** (recommended):
   ```bash
   pip install pre-commit
   pre-commit install
   ```

## Code Quality

We use the following tools:

- **Ruff** for linting and formatting
- **Bandit** for SAST security scanning
- **Mypy** (optional) for type checking

Before submitting a PR, run:
```bash
ruff check .     # Lint
ruff format .    # Format
bandit -r services/  # Security scan
pytest            # Tests
```

## Project Structure

```
services/           # Microservices (FastAPI)
├── aggregator/
├── data-ingestor/
├── detector/
├── ground-dashboard/    # Streamlit UI
├── satellite-monitor/
└── sentinel-preprocessor/
shared/             # Shared schemas, config, utilities
phase0/             # Phase 0: benchmark, dataset construction, analysis
phase_post0/        # Fine-tuning pipeline, Colab notebooks
```

## Commit Guidelines

- Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`
- Keep commits atomic and focused
- Write descriptive commit messages
