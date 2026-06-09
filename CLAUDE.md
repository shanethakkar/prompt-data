# Verity — Trust-Layer Analytics Copilot

Natural-language-to-SQL over the Olist e-commerce DB. The product is TRUST, not
query generation: ambiguity detection, surfaced assumptions, calibrated
confidence, and a measured semantic-error rate. Full spec: docs/SPEC.md.

## Non-negotiables
- Running server stays under 4 GB RAM. LLM via Anthropic API, embeddings via
  fastembed ONNX, SQLite demo DB, row-capped results, eval runs as a SEPARATE
  offline batch. Verify and record server peak RSS.
- Execution is read-only and SELECT-only. Validate and reject any non-SELECT
  before it reaches the DB. This is the prompt-injection backstop.
- No metric is shown unless the eval harness measured it. Never fabricate numbers.
- No em dashes in user-facing copy.

## Stack
Frontend: Next.js 16 App Router, React 19, TS strict, Tailwind v4, hand-built SVG charts.
Backend: Python 3.12, FastAPI, single uvicorn worker.
LLM: Anthropic API, tiered routing (Haiku/Sonnet/Opus). Confirm model strings at docs.claude.com.
Embeddings: fastembed bge-small (ONNX). Storage: sqlite-vec or in-memory.
Eval: BIRD dev (SQLite). Not Spider 2.0 full.

## Commands
- Load demo DB:  uv run python data/load_olist.py  (or: make load-db)
- Run backend:   uv run uvicorn backend.app.main:app --workers 1
- Run frontend:  cd frontend && npm run dev
- Run eval:      uv run python eval/run_bird.py
- All gates:     make check  (lint + typecheck + test)
- Lint only:     make lint
- Types only:    make typecheck
- Tests only:    make test

## Conventions
- Python-first. Pure functions for pipeline math; DB I/O isolated for testability.
- Match the existing portfolio design: dark theme, cyan accent, Geist fonts, SVG charts.
- Commit per phase. Run make check before every commit. Pre-commit hooks run ruff
  automatically on git commit.
- When you discover something non-obvious (API quirk, surprising behavior, a choice
  between real alternatives), add an entry to docs/DECISIONS.md before moving on.

## Workflow
- Read docs/PLAN.md before starting any work. It is the authoritative record of what
  has been built, what phase is active, and what comes next.
- Read docs/DECISIONS.md to pick up discoveries from prior phases before touching
  any code they affect.
- Start each phase in plan mode. Read docs/SPEC.md and the target phase section in
  docs/PLAN.md, produce a plan, wait for approval, then implement.
- Update docs/PLAN.md at the start and end of every phase: mark gates complete,
  record RSS and other measured values, expand the next phase section.
- Keep this file small; link to docs/ for detail.

## Docs
- Active plan:    docs/PLAN.md      (phase status, gate results, current phase detail)
- Findings log:   docs/DECISIONS.md (non-obvious discoveries and architectural choices)
- Full spec:      docs/SPEC.md
- Claude Code:    https://docs.claude.com/en/docs/claude-code/overview
- Models:         https://docs.claude.com/en/docs/about-claude/models