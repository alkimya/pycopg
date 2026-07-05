.PHONY: install test lint format build bench deadcode

install:
	uv sync --all-extras --dev

test:
	uv run pytest

lint:
	uv run ruff check pycopg tests

format:
	uv run black pycopg tests
	uv run ruff check --fix pycopg tests

build:
	uv build

deadcode:
	uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80

bench:
	python -m benchmarks
