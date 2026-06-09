# Verity — Decisions and Findings

Lightweight record of non-obvious implementation discoveries, API quirks, and
architectural choices made during the build. Each entry explains the context,
what was found or decided, and why it matters for future work.

When to add an entry: any time something would have surprised you if you had not
already discovered it, or any time a choice was made between real alternatives.
Do not record things that are obvious from the code or spec.

---

## [Phase 1] pre-commit must use the project's own ruff (version drift bites)

**Context:** The first Phase 1 commit was blocked by the pre-commit hook reporting a ruff
error (`UP`, "convert to X | Y") that `uv run ruff check` did not report.

**Cause:** `.pre-commit-config.yaml` pinned `astral-sh/ruff-pre-commit` at `v0.6.9`, but the
dev dependency is ruff `0.15.16`. The two versions disagree on lint/format output, so the
hook and the `make lint` gate gave different results.

**Fix:** switched `.pre-commit-config.yaml` to `repo: local` hooks that call
`uv run ruff check --fix` and `uv run ruff format` (`language: system`). The hook now uses
the exact ruff pinned in `uv.lock`, so the hook and the gate can never drift. pre-commit was
also added to the dev group and the hook reinstalled so `.git/hooks/pre-commit` points at the
persistent `.venv` interpreter (an ephemeral `uv run --with pre-commit` install left the hook
unable to find `pre-commit`).

---

## [Phase 2] Assumption term-matching is alias-independent (columns/functions/literals)

**Context:** The Assumptions panel must say which semantic-layer terms a query used, but the
generated SQL aliases tables (`SUM(oi.price)`), so a literal substring match against the term's
expression (`SUM(order_items.price)`) fails.

**Decision:** match on the *signature* of each term, not its text: the set of column names
(`exp.Column.name`, which is alias-independent), function names (`type(node).__name__.lower()`,
not sqlglot's untyped `sql_name()`), and string literals it resolves to. A term matches when all
three signature sets are subsets of the query's. This correctly matches `SUM(oi.price)` to revenue
and avoids false `spend` matches (which also need `freight_value`). Structural assumptions
(tables/joins/filters/grain/limit) are exact from the AST.

**mypy note:** sqlglot's `Func.sql_name()` and `Expression.flatten()` are untyped (no-untyped-call
under strict). Use `type(node).__name__.lower()` for function names and a small typed
`_split_and` helper (recursing via `node.args`) instead of `flatten()`.

---

## [Phase 2] CLI forces UTF-8 stdout; clarifying copy restricted to ASCII

**Context:** A live clarification rendered `Jan�Mar` on the Windows console: the model emitted an
en-dash and the default cp1252 stdout could not encode it. Separately, the no-em-dash rule
(CLAUDE.md) applies to user-facing copy, and clarifying questions/options are user-facing.

**Decisions:**
- `cli.py` calls `sys.stdout.reconfigure(encoding="utf-8")` at startup (guarded) so model/schema
  text renders correctly regardless of the console code page.
- The ambiguity system prompt now instructs plain ASCII punctuation (hyphens/commas/colons, no
  em or en dashes) so generated clarifying copy complies with the plain-copy rule.

---

## [Phase 5] Showcase pages: static, honest, Vercel-ready

- **All four showcase routes prerender as static** content from committed JSON (`frontend/content/*.json`,
  synced from `eval/out` by `scripts/sync-content.mjs` on predev/prebuild). They need no backend, so the
  site is largely deployable to Vercel ahead of Phase 6 (only `/ask` needs the hosted API).
- **Committed the content copies** (not gitignored) so the Vercel build (root = frontend/) is
  self-contained regardless of whether `../eval/out` is in the build context. The sync script only
  refreshes them.
- **Gallery is honest, not cherry-picked.** The capture (`run_gallery.py`, ~$0.28) shows 3 clarifications
  and the rest answered with surfaced assumptions + confidence. None are embarrassing: the "email"
  unanswerable returns an explicit "no email data" message, and the prompt-injection card neutralizes the
  attack (counts customers, refuses PII) at confidence 0.24. The under-caught categories (grain, entity,
  injection) are shown plainly on /evals rather than hidden.
- **/methodology and /limitations are audience-authored TSX** (recruiter-friendly), distinct from the
  engineering `docs/*.md`; key figures import from the committed JSON so prose and numbers never drift.
- **Dev note:** a TaskStop'd `next start` can leave an orphan bound to :3000; use a fresh port for
  follow-up previews rather than hunting the PID on Windows.

---

## [Phase 4] Frontend scaffold + streaming findings

- **create-next-app pulled a preview Next (16.3.0-preview.0)** whose SWC binary 404'd. Pinned
  `next` and `eslint-config-next` to the stable **16.2.7** LTS (`--save-exact`); builds cleanly.
- **shadcn CLI changed:** `-b` is now the primitive base (`radix`|`base`), not base color, and init
  prompts for a preset even with `-y`. Used `init -y -f -b radix -t next -p nova` - the **Nova preset
  ships Geist + Lucide**, matching the spec aesthetic. Style key is `radix-nova`.
- **Font-variable mismatch:** the Nova `globals.css` `@theme` maps `--font-sans`, but the scaffold's
  layout declared `--font-geist-sans`. Fixed layout to use `variable: "--font-sans"` / `--font-geist-mono`.
- **SSE through the Next dev/start proxy works** with no buffering (rewrite `/api/:path*` ->
  backend). Verified the full path browser -> Next proxy -> FastAPI -> SSE stages -> answer with a
  real Sonnet call; no CORS needed (CORS middleware kept as a fallback). `X-Accel-Buffering: no` set.
- **4 GB guard held:** the SSE endpoint reuses the pipeline and imports nothing heavy; idle server
  RSS unchanged at 5.6 MB. The frontend is a separate Node process.
- **Streaming pattern:** sync FastAPI endpoint + sync generator so Starlette iterates it in a
  threadpool (blocking Anthropic calls do not block the event loop); single worker, low concurrency.

---

## [Phase 3] Trap eval earns the signature metric that BIRD cannot

**Context:** BIRD questions are well-specified, so the clarification arm never fires and the
confidently-wrong reduction was undemonstrated. Added a trap eval (`eval/run_traps.py`) over the
Olist demo: 27 should-decline questions (ambiguous, unanswerable, prompt-injection) + 15 clear
controls, running the trust pipeline vs a no-trust baseline.

**Result (Sonnet 4.6):** baseline confidently answers **100%** of traps; the trust layer answers
**40.7%** (clarifies or fails the rest) — a **59 pp** reduction — while answering **all** clear
controls (0% over-decline). Threshold-free headline: clarification is the primary defense, so the
metric is simply "did the layer answer a question it shouldn't have."

**Honest category breakdown (where it still slips):** metric/time ambiguity caught 100%;
unanswerable 67%; grain 33%; entity 0%; prompt_injection 0%. Two takeaways recorded in
`docs/limitations.md`: (1) the ambiguity gate is not an injection detector — the SELECT-only
validator is the injection backstop and it holds (no write ever executes); (2) grain/entity
ambiguity is under-caught. Clarification P/R on genuine ambiguity: precision 1.00, recall 0.70.

**Design note:** no fixed confidence threshold in the headline (calibrated confidence maxes ~0.71,
so any 0.8 gate is meaningless). The trap eval uses the shipped calibration map for the reported
mean-confidence figures only.

---

## [Phase 3] Re-run on Sonnet exposed eval-methodology bugs; fixed before trusting numbers

**Context:** Budget was raised, so Phase 3 was re-run on Sonnet 4.6 (the demo model) at K=5 over 240
of a 300-question pool. Reading the first Sonnet aggregate critically surfaced three flaws that made
the headline numbers misleading. All were fixed by re-aggregating the saved records (no new API).

1. **Calibration split was distribution-shifted.** Records arrive grouped by database; a sequential
   train/test split fit on some DBs and tested on others, so isotonic calibration appeared to make
   ECE *worse* (0.11 -> 0.17). Fix: shuffle (seeded) before the split. With an i.i.d. split,
   calibration clearly helps: **ECE 0.439 -> 0.149, Brier 0.422 -> 0.252**.
2. **Confidence scores were runtime-contaminated.** The probe wrote a 10-question calibration map
   that the rest of the run then applied, so `confidence_score` in records was inconsistent. Fix:
   compute all metrics from `confidence_raw` and apply calibration post-hoc in aggregation.
3. **We were about to ship a map that could hurt.** The harness wrote the isotonic map
   unconditionally. Fix: ship it only if it beats raw on the held-out split; otherwise keep raw
   (identity). It shipped here because it genuinely improves calibration.

**Honest finding (not a bug):** self-consistency agreement is a weak raw signal on BIRD — 215/240
questions reach full agreement (raw 1.0) despite 56% accuracy. The model is confidently consistent
even when wrong, so raw confidence is badly over-confident (ECE 0.44); calibration is what makes the
displayed confidence honest. Consequently "confidently-wrong at threshold 0.8 = 0" is a calibration
artifact (calibrated confidence rarely reaches 0.8), not the trust layer catching errors — so we
report the threshold **sweep** (0.6: 0.43 -> 0.36) and headline the calibration improvement, not a
"100% reduction".

**Added:** `--reaggregate` (recompute metrics from saved records + labeled results, no API) and
`--cost` (record true total spend; per-process token tracking under-counts a resumed run).

---

## [Phase 3] build_schema_card must quote table names (reserved words like `order`)

**Context:** The paid BIRD run crashed in `build_schema_card` on a database with a table named
`order`: `PRAGMA table_info(order)` is a syntax error. Olist has no reserved-word table names, so
Phase 1 never hit it; the eval over 11 diverse BIRD schemas surfaced it.

**Fix:** quote the table name in both PRAGMA calls — `PRAGMA table_info("{table}")` with embedded
quotes doubled. Verified by building schema cards for all 11 BIRD DBs (613-6430 chars each, which
also confirms the deferred-retrieval decision: the cards fit). The runner is resumable, so the 43
records completed before the crash were preserved and the rerun finished the remaining 57.

---

## [Phase 3] Tests must not depend on the committed calibration artifact

**Context:** Once `eval/out/calibration.json` was committed, `load_calibration_map` started
returning `calibrated=True`, which flipped a Phase 2 endpoint test that asserted
`confidence.calibrated is False`.

**Fix:** `test_settings.calibration_path` points at a path that never exists, so confidence in
tests is deterministically uncalibrated regardless of whether a real map is committed. Tests assert
behavior, not the presence of an eval output.

---

## [Phase 3] Eval cost is per-process; a resumed run under-reports total spend

`AnthropicClient` accumulates token usage on the instance, so `estimated_cost_usd` in
`eval_results.json` reflects only the final process's calls. After a crash + resume, the reported
$0.44 covers the resumed 57 questions; the full 100-question run cost ~$1-2 total. The `--max-cost`
guard is also per-process. Acceptable for a budget guardrail; noted so the committed cost field is
not mistaken for the all-in total.

---

## [Phase 1] anthropic SDK 0.107.1 structured-output shape — verified

**Context:** Phase 1 generation uses structured outputs to avoid fragile parsing of SQL
out of free text. The plan flagged that the SDK API could vary by version.

**Findings (verified against the installed 0.107.1):**
- `client.messages.parse(...)` exists and accepts `output_format=<PydanticModel>`,
  `system`, `messages`, `temperature`, `thinking`.
- The parsed object is read via the `ParsedMessage.parsed_output` property
  (`Optional[T]`); it walks the content blocks and returns the first parsed text block.
- No fallback to `output_config` was needed. `AnthropicClient.generate_structured`
  raises `LLMError` if `parsed_output` is `None`.

**Design:** the pipeline depends on a narrow `LLMClient` Protocol with a single
`generate_structured(...)` method, not on `anthropic.Anthropic` directly. The real
adapter and the test `FakeLLMClient` both satisfy it, so mypy strict passes and tests
spend no tokens.

---

## [Phase 1] Server must not import the anthropic SDK at startup

**Context:** the 4 GB ceiling and the idle-RSS test (5.6 MB) depend on the server process
staying lean.

**Decision:** `llm.py` imports `anthropic` only under `TYPE_CHECKING` and lazily inside
`build_client()`. `main.py` imports the `LLMClient` Protocol (light) and the pipeline, not
the SDK. Result: idle server RSS stays at **5.6 MB** with `/ask` wired in. If a future change
imports `anthropic` at module top-level, the RSS test will still pass (the SDK is light) but
keep the lazy import to preserve headroom for fastembed in Phase 3.

---

## [Phase 0] sqlglot 25 AST root types — verified by running `uv run --with sqlglot`

**Context:** The SQL validator in `execute.py` uses sqlglot to parse incoming queries and
reject anything that is not a safe SELECT. Choosing the wrong type names would silently
pass dangerous queries.

**Findings:**

| SQL input | sqlglot root type |
|---|---|
| `SELECT 1` | `exp.Select` |
| `WITH cte AS (SELECT 1) SELECT * FROM cte` | `exp.Select` (NOT `exp.With`) |
| `INSERT INTO t VALUES (1)` | `exp.Insert` |
| `DROP TABLE t` | `exp.Drop` |
| `CREATE TABLE t (x INT)` | `exp.Create` |
| `ALTER TABLE t ADD COLUMN y TEXT` | `exp.Alter` (NOT `exp.AlterTable`) |
| `ATTACH DATABASE 'x.db' AS x` | `exp.Attach` (NOT `exp.Command`) |
| `PRAGMA key=value` | `exp.Pragma` (NOT `exp.Command`) |
| `SELECT 1; SELECT 2` | `[exp.Select, exp.Select]` — list length 2 |
| `SELECT load_extension('x')` | `exp.Select` with `exp.Anonymous` child |

**CTE root type is `exp.Select`, not `exp.With`.** The WITH clause is stored in
`stmt.args["with"]` as a child node. A single `isinstance(stmt, exp.Select)` check
covers both plain SELECTs and CTEs. No special branch needed.

**Multi-statement detection:** use `sqlglot.parse()` (plural), not `sqlglot.parse_one()`.
`parse_one` silently discards everything after the first statement. `parse()` returns a
list; asserting `len == 1` is the correct multi-statement guard.

**`ATTACH` and `PRAGMA`** are distinct typed nodes, not caught by `exp.Command`. Both
must be in the explicit forbidden-types tuple.

---

## [Phase 0] sqlglot Limit node stores its value under `expression`, not `this`

**Context:** The LIMIT clamp (reduce a user-supplied `LIMIT 9999` down to 500) read the
limit value from the wrong arg and silently never fired. A test caught it.

**Finding:** For `SELECT 1 LIMIT 9999`, the AST is `Limit(expression=Literal(this=9999))`.
The numeric value is at `limit_node.args["expression"]`, and `limit_node.args["this"]` is
`None`. The correct access is:

```python
limit_value = existing_limit.args.get("expression")
if isinstance(limit_value, exp.Literal) and limit_value.is_number:
    if int(limit_value.this) > default_limit:
        statement = statement.limit(default_limit)
else:
    statement = statement.limit(default_limit)   # fail safe: unknown limit -> cap
```

**Why it matters:** Without the clamp, a generated query could request an unbounded row
count, threatening the row-cap and memory guarantees. The clamp now also fails safe: any
limit that is not a plain numeric literal is replaced with the cap.

---

## [Phase 0] sqlglot round-trip DROPS named-column table aliases (e.g. `WITH r(n) AS ...`)

**Context:** The validator re-emits every query via `statement.sql()` to inject the LIMIT.
A timeout test used `WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL ...)`. After the round-trip
the `(n)` column list was gone, sqlglot logged `WARNING ... Named columns are not supported
in table alias`, and SQLite then failed with `no such column: n`.

**Finding:** sqlglot's SQLite generator does not preserve column names declared on a table
alias / CTE name. Define CTE columns inside the body instead:

```sql
-- dropped by round-trip:
WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n < 1000)  SELECT ...
-- survives round-trip:
WITH RECURSIVE r AS (SELECT 1 AS n UNION ALL SELECT n+1 FROM r WHERE n < 1000) SELECT ...
```

**Why it matters (carry into Phase 1):** because the validator round-trips SQL through
sqlglot, any construct sqlglot cannot faithfully regenerate will be silently altered before
execution. Generated SQL should be canonicalized/validated against this round-trip, and the
generation prompt should avoid named-column aliases. Watch for other lossy round-trips when
wiring real generation.

---

## [Phase 0] sqlglot `.limit()` returns a new node — do not mutate in place

**Context:** LIMIT injection modifies the parsed AST before converting back to SQL.

**Finding:** `exp.Select.limit(n)` returns a **new** `Select` node; it does not mutate
the receiver. The result must be reassigned:

```python
# wrong — silently discards the limit
statement.limit(default_limit)
return statement.sql(dialect="sqlite")

# correct
statement = statement.limit(default_limit)
return statement.sql(dialect="sqlite")
```

This was verified: calling `.limit(500)` on a CTE correctly emits
`WITH c AS (...) SELECT ... LIMIT 500` when the result is reassigned.

---

## [Phase 0] sqlglot pin rationale — `>=25.0,<26`

**Context:** sqlglot has historically made breaking AST changes between minor versions.

**Decision:** Pin `sqlglot>=25.0,<26` in `pyproject.toml`. The validator tests for
`ATTACH` and `PRAGMA` rejection serve as regression guards: if a version bump renames
those AST nodes, the tests will catch it before the change reaches production.

---

## [Phase 0] Geolocation table has no single-column primary key

**Context:** The `olist_geolocation_dataset.csv` has multiple rows per zip code prefix
(different lat/lng centroids for the same zip). It cannot have a primary key on
`geolocation_zip_code_prefix` alone.

**Decision:** Use SQLite's implicit rowid table (no explicit PRIMARY KEY declaration).
Add an index on `geolocation_zip_code_prefix` for join performance. Do not attempt to
deduplicate — the raw data is kept as-is.

**Consequence for SQL generation (Phase 1+):** queries joining on zip code prefix will
return multiple rows per zip. The schema card must document this so the LLM does not
assume a 1-to-1 relationship.

---

## [Phase 0] Olist column name typos — preserve exactly

**Context:** The original Olist dataset has two misspelled column names in the products
table: `product_name_lenght` and `product_description_lenght` (should be "length").

**Decision:** Preserve the typos exactly. The schema card, semantic layer, and all
generated SQL must match the actual column names in `demo.db`. Correcting them would
create a silent mismatch between the schema card and the database.

---

## [Phase 0] pandas isolated to `data` dependency group — never in server

**Context:** The 4 GB RAM constraint prohibits pandas in the server process. pandas
alone adds ~150 MB RSS on import.

**Decision:** pandas is declared in `[dependency-groups] data` in `pyproject.toml`,
not in `[project] dependencies`. This makes the boundary explicit and tool-enforced.
mypy's `exclude` list covers `data/` and `eval/` so these offline scripts are not
type-checked under strict mode.

**Runtime enforcement:** `backend/tests/test_server_rss.py` measures actual RSS of the
running uvicorn process. If pandas (or any large library) is accidentally imported, the
RSS test will catch it. Measured idle RSS at Phase 0: **5.6 MB** (limit 4096 MB).

---

## [Phase 0] Verified row counts in demo.db (pandas-truth, not `wc -l`)

`wc -l` overcounts the review and other text tables because review comments contain embedded
newlines inside quoted fields. The real row counts after load:

| table | rows |
|---|---|
| product_category_name_translation | 73 (71 from CSV + 2 seeded) |
| customers | 99,441 |
| sellers | 3,095 |
| products | 32,951 |
| orders | 99,441 |
| order_items | 112,650 |
| order_payments | 103,886 |
| order_reviews | 99,224 |
| geolocation | 1,000,163 |

`verify()` therefore asserts only non-zero counts plus a clean `PRAGMA foreign_key_check`,
not exact line-count matches.

---

## [Phase 0] `make` is not on PATH on Windows

The Makefile is the canonical interface for the verification gates and works in CI and on
Unix. On this Windows dev box `make` is not installed, so run the underlying commands the
Makefile documents directly, e.g. `uv run pytest backend/tests/ -v -s`,
`uv run ruff check backend/ data/`, `uv run mypy backend/`.
