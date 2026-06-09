.PHONY: check lint typecheck test load-db help

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

check: lint typecheck test  ## Run all verification gates (lint + typecheck + test)

load-db:  ## Build data/demo.db from raw CSVs (run once before tests)
	uv run python data/load_olist.py

test:  ## Run pytest suite
	uv run pytest backend/tests/ -v -s

lint:  ## Run ruff linter and auto-fix
	uv run ruff check backend/ data/ --fix

typecheck:  ## Run mypy strict
	uv run mypy backend/
