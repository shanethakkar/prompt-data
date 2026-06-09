# Verity — Decisions and Findings

Lightweight record of non-obvious implementation discoveries, API quirks, and
architectural choices made during the build. Each entry explains the context,
what was found or decided, and why it matters for future work.

When to add an entry: any time something would have surprised you if you had not
already discovered it, or any time a choice was made between real alternatives.
Do not record things that are obvious from the code or spec.

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
RSS test will catch it.
