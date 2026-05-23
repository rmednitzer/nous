.PHONY: help install lint format typecheck test check policy schema docs-build docs-serve serve clean

help:
	@echo "Targets:"
	@echo "  install     uv sync --all-extras"
	@echo "  lint        ruff check"
	@echo "  format      ruff format"
	@echo "  typecheck   mypy --strict"
	@echo "  test        pytest"
	@echo "  check       lint + typecheck + test"
	@echo "  policy      em-dash and private-repo greps (CI parity)"
	@echo "  schema      regenerate generated docs (tool reference, ADR index, backlog summary, JSON Schemas)"
	@echo "  docs-build  mkdocs build --strict"
	@echo "  docs-serve  mkdocs serve"
	@echo "  serve       run the MCP server on stdio"
	@echo "  clean       remove caches and build artefacts"

install:
	uv sync --all-extras

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy

test:
	uv run pytest

check: lint typecheck test

policy:
	bash scripts/policy_checks.sh

schema:
	uv run python scripts/gen_schemas.py
	uv run python scripts/gen_tool_reference.py
	uv run python scripts/gen_adr_index.py
	uv run python scripts/gen_backlog_summary.py

docs-build:
	uv run mkdocs build --strict

docs-serve:
	uv run mkdocs serve

serve:
	uv run python -m nous serve

clean:
	rm -rf .ruff_cache .mypy_cache .pytest_cache build dist site *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
