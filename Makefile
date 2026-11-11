.PHONY: setup dev test lint format build

setup:
	./scripts/bootstrap.sh

dev:
	docker compose up

test:
	pytest backend/tests agents/tests

lint:
	black --check backend agents shared
	isort --check-only backend agents shared
	flake8 backend agents shared

format:
	black backend agents shared
	isort backend agents shared
