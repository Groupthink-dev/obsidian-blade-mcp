.PHONY: smoke help install install-dev sync test test-unit test-e2e test-cov lint format format-check type-check check check-linux build publish clean run server pre-commit-install pre-commit-run

help:
	@echo "Available targets:"
	@echo "  make install          - Install project dependencies"
	@echo "  make install-dev      - Install project with dev dependencies"
	@echo "  make sync             - Sync dependencies (uv sync --group dev)"
	@echo "  make test             - Run all unit tests (excluding e2e)"
	@echo "  make test-unit        - Run unit tests only"
	@echo "  make test-e2e         - Run e2e tests (requires running Obsidian)"
	@echo "  make test-cov         - Run tests with coverage report"
	@echo "  make lint             - Run ruff linter"
	@echo "  make format           - Format code with ruff"
	@echo "  make format-check     - Check formatting without fixing"
	@echo "  make type-check       - Run mypy type checker"
	@echo "  make check            - Run all quality checks (lint + format + type-check)"
	@echo "  make check-linux      - Run the Woodpecker lane in podman (Linux, no Obsidian)"
	@echo "  make build            - Build sdist and wheel into dist/"
	@echo "  make publish          - Upload dist/ to PyPI (needs UV_PUBLISH_TOKEN)"
	@echo "  make clean            - Clean build artifacts and cache"
	@echo "  make run              - Run the MCP server"
	@echo "  make server           - Alias for 'run'"
	@echo "  make pre-commit-install - Install pre-commit hooks"
	@echo "  make pre-commit-run   - Run pre-commit on all files"

# Installation
install:
	uv sync

install-dev:
	uv sync --group dev --group test

sync:
	uv sync --group dev --group test

# Testing
test:
	uv run pytest tests/ -m "not e2e" -v

test-unit:
	uv run pytest tests/ -m "not e2e" -v

test-e2e:
	OBSIDIAN_E2E=1 uv run pytest tests/e2e/ -v -m e2e

test-cov:
	uv run pytest tests/ -m "not e2e" --cov=src/obsidian_blade_mcp --cov-report=term-missing -v

# Code quality
lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

format-check:
	uv run ruff format --check src/ tests/

type-check:
	uv run mypy src/obsidian_blade_mcp

check: lint format-check type-check
	@echo "All quality checks passed!"

# The same commands as .woodpecker/validation.yaml, on the same image tag, with no
# obsidian binary on PATH. Native arch; the lane itself runs linux/amd64.
CONTAINER ?= podman
check-linux:
	$(CONTAINER) run --rm -v "$(CURDIR)":/w:ro -w /tmp docker.io/library/python:3.13-bookworm bash -ec '\
	  cp -r /w /src && cd /src && rm -rf .venv; \
	  export UV_PYTHON_DOWNLOADS=never UV_PYTHON=3.13 UV_CACHE_DIR=/tmp/uv; \
	  pip install --quiet --disable-pip-version-check --root-user-action=ignore uv; \
	  uv sync --group dev --group test --frozen; \
	  uv run ruff check src/ tests/; \
	  uv run ruff format --check src/ tests/; \
	  uv run mypy src/obsidian_blade_mcp; \
	  uv run pytest tests/ -m "not e2e" -q'

# Release. The canonical remote is Forgejo, which PyPI trusted publishing does not
# support, so 1.0.0 is published from a workstation with a project-scoped token.
# .github/workflows/publish.yml takes over once the GitHub mirror exists (v1.1.0).
build:
	rm -rf dist
	uv build
	uv run --with twine twine check dist/*

publish: build
	@test -n "$$UV_PUBLISH_TOKEN" || (echo "UV_PUBLISH_TOKEN is unset" && exit 1)
	@grep -q "^version = \"$$(git describe --tags --exact-match 2>/dev/null | sed 's/^v//')\"" pyproject.toml || \
	  (echo "HEAD is not at a tag matching pyproject.toml version" && exit 1)
	uv publish

# Pre-commit
pre-commit-install:
	uv run pre-commit install

pre-commit-run:
	uv run pre-commit run --all-files

# Running
run:
	uv run obsidian-blade-mcp

server: run

# Cleanup
clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Cleanup complete!"

# Drive the server as an MCP client would: handshake, tool count, vault_info.
# Defaults to the published package via uvx; SMOKE_CMD overrides the command.
SMOKE_CMD ?= uvx obsidian-blade-mcp
smoke:
	uv run python scripts/smoke.py $(SMOKE_CMD)
