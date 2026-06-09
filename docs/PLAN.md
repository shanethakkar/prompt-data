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
| 1 | Core text-to-SQL | **Code-complete** (offline gates green; live smoke pending API key) |
| 2 | Trust layer | Not started |
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
- [ ] Live CLI smoke against the Anthropic API — **PENDING**: no `ANTHROPIC_API_KEY`
  configured (no `.env`). Cannot run without a key; results will not be fabricated.

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

**Remaining to close Phase 1:** run the live smoke once a key is available, record the
generated SQL / row counts / any self-correction here, then mark complete.

---

## Phase 2 — Trust layer *(expand before starting)*

Deliverables: ambiguity detection and clarifying questions, assumption extraction,
self-consistency confidence, placeholder calibration map.

Done when: an ambiguous question triggers a clarifying question; a clear one returns
assumptions and a confidence signal.

*Expand this section at the start of Phase 2.*

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
