.PHONY: setup build up down logs phase0 test clean

setup:
	@echo "Copying environment template..."
	cp -n .env.example .env || true
	@echo "Creating local data and model directories..."
	mkdir -p phase0/data/scenes phase0/data/tiles phase0/data/annotations phase0/data/results shared/models

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

phase0:
	cd phase0 && python download_scenes.py

test-all:
	@# Single invocation with importlib mode avoids namespace collisions.
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
	uv run python -m pytest tests/ground_dashboard/ -v -q

test-coverage:
	@# Single invocation with importlib mode avoids namespace collisions.
	uv run python -m pytest services/aggregator/tests/ services/detector/tests/ \
		services/satellite-monitor/tests/ services/data-ingestor/tests/ \
		services/sentinel-preprocessor/tests/ phase0/tests/ shared/tests/ \
		tests/integration/ services/ground_dashboard/tests/ -q \
		--cov=. --cov-report=term --cov-report=html:coverage_html \
		--cov-fail-under=60

lint:
	ruff check services/ research/ shared/

sast:
	bandit -r services/ --quiet || true

clean:
	@echo "Cleaning up generated tiles, downloaded scenes, and results..."
	find phase0/data/scenes -type f ! -name '.gitkeep' -delete
	find phase0/data/tiles -type f ! -name '.gitkeep' -delete
	find phase0/data/results -type f ! -name '.gitkeep' -delete
	rm -rf coverage_html/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
