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

test:
	@echo "Pytest not yet configured. Skeletons only."

clean:
	@echo "Cleaning up generated tiles, downloaded scenes, and results..."
	find phase0/data/scenes -type f ! -name '.gitkeep' -delete
	find phase0/data/tiles -type f ! -name '.gitkeep' -delete
	find phase0/data/results -type f ! -name '.gitkeep' -delete
