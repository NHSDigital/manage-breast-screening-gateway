include scripts/shared.mk
include scripts/terraform/terraform.mk

.DEFAULT_GOAL := help

.PHONY: clean config dependencies githooks-config githooks-run help test test-lint test-unit _install-uv
.SILENT: help

# ---------------------------------------------------------------------------
# Help & Meta
# ---------------------------------------------------------------------------
help: # Print help @Others
	printf "\nUsage: \033[3m\033[93m[arg1=val1] [arg2=val2] \033[0m\033[0m\033[32mmake\033[0m\033[34m <command>\033[0m\n\n"
	perl -e '$(HELP_SCRIPT)' $(MAKEFILE_LIST)

# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------
package: # Create release package @Operations
	./scripts/bash/package_release.sh

clean: # Clean-up project resources @Operations
	@echo "Cleaning up..."
	rm -rf .pytest_cache __pycache__ .coverage htmlcov/ .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

# ---------------------------------------------------------------------------
# Bootstrap & Environment
# ---------------------------------------------------------------------------
config: _install-tools _install-uv githooks-config dependencies # Configure development environment @Configuration

dependencies: # Install dependencies @Pipeline
	uv sync --all-extras

githooks-config: # Install pre-commit hooks @Configuration
	@if ! command -v pre-commit >/dev/null 2>&1; then \
		PC_VERSION=$$(awk '/^pre-commit / {print $$2}' .tool-versions); \
		echo "Installing pre-commit==$${PC_VERSION}..."; \
		pip install "pre-commit==$${PC_VERSION}"; \
	fi
	pre-commit install -c .pre-commit-config.yaml

githooks-run: # Run git hooks @Operations
	pre-commit run \
    --config .pre-commit-config.yaml \
		--all-files

_install-uv:
	@if ! uv --version >/dev/null 2>&1; then \
		UV_VERSION=$$(awk '/^uv / {print $$2}' .tool-versions); \
		echo "Installing uv==$${UV_VERSION}..."; \
		pip install "uv==$${UV_VERSION}"; \
	else \
		echo "uv already installed"; \
	fi

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------
test: test-unit test-integration test-lint # Run all tests @Testing

test-unit: # Run unit tests (use ARGS="<args>" for additional options) @Testing
	uv run pytest -m "not integration" $(ARGS)

test-integration:
	uv run pytest -m "integration" $(ARGS)

test-lint: # Lint files @Testing
	uv run ruff check .
	uv run ruff format --check .
	uv run pyright
