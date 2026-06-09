.PHONY: check lint typecheck test load-db load-db-full pack-db unpack-db help

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

check: lint typecheck test  ## Run all verification gates (lint + typecheck + test)

load-db:  ## Build the slim data/demo.db from raw CSVs (the shipped, deploy-sized DB)
	uv run python data/load_olist.py --slim

load-db-full:  ## Build the full-fidelity data/demo.full.db locally (all tables/columns)
	uv run python data/load_olist.py --db data/demo.full.db

pack-db:  ## Recreate the committed data/demo.db.gz from a freshly built slim data/demo.db
	gzip -9 -kf data/demo.db

unpack-db:  ## Decompress the committed data/demo.db.gz to data/demo.db (no raw CSVs needed)
	gzip -dkf data/demo.db.gz

test:  ## Run pytest suite
	uv run pytest backend/tests/ -v -s

lint:  ## Run ruff linter and auto-fix
	uv run ruff check backend/ data/ --fix

typecheck:  ## Run mypy strict
	uv run mypy backend/
