.PHONY: test lint format run-dashboard docker-up build-lambda help

help:
	@echo "Ai-Incident-SRE targets:"
	@echo "  test          - Run pytest"
	@echo "  build-lambda  - Package Lambda handler zip"
	@echo "  lint          - Run ruff check"
	@echo "  format        - Run ruff format"
	@echo "  run-dashboard - Start dashboard locally"
	@echo "  docker-up     - Start dashboard via Docker Compose"

test:
	pytest tests/ -v

lint:
	ruff check dashboard/ sre-brain/ chaos-scripts/ vm-image/

format:
	ruff format dashboard/ sre-brain/ chaos-scripts/ vm-image/

run-dashboard:
	cd dashboard && python app.py

docker-up:
	docker compose up --build -d

build-lambda:
	python scripts/build-lambda.py
