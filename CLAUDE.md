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
- Update docs/DECISIONS.md the moment a non-obvious finding lands (API quirk, surprising
  behavior, a data gotcha, a choice between real alternatives). Do it as it comes in, not
  in a batch at the end; a finding you defer is a finding you lose.

## Workflow
Per-phase order. Do NOT skip step 2: the repo's plan, not your memory, is the source of truth.
1. Read docs/PLAN.md (authoritative state) and docs/DECISIONS.md (prior findings) before
   touching anything. Re-read the target phase section of docs/SPEC.md.
2. BEFORE writing any code, commit the phase plan into docs/PLAN.md: flip the phase to
   In progress in the status table and expand that phase's section (decisions, files,
   key designs, gate checklist). The plan must live in the repo, not only in chat or the
   plan-mode scratch file.
3. Start in plan mode: produce/confirm the approach, wait for approval, then implement.
4. As findings arise mid-phase, append to docs/DECISIONS.md immediately (see Conventions).
5. At end of phase: fill in the gate results in docs/PLAN.md (mark gates, record measured
   values like RSS), flip status to Complete, then run make check and commit.
- Keep this file small; link to docs/ for detail.

## Docs
- Active plan:    docs/PLAN.md      (phase status, gate results, current phase detail)
- Findings log:   docs/DECISIONS.md (non-obvious discoveries and architectural choices)
- Full spec:      docs/SPEC.md
- Claude Code:    https://docs.claude.com/en/docs/claude-code/overview
- Models:         https://docs.claude.com/en/docs/about-claude/models