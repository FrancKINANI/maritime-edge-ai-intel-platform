.PHONY: setup build up down logs test-all test-services test-integration test-dashboard test-coverage lint sast clean

setup:
	@echo "Copying environment template..."
	cp -n .env.example .env || true
	@echo "Creating local data and model directories..."
	mkdir -p shared/models

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

test-all:
	@echo "=== Running all tests ==="
	uv run python -m pytest services/aggregator/tests/ services/detector/tests/ \
		services/satellite_monitor/tests/ services/data_ingestor/tests/ \
		services/sentinel_preprocessor/tests/ research/tests/ shared/tests/ \
		tests/integration/ services/ground_dashboard/tests/ -v -q

test-services:
	@echo "=== Service tests ==="
	uv run python -m pytest research/tests/ -q
	uv run python -m pytest services/sentinel_preprocessor/tests/ -q
	uv run python -m pytest services/aggregator/tests/ -q
	uv run python -m pytest services/detector/tests/ -q
	uv run python -m pytest services/satellite_monitor/tests/ -q
	uv run python -m pytest services/data_ingestor/tests/ -q
	uv run python -m pytest shared/tests/ -q

test-integration:
	uv run python -m pytest tests/integration/ -v -q

test-dashboard:
	uv run python -m pytest services/ground_dashboard/tests/ -v -q

test-coverage:
	@# Single invocation with importlib mode avoids namespace collisions.
	uv run python -m pytest services/aggregator/tests/ services/detector/tests/ \
		services/satellite_monitor/tests/ services/data_ingestor/tests/ \
		services/sentinel_preprocessor/tests/ shared/tests/ \
		tests/integration/ services/ground_dashboard/tests/ -q \
		--cov=. --cov-report=term --cov-report=html:coverage_html \
		--cov-fail-under=60

lint:
	ruff check services/ research/ shared/

sast:
	bandit -r services/ --quiet || true

clean:
	@echo "Cleaning up build artifacts..."
	rm -rf coverage_html/ .coverage
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .ruff_cache
