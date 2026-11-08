.PHONY: setup dev test lint format build

setup:
	./scripts/bootstrap.sh

dev:
	docker compose up

test:
	pytest agents/tests

lint:
	black --check backend agents shared data_scripts
	isort --check-only backend agents shared data_scripts
	flake8 backend agents shared data_scripts

format:
	black backend agents shared data_scripts
	isort backend agents shared data_scripts

