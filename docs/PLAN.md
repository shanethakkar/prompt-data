# Verity — Active Build Plan

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
| 3 | Eval harness | Not started |
| 4 | Frontend core | Not started |
| 5 | Showcase pages | Not started |
| 6 | Production and polish | Not started |

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

## Phase 3 — Eval harness *(expand before starting)*

Deliverables: BIRD runner, all metrics (exec accuracy, semantic-error rate, calibration,
clarification precision/recall, cost/latency), trust-layer ablation, fitted calibration map,
JSON output. Done within the 4 GB memory budget.

*Expand this section at the start of Phase 3.*

---

## Phase 4 — Frontend core *(expand before starting)*

Deliverables: Next.js 16 App Router scaffold, /ask page with full answer card, clarify-then-answer
flow, streaming, design system (dark theme, cyan accent, Geist fonts, SVG charts).

*Expand this section at the start of Phase 4.*

---

## Phase 5 — Showcase pages *(expand before starting)*

Deliverables: /gallery (trap questions), /evals (reading Phase 3 output), /methodology,
/limitations.

*Expand this section at the start of Phase 5.*

---

## Phase 6 — Production and polish *(expand before starting)*

Deliverables: model routing and cost tracking, prompt-injection hardening, optional
bring-your-own-DB, accessibility and mobile sweep, deploy, README with measured headline
numbers and verified peak RSS.

*Expand this section at the start of Phase 6.*
