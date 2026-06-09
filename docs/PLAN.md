# Prompt Data — Active Build Plan

This file is the living build plan. Update it at the start and end of every phase:
mark the phase complete, record the verified gate results, and expand the next
phase plan before starting it. Any agent reading this file should treat it as
the authoritative source of what has been built, what is in progress, and what
comes next. Full spec: docs/SPEC.md.

---

## Phase status

| Phase | Name | Status |
|---|---|---|
| 0 | Scaffold and safety floor | **Complete** (gates green, idle RSS 5.6 MB) |
| 1 | Core text-to-SQL | **Complete** (offline gates green; live smoke passed 5/5) |
| 2 | Trust layer | **Complete** (offline gates green; live smoke clear/ambiguous/clarify all pass) |
| 3 | Eval harness | **Complete** (Sonnet/240 + calibration + trap eval: 59pp confidently-wrong reduction, 0 over-decline) |
| 4 | Frontend core | **Complete** (/ask streams the trust pipeline; verified live + screenshots) |
| 5 | Showcase pages | **Complete** (4 static pages from committed JSON; Vercel-ready; screenshots reviewed) |
| 6 | Deploy (Vercel + Render) | **Complete** (repo deploy-ready + pushed; go-live via docs/DEPLOY.md) |
| 7 | Usability + bring-your-own-data | **In progress** (A chart axes + B schema explorer first) |

---

## Phase 0 — Scaffold and safety floor

**Done when:** `python data/load_olist.py` produces `data/demo.db`, `pytest backend/tests/ -v -s` passes
(including RSS assertion with value printed), `ruff check backend/ data/` is clean,
`mypy backend/` is clean under strict mode.

**Verified gate results:** (2026-06-09, sqlglot 25.34.1, Python 3.12.13)
- [x] `uv run python data/load_olist.py` — OK, FK check clean, all tables non-empty
- [x] `uv run pytest backend/tests/ -v -s` — 31 passed, idle RSS: **5.6 MB**
- [x] `uv run ruff check backend/ data/ eval/` — clean
- [x] `uv run mypy backend/` — clean (strict, 8 files)

**Deltas from plan (data-quality findings, see docs/DECISIONS.md):**
- `order_reviews` is a rowid table (review_id not unique: 814 dups), indexed on review_id + order_id
- 2 product categories seeded into the translation table so the products FK holds
- Limit clamp reads the `expression` arg (not `this`); fails safe on non-numeric limits
- Timeout test avoids named-column CTE aliases (sqlglot drops them on round-trip)
- `types-psutil` added to dev deps for mypy strict

### Files to create

```
pyproject.toml
.python-version           (3.12)
.gitignore
.env.example
backend/__init__.py
backend/app/__init__.py
backend/app/main.py
backend/app/pipeline/__init__.py
backend/app/pipeline/execute.py     <- core deliverable: validator + sandbox
backend/tests/__init__.py
backend/tests/test_execute.py
backend/tests/test_server_rss.py
data/load_olist.py                  <- core deliverable: CSVs -> demo.db
eval/__init__.py
eval/run_bird.py                    (stub)
eval/metrics.py                     (stub)
eval/ablation.py                    (stub)
eval/calibrate.py                   (stub)
eval/out/.gitkeep
frontend/.gitkeep                   (Next.js scaffold deferred to Phase 4)
docs/methodology.md                 (stub)
docs/limitations.md                 (stub)
```

### Key decisions

- Python packaging: **uv** with `pyproject.toml`
- Default query LIMIT: **500 rows**
- RSS measurement: **pytest fixture + psutil** (subprocess, not in-process)
- Frontend scaffold: **deferred to Phase 4**

### pyproject.toml structure

```toml
[project]
name = "verity"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlglot>=25.0,<26",
    "psutil>=6.0",
    "httpx>=0.27",
    "python-dotenv>=1.0",
]

[dependency-groups]
dev = ["pytest>=8.0", "ruff>=0.6", "mypy>=1.11"]
data = ["pandas>=2.2"]   # offline scripts only — never import in server

[tool.mypy]
python_version = "3.12"
strict = true
exclude = ["data/", "eval/", "frontend/"]

[tool.pytest.ini_options]
testpaths = ["backend/tests"]
```

Pin sqlglot `<26`. The `data` group makes the pandas/server boundary explicit.

### data/load_olist.py

Reads 9 Olist CSVs, writes `data/demo.db`. Idempotent: drop-in-reverse-FK-order, create, load.

**Load order (parents before children):**
1. `product_category_name_translation`
2. `customers`
3. `sellers`
4. `products` (FK -> product_category_name_translation)
5. `orders` (FK -> customers)
6. `order_items` (FKs -> orders, products, sellers; composite PK)
7. `order_payments` (FK -> orders; composite PK)
8. `order_reviews` (FK -> orders)
9. `geolocation` (rowid table, no single-column PK)

**Column name note:** raw CSVs have `product_name_lenght` and `product_description_lenght`
(original dataset typos). Preserve exactly so generated SQL matches the schema.

**Indexes:** `customers(customer_unique_id)`, `orders(customer_id)`, `orders(order_status)`,
`orders(order_purchase_timestamp)`, `order_items(product_id)`, `order_items(seller_id)`,
`order_reviews(order_id)`, `geolocation(geolocation_zip_code_prefix)`,
`products(product_category_name)`.

**Geolocation note:** 1M rows. Use `chunksize=50_000` in `df.to_sql`. After each table load,
`del df; gc.collect()` to release memory. Run `ANALYZE` after all tables are loaded.
Close with `PRAGMA foreign_key_check`.

### backend/app/pipeline/execute.py

Security model — belt-and-suspenders, outermost to innermost:
1. sqlglot AST validation: reject non-SELECT before any DB contact. Fails CLOSED.
2. LIMIT injection: inject or clamp to 500 rows via AST.
3. Read-only SQLite URI: `file:path?mode=ro` — OS-level `O_RDONLY` backstop.
4. Statement timeout: `threading.Timer` + `conn.interrupt()`.

**Forbidden root types (verified against sqlglot 25 with `uv run --with sqlglot`):**

```python
_FORBIDDEN_ROOT_TYPES = (
    exp.Insert, exp.Update, exp.Delete,
    exp.Drop, exp.Create, exp.Alter,
    exp.Attach, exp.Pragma,           # verified: ATTACH->exp.Attach, PRAGMA->exp.Pragma
    exp.Transaction, exp.Commit, exp.Rollback,
    exp.Command,                      # catch-all for unmodelled statements
)
```

**CTE handling:** `WITH...SELECT` parses as root `exp.Select` (not `exp.With`). The WITH
clause is stored in `stmt.args["with"]`. A plain `isinstance(stmt, exp.Select)` check
covers both CTEs and plain SELECTs. No special branch needed.

**LIMIT injection:**
```python
existing_limit = statement.args.get("limit")
if existing_limit is None:
    statement = statement.limit(default_limit)   # .limit() returns new node — reassign
else:
    limit_expr = existing_limit.args.get("this")
    if isinstance(limit_expr, exp.Literal) and limit_expr.is_number:
        if int(limit_expr.this) > default_limit:
            statement = statement.limit(default_limit)
return statement.sql(dialect="sqlite")
```

Verified: `statement.limit(500)` on a CTE correctly emits `WITH c AS (...) SELECT ... LIMIT 500`.

**Forbidden functions** (checked via `statement.find_all(exp.Anonymous)`):
`load_extension`, `writefile`, `edit`.

**Connection:**
```python
sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
```

**Timeout:**
```python
timer = threading.Timer(timeout_seconds, conn.interrupt)
timer.start()
try:
    cursor = conn.execute(final_sql)
    ...
except sqlite3.OperationalError:
    if timed_out:
        return ExecutionResult(..., timed_out=True)
    raise
finally:
    timer.cancel()
    conn.close()
```

`conn.interrupt()` on a closed connection is a no-op in CPython sqlite3. Safe.

### backend/tests/test_execute.py

Unit tests for `validate_and_inject` (no DB): SELECT passes, CTE passes, LIMIT preserved,
LIMIT clamped, INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/ATTACH/PRAGMA rejected, multi-statement
rejected, `load_extension` rejected, empty/whitespace/parse-error rejected, subquery passes.

Integration tests: `tmp_path` fixture creates a minimal SQLite DB. Covers: execute returns rows
and columns, LIMIT injected into `sql_executed`, existing LIMIT respected, ValidationError on
invalid SQL, timeout via recursive CTE with `timeout_seconds=0.05`.

### backend/tests/test_server_rss.py

Starts uvicorn on port 8765 as a subprocess, polls `/health` (15s timeout), measures
`psutil.Process(pid).memory_info().rss`, prints MB value, asserts < 4096 MB. Terminates
cleanly in fixture teardown.

### Risk flags

| Risk | Mitigation |
|---|---|
| pandas imported in server | mypy excludes `data/`; RSS test detects ~80 MB blowup |
| sqlglot API change | Pin `<26`; ATTACH and PRAGMA tests catch regressions |
| Geolocation OOM | `chunksize=50_000`, `del df; gc.collect()` after each table |
| `.limit()` returns new node | Assign back: `statement = statement.limit(n)` |
| Port 8765 collision | Fixed obscure port; document in test file |

---

## Phase 1 — Core text-to-SQL

**Done when:** straightforward Olist questions answer correctly end-to-end via CLI and
`/ask`, with offline gates green and a recorded live smoke.

**Verified gate results:** (2026-06-09, anthropic 0.107.1, Python 3.12.13)
- [x] `uv run ruff check backend/ data/ eval/` — clean
- [x] `uv run mypy backend/` — clean (strict, 21 files)
- [x] `uv run pytest backend/tests/ -q` — 52 passed, idle RSS still **5.6 MB**
- [x] Live CLI smoke against the Anthropic API (claude-sonnet-4-6) — **5/5 correct,
  all on the first attempt** (no self-correction, no timeouts):
  - "top 5 product categories by revenue" -> joins through the translation table,
    `SUM(price)` excluding freight (semantic layer), bar. Top: health_beauty 1,258,681.34.
  - "how many orders were delivered" -> `COUNT(DISTINCT order_id) WHERE order_status='delivered'`,
    stat. **96,478**.
  - "average review score by product category" -> 4-way join, 74 rows, bar.
  - "orders per month in 2017" -> STRFTIME month + `COUNT(DISTINCT order_id)`, 12 rows, line
    (Nov spike 7,544).
  - "top 10 sellers by revenue" -> `SUM(price)` per seller, bar.

**What shipped:**
- `config.py` (env settings), `llm.py` (LLMClient protocol + AnthropicClient adapter using
  `messages.parse` structured outputs, system prompt cached via `cache_control`)
- `semantic_layer.py` (business-term resolutions), `pipeline/schema.py` (read-only
  introspection + hand-authored Olist descriptions, retrieval seam)
- `pipeline/route.py` (model seam), `pipeline/generate.py` (structured `SqlGeneration`
  + self-correction loop), `pipeline/answer.py` (orchestrator + chart heuristic)
- `cli.py` and `POST /ask` (settings + client injected as FastAPI dependencies)
- 21 new mocked tests; fixture DB only, never the real demo.db

**Decisions confirmed during build (see docs/DECISIONS.md):**
- anthropic 0.107.1 has `messages.parse(output_format=Model)`; result via `.parsed_output`
- Server does not import the SDK at startup (lazy import in `build_client`), so idle RSS holds at 5.6 MB

**Live smoke observations (carry into Phase 2/3):**
- Sonnet 4.6 used the semantic layer correctly without prompting per-question, and
  reached for the translation table and STRFTIME unaided.
- Zero self-correction across 5 questions: the cap-2 repair loop is in place but the
  Olist happy-path rarely exercises it. Phase 3 (BIRD) will stress it.
- The sqlglot round-trip re-emit caused no observed query mangling on these (no named-column CTEs).

---

## Phase 2 — Trust layer

**Done when:** an ambiguous question returns a clarifying question with options, and a clear
question returns an answer plus a structured assumptions panel and a (provisional) confidence
score, end-to-end via CLI and `/ask`, with offline gates green and a recorded live smoke.

**Gate results:** (2026-06-09, anthropic 0.107.1)
- [x] `uv run ruff check backend/ data/ eval/` — clean
- [x] `uv run mypy backend/` — clean (strict, 27 files)
- [x] `uv run pytest backend/tests/ -q` — 72 passed, idle RSS still **5.6 MB**
- [x] Live smoke (claude-sonnet-4-6, K=5):
  - clear ("how many orders delivered") -> answer 96,478, assumptions (delivered + order count
    terms, table, filter, limit), confidence 1.00 across 5 samples (provisional/uncalibrated)
  - ambiguous ("top products last quarter") -> clarification flagging metric + time_window, 4 options
  - clarify follow-up (`--clarify "by total revenue, calendar Q4 2018"`) -> proceeds, CTE query,
    full assumptions surfaced, confidence 1.00 (0 rows: Olist data barely covers Q4 2018 -
    correct query, honest empty result)

**Findings (see docs/DECISIONS.md):** term-matching by columns/functions/literals is
alias-independent; CLI now forces UTF-8 stdout; ambiguity prompt restricted to ASCII punctuation
to honor the no-em-dash rule for user-facing clarifying copy.

### Decisions (locked)
- Assumptions: deterministic from the executed SQL via sqlglot (tables, joins, filters, grain,
  LIMIT) + matched semantic-layer terms. No extra LLM call.
- Answer selection: displayed answer is the temp-0 generation (reproducible); K-1 temp>0 samples
  vote only for the agreement fraction.
- Confidence: shown, labeled provisional (`calibrated=False`) until Phase 3 fits the isotonic map.
- K (self-consistency samples): default 5, configurable.

### Files to create
```
backend/app/pipeline/ambiguity.py     # AmbiguityReport + detect_ambiguity (clarify or proceed)
backend/app/pipeline/assumptions.py   # pure: sqlglot SQL -> Assumptions
backend/app/pipeline/confidence.py    # self-consistency, canonicalize_rows, calibration seam
backend/tests/test_ambiguity.py
backend/tests/test_assumptions.py
backend/tests/test_confidence.py
```

### Files to modify
```
backend/app/config.py        # self_consistency_samples (5), _temperature (0.7), calibration_path
backend/app/pipeline/answer.py   # respond() + Clarification/Assumptions/Confidence/TrustedResponse
backend/app/main.py          # /ask returns TrustedResponse (kind-based) + clarification_answer field
backend/app/cli.py           # render clarification vs answer + assumptions + provisional confidence
backend/tests/conftest.py    # FakeLLMClient type-aware (match output_format); new Settings fields
backend/tests/test_answer.py # extend: respond clear/clarify paths + /ask shapes
```

### Key designs
- `respond(question, *, client, settings, clarification_answer=None)`: detect_ambiguity ->
  if needs_clarification and no clarification_answer, return `kind="clarification"`; else run the
  Phase 1 temp-0 `generate_with_self_correction` (primary/displayed answer), extract assumptions
  from `primary.sql`, run self-consistency for agreement, compute confidence. Returns a
  `kind`-based `TrustedResponse`.
- raw confidence = `agreement * (0.85 if self_correction_fired else 1.0) * retrieval_score`
  (retrieval_score placeholder 1.0; Phase 3 supplies the real value). `calibrated=False` until
  `load_calibration_map` finds a real map at `calibration_path`.
- `canonicalize_rows` (sort rows, round floats) lives in confidence.py; Phase 3 `eval/metrics.py`
  reuses it.

### Risks (see plan file for full table)
Over-asking (conservative prompt; measured Phase 3); K-call cost (prompt caching + Phase 6 Haiku
routing); float-noise agreement (canonicalize); term-match heuristic (structural parts exact);
confidence not a measured metric (provisional label, no claims until Phase 3).

---

## Phase 3 — Eval harness

**Done when:** one command produces a committed `eval/out/eval_results.json` (+ `calibration.json`)
on a pinned subset within budget, numbers are reproducible, offline gates green, and the fitted
calibration map is picked up by the server (`confidence.calibrated == True`).

**Gate results:** (2026-06-09, claude-sonnet-4-6 — matches the demo — K=5, 240 of the 300-question
pool; re-run from the budget-shaped Haiku/100 pilot now that funds were added. ~$9.28 total spend.)
- [x] `uv run python eval/prep_bird.py` — extracted 11 DBs; pinned pool 300 (182/89/29 simple/mod/chal)
- [x] `uv run python eval/run_bird.py --dry-run --limit 3` — plumbing OK, no API
- [x] `uv run ruff check backend/ data/ eval/` — clean
- [x] `uv run mypy backend/ eval/` — clean (strict, 36 files; eval type-checked)
- [x] `uv run pytest backend/tests/ -q` — 86 passed
- [x] **Sonnet run (240 questions, K=5):**
  - execution accuracy **55.8%**; semantic-error rate **44.2%**; clarification rate **0%** on BIRD
    (those questions are well-specified, so the gate correctly never fires)
  - **calibration is the headline: ECE 0.439 -> 0.149, Brier 0.422 -> 0.252** on a randomized
    held-out split (test_n=96); the isotonic map ships because it improves held-out calibration
  - **self-consistency is a weak raw signal here:** 215/240 questions hit full agreement (raw 1.0)
    despite 56% accuracy. The model is confidently consistent even when wrong; calibration is what
    makes confidence honest (deflates raw 1.0 -> ~0.71)
  - confidently-wrong: baseline **0.433**; with-trust at 0.8 = **0.0** (an ARTIFACT: calibrated
    confidence rarely reaches 0.8 because true accuracy is ~56%). Threshold sweep is the honest read:
    at 0.6, **0.433 -> 0.363**. We do NOT headline a "100% reduction".
  - clarification (labeled set): **precision 1.00, recall 0.69, over-ask 0.0**
  - eval peak RSS **96 MB** (separate offline process, well under 4 GB)
- [x] Server picks up the fitted map: `load_calibration_map(...).calibrated == True` (apply(1.0)=0.71)
- [x] **Trap eval (the signature metric; Sonnet, 27 traps + 15 clear controls, ~$0.88) — `eval/out/trap_results.json`:**
  - **baseline confidently answers 100% of traps -> trust answers 40.7%: a 59pp absolute reduction**,
    with **0% over-decline** on clear controls (trust answered all 15)
  - clarification P/R on genuine ambiguity: **precision 1.00, recall 0.70**
  - by category (trust still-answered = slip-through): metric **0%**, time **0%**, unanswerable **33%**,
    grain **67%**, entity **100%**, prompt_injection **100%**
  - honest reading: strong on metric/time ambiguity; weak on grain/entity; the ambiguity gate does
    NOT detect prompt injection (the SELECT-only validator is the injection backstop, and it holds).
    Mean confidence is lower on answered traps (0.63) than clear (0.69) but only weakly separating.

**Numbers are a pinned-subset Sonnet result (240 of 1534 BIRD dev), reported with N and caveated.**
The committed `eval/out/eval_results.json` + `calibration.json` are the reproducible record.

**Methodology fixes applied during the re-run (see docs/DECISIONS.md):** randomized (not
DB-sequential) calibration split; metrics computed from raw confidence, calibration applied
post-hoc; the isotonic map ships only if it beats raw on held-out data; a confidently-wrong
threshold sweep replaces a single hand-picked cutoff; `--reaggregate`/`--cost` for free recompute.
Earlier finding still stands: `build_schema_card` now quotes PRAGMA table names (reserved word `order`).

### Phase 3 addendum: trap eval (earn the signature confidently-wrong reduction)

**Why:** BIRD questions are well-specified, so the clarification arm never fires and the
confidently-wrong reduction is not demonstrated on BIRD (it's a calibration artifact at 0.8).
The signature metric needs questions that *should not* be confidently answered.

**Design (Olist demo DB; reuses the harness; uses the shipped calibration map):**
- Expand `eval/labeled_ambiguity.json` to ~40-55 items, each tagged `category`
  (ambiguous_metric, ambiguous_time, grain, entity, unanswerable, prompt_injection) and
  `ambiguous` (=should-decline) plus ~15 `clear` controls.
- `eval/run_traps.py`: for each item run BOTH pipelines.
  - trust outcome: clarified | flagged_low_conf (calibrated confidence < threshold) | answered_confidently.
  - baseline (no trust): answered (executed) | failed.
  - "confidently wrong" on a should-decline question = produced a confident executed answer.
- Metrics (`eval/metrics.py`): baseline confidently-answered rate vs trust confidently-answered
  rate on should-decline items (the reduction = signature); over-decline rate on `clear` items (cost).
- Output committed `eval/out/trap_results.json`. Mocked test for the runner. ~$1-2 paid run.
- Confidence-resolution finding documented in `docs/limitations.md` (not strengthened now).

### Decisions (locked)
- Scope: pinned BIRD subset stratified by db_id x difficulty (committed ids, seeded). Re-run on
  Sonnet 4.6, K=5, 240 questions (was Haiku/100 under the old budget). Numbers caveated as pinned-subset.
- Retrieval deferred: full per-DB schema cards via `build_schema_card`; retrieval_score stays 1.0.
- Calibration: pure-Python PAVA isotonic on a held-out train split; ECE/Brier on the test split
  (raw vs calibrated); write `eval/out/calibration.json` (`{"type":"isotonic","x","y"}`); wire back.
- Labeled ambiguity set: commit `eval/labeled_ambiguity.json` (trap + clear, tagged by dimension)
  to measure clarification precision/recall and penalize over-asking; seeds the Phase 5 gallery.

### Files to create
```
eval/prep_bird.py            # offline unzip + pinned stratified subset
eval/bird_subset.json        # committed pinned question_ids
eval/labeled_ambiguity.json  # committed trap + clear labels
eval/run_bird.py             # offline batch: with-trust + without-trust, resumable
eval/metrics.py              # pure metric fns (reuses confidence.canonicalize_rows)
eval/calibrate.py            # PAVA isotonic fit -> calibration.json
eval/ablation.py             # confidently-wrong with vs without trust
backend/tests/test_metrics.py, test_calibrate.py, test_run_bird.py
```

### Files to modify
```
backend/app/llm.py   # AnthropicClient accumulates token usage (cost tracking); Protocol unchanged
pyproject.toml       # remove eval/ from mypy exclude (type eval now)
.gitignore           # un-ignore eval/out/eval_results.json + calibration.json (commit for reproducibility)
```

### Key designs
- Runner composes pipeline building blocks directly (detect_ambiguity -> generate_with_self_correction
  -> execute -> self_consistency -> compute_confidence) with a BIRD schema card and empty semantic
  layer, so product `respond()` stays unchanged. BIRD `evidence` is folded into the question.
- Gold SQL executes raw read-only (no validator re-emit) so backticks and >500-row results survive;
  predicted goes through the product sandbox with a high eval row cap. Match via `canonicalize_rows`.
- Confidently-wrong (with trust) = not-clarified + executed + wrong + score>=0.8; baseline = all
  semantic errors. The reduction is the signature number.
- Resumable: append records to `eval/out/results.partial.jsonl`, skip done ids on rerun; `--max-cost` abort.

### Risks (see plan file for full table)
Cost overrun (Haiku+K=3+~100, --max-cost, resumable, caching); small-N noise (caveat); sqlglot
re-emit on predicted (faithful to product; gold raw); LIMIT truncation (high eval cap); temp>0
non-determinism (temp-0 primary reproducible, committed JSON canonical); eval memory (one DB at a time).

---

## Phase 4 — Frontend core (/ask + design system)

**Done when:** the demo DB is fully usable through the browser - a polished, responsive `/ask`
page that streams the trust pipeline stage by stage and renders the full answer card (answer,
SVG chart, sortable table, SQL+copy, assumptions, calibrated confidence, collapsible grounding),
plus the clarify-then-answer flow. Showcase pages are Phase 5.

**Gate results:** (2026-06-09, Next 16.2.7, React 19.2.7, Tailwind 4.3, shadcn radix-nova)
- [x] backend: ruff + mypy strict (39 files) clean; 92 tests pass (incl. test_stream); idle RSS **5.6 MB**
- [x] frontend: `npm run lint` clean, `npx tsc --noEmit` clean, `npm run build` succeeds (Turbopack)
- [x] E2E live (real Sonnet via the Next /api proxy):
  - clear ("how many orders were delivered") -> stages stream -> answer card: stat **96,478**,
    syntax-highlighted SQL + copy, assumptions (orders / delivered filter), confidence **0.71 calibrated**
  - ambiguous ("who are the top sellers") -> clarification card flagging **metric** with 4 option chips
  - Playwright screenshots (hero / answer / clarify) reviewed: dark canvas, cyan accent, Geist,
    depth cards with halo - reads as a shipped product, not a resume project

### Versions (verified current 2026-06)
Next.js 16.2.x (Turbopack default, React 19.2), Tailwind 4.3.x, shadcn/ui (Tailwind v4 mode),
Node 22 LTS. Backend already current via uv floors; `sqlglot<26` is the only deliberate pin.

### Decisions (locked)
- UI primitives: **shadcn/ui** (Radix, accessible) themed via Tailwind v4 `@theme`; charts hand-built SVG.
- Streaming: **real backend SSE** - refactor `respond()` into an event generator; `POST /ask/stream`
  emits true stages; the UI shows genuine per-stage progress.
- Scope: design system + complete `/ask` only.

### 4 GB RAM guard (non-negotiable)
The SSE endpoint runs in the uvicorn process: it reuses the existing pipeline, imports nothing heavy,
and keeps anthropic lazy-imported. CORS middleware (starlette) is light. The RSS test must stay green
after the backend change. The frontend is a separate Node/Vercel process, not subject to the server budget.

### Skills -> tasks (how we hit "premium, major-company feel")
frontend-design (visual system, answer card) · tailwind-v4-shadcn (scaffold/theme) ·
nextjs-app-router-patterns (App Router + streaming) · framer-motion-animator (micro-interactions,
prefers-reduced-motion) · frontend-ui-dark-ts (dark depth-card aesthetic) · tailwind-design-system
(tokens) · chart-visualization (SVG charts) · webapp-testing + playwright-cli (verify + screenshots).

### Part A - backend streaming
- `answer.py`: `StageEvent` + `respond_events(...) -> Iterator[StageEvent]` yielding
  stage events (ambiguity -> generating -> executing -> confidence) then a terminal
  clarification/answer; `respond()` drains it (one path, existing /ask unchanged).
- `main.py`: `POST /ask/stream` -> `StreamingResponse(text/event-stream)`; add light CORS.
- `tests/test_stream.py`: assert SSE event order for clear + ambiguous (FakeLLMClient).

### Part B - frontend scaffold (frontend/)
create-next-app (App Router, TS strict, Tailwind v4, ESLint, Turbopack); shadcn init + primitives
(button, card, dialog, tabs, tooltip, dropdown-menu, table, badge, skeleton, sonner, separator,
scroll-area); `@theme` tokens (canvas #0c0c0e, off-white text, cyan #22d3ee, Geist Sans/Mono, OKLCH,
dark default); `next.config.ts` rewrite `/api/:path*` -> `${API_BASE:-http://localhost:8000}`.

### Part C - /ask (`/` is the ask page)
`useAskStream` (POST /api/ask/stream, parse SSE, stage state machine) · `QuestionInput` (starter chips)
· `ConversationThread` · `AnswerCard` (plain answer, `Chart` by chart_type stat|bar|line|table|none,
sortable `ResultTable`, `SqlBlock` copy, `AssumptionsPanel`, `ConfidenceBadge` calibrated-vs-provisional,
collapsible `Grounding`) · `ClarificationCard` (option chips -> re-stream with clarification_answer) ·
`StageProgress`. Hand-built SVG charts, ARIA-labelled; framer-motion micro-interactions with
prefers-reduced-motion; mobile-first. `lib/types.ts` mirrors backend shapes.

### Risks (see plan file for full table)
SSE buffering through the Next proxy (verify early; fall back to CORS+direct origin); RSS creep
(re-run test); shadcn/Tailwind v4 setup churn (follow the skill); generic-AI look (drive with
frontend-design); respond() refactor regressing non-streaming /ask (drain same generator; tests green).

---

## Phase 5 — Showcase pages

**Done when:** /gallery, /evals, /methodology, /limitations render; the gallery contrast and the
dashboard metrics are real (from committed JSON); offline + frontend gates green; screenshots reviewed.
All four are static (no backend) -> Vercel-ready ahead of Phase 6.

**Gate results:** (2026-06-09)
- [x] backend: ruff + mypy strict (41 files) clean; 94 tests pass (incl. test_gallery); 4 GB unaffected
- [x] paid gallery capture (Sonnet, ~$0.28) -> committed `eval/out/gallery.json` (12 cards, 3 clarify)
- [x] frontend: lint clean, tsc clean, `next build` -> **all 5 routes prerender as static** (/, /evals,
      /gallery, /methodology, /limitations) -> the showcase pages need no backend (Vercel-ready)
- [x] Playwright screenshots of all four reviewed: /evals dashboard (signature ablation 100%->41%,
      reliability diagram near the diagonal, by-category slip-through, clarification 1.00/0.70/0.00),
      /gallery contrast cards, /methodology + /limitations. Numbers match the committed JSON.

### Decisions (locked)
- /gallery: capture REAL baseline-vs-Prompt Data outputs via `eval/run_gallery.py` -> `gallery.json` (I run it, ~$1-1.5).
- /methodology + /limitations: recruiter-friendly authored TSX (NOT the raw docs/*.md); numbers imported from committed JSON.
- Data: committed `frontend/content/*.json` (copies), refreshed by a sync script on predev/prebuild (Vercel-safe).
- Honest framing: trap result (baseline 100% -> Prompt Data 41%, 59pp) is the headline; BIRD = accuracy + calibration (ECE 0.44->0.15), caveated with N.

### Parts
- A: `eval/run_gallery.py` (~12 curated questions: traps + 1-2 hard answerable; baseline + respond()) -> `gallery.json`; `test_gallery.py` mocked.
- B: `frontend/scripts/sync-content.mjs`; committed `frontend/content/{eval_results,trap_results,gallery}.json`; `lib/eval-types.ts`; predev/prebuild hooks.
- C: `/evals` static page + `components/evals/*` (metric cards, signature ablation bars, reliability diagram, calibration before/after, trap by-category, clarification P/R, cost/latency) reusing Phase 4 SVG primitives.
- D: `/gallery` static page + `components/gallery/*` (naive vs Prompt Data cards, category filter) reusing `components/ask/*` + `charts/*`.
- E: `/methodology` + `/limitations` authored TSX, numbers from `content/*.json`.
- F: nav links in `app/layout.tsx` (Ask, Gallery, Evals, Methodology, Limitations), active-route styling.

### Risks (see plan file)
Vercel build context (commit content/*.json); weak contrasts (capture ~14, feature best ~10);
number drift (import JSON); capture cost (dry-run first, ~$1.5); dashboard overclaiming (trap headline, BIRD caveated).

---

## Phase 6 — Deploy (Vercel frontend + Render backend)

**Done when:** the repo is deploy-ready (prod config + spend guard + slim committed DB + Docker)
and pushed to github.com/shanethakkar/prompt-data, with a `docs/DEPLOY.md` runbook. Cloud go-live
(Render + Vercel dashboards, secrets) is user-driven via the runbook.

**Gate results:** (2026-06-09)
- [x] slim DB: 110 MB uncompressed -> shipped as committed `data/demo.db.gz` (**50.9 MB**, decompressed
      at Docker build); no geolocation, no review free-text; delivered=96,478 (matches the gallery)
- [x] backend: ruff + mypy strict (43 files) clean; **98 tests** (incl. 4 test_ratelimit); idle RSS **5.6 MB**
- [x] spend guard verified live: 1st /ask/stream streams answer (96,478), 2nd -> **429** + Retry-After;
      CORS header returned for the allowed origin; /health unaffected
- [x] frontend: lint, tsc, build green (5 static routes); fetch uses NEXT_PUBLIC_API_BASE in prod
- [~] Dockerfile + .dockerignore written and inspected; Docker not installed locally -> Render builds in cloud
- [x] Dockerfile/render.yaml/DEPLOY.md complete; push to github.com/shanethakkar/prompt-data

### Decisions (locked)
- Host: **Render** (Docker, render.yaml blueprint). demo.db: **slim, committed** (drop geolocation).
- Frontend->backend: **direct CORS in prod** (NEXT_PUBLIC_API_BASE -> Render); local keeps /api rewrite.
- GitHub: repo github.com/shanethakkar/prompt-data; push with the machine's credentials.

### Parts
- A: `load_olist.py --skip-geolocation` + VACUUM; commit slim `data/demo.db` (un-ignore); Makefile
  `load-db` (slim) + `load-db-full`; the committed gallery/eval JSON is unaffected (no geo questions).
- B: `config.py` add `cors_origins`/`rate_limit_per_minute`/`daily_request_cap`; new
  `backend/app/ratelimit.py` (in-memory per-IP window + global daily cap, UTC reset); `main.py`
  env-driven CORS + guard on /ask & /ask/stream (not /health); `test_ratelimit.py`.
- C: `Dockerfile` (python:3.12-slim + uv, COPY backend/ + slim demo.db + calibration.json);
  `.dockerignore` (exclude data/raw 1.9 GB, demo.full.db, frontend, .next, node_modules, .git);
  `render.yaml` (docker web service, healthCheckPath /health, secrets sync:false).
- D: `lib/use-ask.ts` endpoint base from `NEXT_PUBLIC_API_BASE` (prod direct CORS) else `/api`
  (local proxy); `.env.local.example`.
- E: `docs/DEPLOY.md` runbook (GitHub push, Render blueprint + secrets, Vercel import + env, smoke test).

### Risks (see plan file)
slim DB >100 MB (drop review_comment_* then git-lfs); Vercel SSE proxy timeout (direct CORS);
Render cold start (documented, $7 always-on option); /ask abuse (guard); XFF parsing behind proxy.

---

## Phase 7 — Usability + bring-your-own-data

**Live feedback (prompt-data.vercel.app):** charts lack x/y axes; users can't see the schema so they
don't know what to ask; no way to query their own data. Plus polish: cold-start warming, README,
CSV export, shareable links, mobile/a11y. All backend work holds the 4 GB ceiling and the
SELECT-only/read-only backstop. **Doing A + B first, then C-H.**

### Decisions (locked)
- Upload supports both CSV and .db; per-session, ephemeral (TTL), strict caps (Part C, later).
- Custom datasets: semantic layer off + confidence shown uncalibrated (honest; map was fit on Olist).

### Part A - chart axes (now)
`frontend/components/charts/chart.tsx`: real axes on BarChart + LineChart (axis lines, ticks, light
gridlines, nice-rounded numeric scale), responsive + ARIA. Shared `niceTicks` helper. StatCard unchanged.

### Part B - schema explorer (now)
- Backend: `schema_tables(db_path) -> list[TableInfo]` in `pipeline/schema.py` (structured reuse of
  PRAGMA introspection + TABLE_DESCRIPTIONS/COLUMN_NOTES + row counts); bound `build_schema_card`
  lru_cache. `GET /schema` in `main.py` (optional `session` param; resolves to Olist until Part C).
- Frontend: `lib/api.ts` `apiUrl()`; shadcn Sheet; `SchemaDrawer` ("Data" trigger on /ask) listing
  tables/columns/descriptions from `/schema`.

### Parts C-H (later): BYO upload (CSV + .db, sessions, caps), cold-start warming + states, CSV
download, shareable ?q= links, repo README, apiUrl reuse, mobile/a11y sweep.

**Gate results (A+B):** *(fill in)*  backend ruff/mypy/pytest + RSS; frontend lint/tsc/build; screenshots.
