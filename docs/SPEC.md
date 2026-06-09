# Verity — Trust-Layer Analytics Copilot

> Working name: **Verity**. Rename in one place (CLAUDE.md product line and the frontend brand token) if you want something else.

This is the build specification. It is written to be read by Claude Code. Put it at `docs/SPEC.md` and reference it from `CLAUDE.md`. Build it phase by phase. Do not skip the trust layer or the eval harness; they are the entire point of the project.

---

## 1. North star

Verity is a natural-language-to-SQL analytics copilot whose differentiator is **trust**, not query generation. Generating SQL is a solved, crowded category. What is not solved is making the answer trustworthy for a non-technical user: knowing when a question is ambiguous, stating the assumptions made, attaching a calibrated confidence signal, and measuring how often the system is *confidently wrong*.

A user asks a question in plain English about the Olist e-commerce database. Verity either answers, with the SQL, the assumptions it made, a confidence signal, and the grounding rows, or it asks a clarifying question instead of guessing. Every claim Verity makes about its own quality is backed by a reproducible benchmark, never asserted.

The build is finished when three artifacts exist and are deployed:
1. A polished frontend a recruiter can click through in 60 seconds.
2. A live eval dashboard rendering real, reproducible metrics.
3. A documented limitations page listing the failure modes it cannot catch.

---

## 2. The thesis (do not lose this)

Every feature serves one of these four trust behaviors. If a proposed feature does not, it is out of scope for v1.

1. **Ambiguity detection.** Detect underspecified questions and ask a clarifying question instead of guessing. Do not over-ask on clear questions.
2. **Assumption surfacing.** When proceeding without clarifying, state the concrete assumptions made: which column maps to which business term, the time grain, the filters applied.
3. **Calibrated confidence.** Produce a confidence score that actually tracks correctness. When Verity says 85% confident, it should be right about 85% of the time.
4. **Measured honesty.** Quantify the *semantic-error rate*, queries that execute successfully but answer the wrong question, and show how the trust layer reduces the confidently-wrong subset.

---

## 3. Hard constraints (non-negotiable)

- **Memory: the running local server must not exceed 4 GB RAM.** Enforced by these choices: all LLM inference via the Anthropic API, no local model weights in the server process; embeddings via a small ONNX model through `fastembed`, never PyTorch or `transformers`, in the server process; the demo database is SQLite, queried with SQL, never loaded wholesale into pandas in the server; display result sets are row-capped; the eval harness runs as a **separate offline batch process**, not inside the live server, and processes benchmark databases one at a time releasing memory between each. Run a single uvicorn worker. Verify by measuring the server process RSS under load and confirming it stays below 4096 MB; record the observed peak in the README.
- **Read-only, SELECT-only execution.** Open SQLite read-only. Parse every generated query and reject anything that is not a single read-only `SELECT`/CTE. Inject a `LIMIT` and a statement timeout. This validator is the real prompt-injection backstop: regardless of what the model emits, only a read-only SELECT ever reaches the database.
- **No fabricated metrics.** Every number on the eval dashboard, in the methodology page, and in any README claim must be produced by the eval harness from a real run. If a metric has not been measured, it does not appear.
- **No em dashes in user-facing copy.** Use commas, colons, or semicolons. Keep product copy plain and direct.

---

## 4. Tech stack

- **Frontend:** Next.js 16 (App Router), React 19, TypeScript strict mode, Tailwind CSS v4 with CSS-first `@theme` tokens. Charts are hand-built React + SVG primitives, no chart library. Match the existing portfolio aesthetic (see Section 9).
- **Backend:** Python 3.12, FastAPI, single-worker uvicorn. This is the brain: schema retrieval, SQL generation, trust layer, execution sandbox.
- **LLM:** Anthropic API. Use model tiers, not a single model (see Section 10 routing). Confirm current model strings at https://docs.claude.com/en/docs/about-claude/models. As of writing, the tiers are Haiku 4.5 (fast/cheap), Sonnet 4.6 (balanced), Opus 4.x (strongest).
- **Embeddings:** `fastembed` with a small model such as `BAAI/bge-small-en-v1.5` (ONNX, CPU, low RAM). Store schema embeddings in `sqlite-vec`, or in-memory NumPy cosine since schemas are small.
- **Database:** SQLite for the Olist demo DB and for the BIRD benchmark DBs. External Postgres/MySQL read-only connections for the optional bring-your-own-DB mode.
- **Eval data:** BIRD dev set (SQLite-based, self-contained, hard) as the primary benchmark. Spider 2.0-lite local subset is an optional stretch. Do **not** target Spider 2.0 full; it requires live BigQuery/Snowflake connections and breaks the memory and self-containment constraints.
- **Deploy:** Frontend on Vercel. Backend on a small always-on host (Render, Railway, or Fly) sized at or under the 4 GB ceiling.

---

## 5. Repository structure

```
verity/
  CLAUDE.md                  # project conventions, <200 lines, see Section 14
  docs/
    SPEC.md                  # this file
    methodology.md           # source for the /methodology page
    limitations.md           # source for the /limitations page
  backend/
    app/
      main.py                # FastAPI app, routes, streaming
      pipeline/
        schema.py            # introspection, schema card, retrieval
        generate.py          # SQL generation + self-correction loop
        execute.py           # read-only sandbox + SQL validator
        ambiguity.py         # ambiguity detection + clarifying questions
        assumptions.py       # assumption extraction
        confidence.py        # self-consistency + calibration application
        route.py             # model routing + cost tracking
      semantic_layer.py      # business-term to column/metric definitions
    tests/
  eval/                      # OFFLINE batch, not imported by the server
    run_bird.py              # benchmark runner, memory-bounded
    metrics.py               # exec accuracy, semantic-error, calibration, clarification
    ablation.py              # with vs without trust layer
    calibrate.py             # fit isotonic regression, emit calibration map
    out/                     # eval_results.json, calibration.json, charts/
  data/
    raw/                     # Olist CSVs and BIRD dev set go here (gitignored)
    load_olist.py            # CSVs -> data/demo.db
    demo.db                  # generated, gitignored
  frontend/
    app/
      page.tsx               # /ask
      gallery/page.tsx       # /gallery (trap questions)
      evals/page.tsx         # /evals (dashboard)
      methodology/page.tsx
      limitations/page.tsx
      connect/page.tsx       # optional, staged
    components/
    lib/
```

Backend and eval share no live state. The eval `out/` JSON is the only thing the frontend `/evals` page consumes, copied or fetched as static data.

---

## 6. Data layer

- `data/load_olist.py` reads the nine Olist CSVs from `data/raw/` and writes `data/demo.db` (SQLite) with proper foreign keys and indexes on join columns. The script is idempotent: re-running drops and rebuilds cleanly. Do not assume network access; the CSVs are downloaded manually by the user into `data/raw/`.
- `semantic_layer.py` defines a small mapping of business terms to columns and metrics so vague language resolves correctly. Examples: "revenue" maps to `order_items.price` summed, "spend" includes freight, "a customer" resolves via `customer_unique_id` not `customer_id`, "delivered" maps to `order_status = 'delivered'`. The semantic layer is consulted during generation and its resolutions become the surfaced assumptions. Keep it as a readable, documented config, not buried in prompts.
- A generated **schema card** describes each table, column, type, foreign keys, and a one-line description, used both in prompts and as the retrieval corpus.

---

## 7. Core pipeline (happy path)

1. **Schema context.** If the full schema card fits under a token budget, put all of it in the prompt. Otherwise retrieve the top-k relevant tables and columns via `fastembed` similarity against the question. The Olist demo always fits; retrieval matters for BIRD and bring-your-own.
2. **Generation.** Generate a single read-only SELECT given the question, schema context, and semantic-layer resolutions.
3. **Validation and execution.** Pass through the SELECT-only validator, inject LIMIT and timeout, execute read-only against the connection, return rows.
4. **Self-correction.** On execution error, feed the error back to the model once or twice to repair, capped to avoid loops. Record whether self-correction fired; it is a confidence signal.
5. **Presentation.** Return the answer, the SQL, the result rows, a suggested chart type, and the assumptions and confidence from the trust layer.

---

## 8. Trust layer (the differentiator)

**Ambiguity detection (`ambiguity.py`).** Before committing to a final query, classify the question across dimensions: ambiguous metric definition, ambiguous or relative time window, entity-resolution ambiguity, aggregation grain, and answerability against the schema. If ambiguity on any dimension exceeds a threshold, return a targeted clarifying question rather than an answer. Two failure modes to balance and both are measured in Section 11: failing to ask when you should, and over-asking on clear questions.

**Clarifying questions.** When triggered, generate one concrete, minimal clarifying question with selectable options where possible, for example "by total revenue or by number of orders" and "calendar or fiscal quarter." The frontend renders these as tappable chips that feed the answer back into the pipeline.

**Assumption surfacing (`assumptions.py`).** When Verity proceeds, extract the concrete assumptions it made as a structured object: term-to-column mappings, time grain, filters, and the join path. Rendered explicitly in the UI.

**Confidence via self-consistency (`confidence.py`).** Sample K generations at nonzero temperature, K around 5. Execute or canonicalize each and measure agreement of the result sets. Agreement fraction, combined with whether self-correction fired and the retrieval score, forms a raw confidence. Then apply a **calibration map** fit offline by `eval/calibrate.py` (isotonic regression on a held-out BIRD split) so the displayed confidence tracks observed accuracy. The server loads the static calibration map; it does not fit anything at request time.

---

## 9. Frontend (fully fleshed out)

Match the existing portfolio design language for brand consistency: dark theme on a near-black canvas around `#0c0c0e`, warm off-white text, a single cyan accent around `#22d3ee`, Geist Sans for headings and body, Geist Mono for labels and nav, depth cards with soft shadows and a subtle accent halo on hover, all charts as hand-built SVG. Accessible throughout: semantic HTML, ARIA labels on chart SVGs, full keyboard navigation, `prefers-reduced-motion` honored. Mobile-first responsive.

**/ask (home).** The primary surface.
- Question input with a few suggested starter questions.
- A conversation thread supporting the clarify-then-answer flow.
- The **answer card** is the centerpiece: the plain-English answer, a hand-built SVG chart appropriate to the result, a sortable result table, the generated SQL with syntax highlighting and a copy button, an **Assumptions** panel listing the structured assumptions, a **Confidence** badge with a one-line explanation of what drove it, and a collapsible **grounding** view showing the source rows.
- When the pipeline asks for clarification, render the clarifying question with tappable option chips instead of an answer card.
- Stream the response; show meaningful loading states per stage rather than one spinner.

**/gallery (trap questions, the killer demo).** A curated showcase of the questions that break naive copilots, each rendered as a side-by-side contrast: a "naive copilot" pane that produces a plausible but wrong answer, and the Verity pane that catches it. Categories to cover, roughly eight to twelve cards total: ambiguous metric, relative or ambiguous time window, an unanswerable question whose column does not exist, a hard multi-join, an aggregation-grain trap, a prompt-injection attempt, and an entity-ambiguity case. Each card documents the behavior; the naive outputs are precomputed and stored, not generated live.

**/evals (dashboard).** Renders real metrics from `eval/out/`.
- Metric cards: execution accuracy on BIRD, semantic-error rate, confidently-wrong rate, calibration error.
- A reliability diagram (hand-built SVG) plotting predicted confidence against observed accuracy.
- The trust-layer ablation as a bar comparison: confidently-wrong rate with the trust layer versus without.
- Clarification precision and recall.
- Cost and latency, broken down by model-routing tier.

**/methodology.** Long-form writeup rendered from `docs/methodology.md`, audit-defensible, explaining each trust behavior, the eval design, and how the calibration map is fit.

**/limitations.** Rendered from `docs/limitations.md`. The honest page: failure classes Verity cannot catch, where confidence is least calibrated, the semantic errors that still slip through, and the known ambiguity false-negatives.

**/connect (optional, staged to Phase 6).** Upload a SQLite file or enter a read-only connection string, preview the inferred schema card, then ask questions against it. Showcases schema robustness on input the system has not seen.

---

## 10. Production touches

- **Model routing (`route.py`).** Route a fast cheap model for straightforward SQL generation and a stronger model for ambiguity detection and complex or self-correcting cases. Track token cost per request and expose the aggregate on the dashboard. Measure and document the cost-versus-accuracy tradeoff of the routing.
- **Prompt-injection defense.** Treat the user question strictly as data. The SELECT-only validator is the hard backstop. Include adversarial questions in the trap gallery and confirm the validator blocks them.
- **Bring-your-own-DB (staged).** Read-only connection, schema-card inference via the same code path as Olist, retrieval-based schema context for large schemas.

---

## 11. Eval harness (offline batch)

Runs outside the server with one command and stays within the memory budget by loading one benchmark database at a time. Outputs JSON and SVG-ready data to `eval/out/`.

Metrics:
- **Execution accuracy.** Fraction of questions whose result set matches gold. Table stakes.
- **Semantic-error rate.** Fraction that execute successfully but return the wrong result. This is the headline trust metric.
- **Confidently-wrong rate, with and without the trust layer.** The ablation. Without the trust layer, count semantic errors emitted with high confidence. With the trust layer, count how many of those convert to a clarifying question or an explicit low-confidence flag versus how many still slip through confidently. The reduction is the project's signature number.
- **Calibration.** Expected Calibration Error and Brier score, plus the reliability-diagram data. `calibrate.py` fits the isotonic map on a held-out split; `metrics.py` evaluates calibration on the test split.
- **Clarification precision and recall.** Against a hand-labeled set: all trap questions plus a labeled sample of BIRD questions tagged clear or ambiguous. Penalize over-asking on clear questions.
- **Cost and latency** per routing tier.

Determinism: pin the eval question set, fix seeds where possible, and commit the resulting `eval_results.json` so the dashboard and README claims are reproducible.

---

## 12. Build phases

Build in order. Each phase ends with a passing verification gate (lint, type-check, build, tests) and a commit. Use plan mode at the start of each phase.

- **Phase 0, scaffold and safety floor.** Monorepo, CLAUDE.md, env config, `load_olist.py` producing `demo.db`, and the read-only SELECT-only execution sandbox with its validator. Done when a hardcoded SELECT runs through the sandbox, any non-SELECT is rejected, and idle server RSS is recorded.
- **Phase 1, core text-to-SQL.** Schema card and retrieval, generation, validation, execution, self-correction. Done when a set of straightforward Olist questions answer correctly end to end via an API or CLI call.
- **Phase 2, trust layer.** Ambiguity detection and clarifying questions, assumption extraction, self-consistency confidence, and application of a placeholder calibration map. Done when an ambiguous question triggers a clarifying question and a clear one returns an answer with assumptions and a confidence signal.
- **Phase 3, eval harness.** BIRD runner, all metrics, the trust-layer ablation, the fitted calibration map, cost and latency, JSON output. Done when one command produces `eval_results.json` within the memory budget and the numbers are reproducible. Wire the real calibration map back into the server.
- **Phase 4, frontend core.** The /ask page with the full answer card, the clarify-then-answer flow, streaming, and the design system. Done when the demo DB is fully usable through the browser.
- **Phase 5, showcase pages.** /gallery, /evals reading Phase 3 output, /methodology, /limitations. Done when all four render and the gallery contrast and dashboard metrics are real.
- **Phase 6, production and polish.** Model routing and cost tracking, prompt-injection hardening verified against the gallery, optional bring-your-own-DB, accessibility and mobile sweep, deploy, README with the measured headline numbers and the verified peak RSS.

---

## 13. Definition of done

The deployed project produces these, all measured, none asserted:
- Execution accuracy on BIRD dev.
- Semantic-error rate, and the confidently-wrong-rate reduction attributable to the trust layer.
- Calibration error (ECE and Brier) with a reliability diagram.
- Clarification precision and recall.
- Cost and latency per routing tier.
- A verified server peak RSS under 4096 MB.

These become the resume bullets. Phrase them as the trust-layer wins, for example the confidently-wrong reduction and the calibration error, not as a bare accuracy number.

---

## 14. CLAUDE.md template

Create this at the repo root. Keep it under 200 lines. Refine as the build proceeds.

```markdown
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
- Load demo DB:  python data/load_olist.py
- Run backend:   uvicorn backend.app.main:app --workers 1
- Run frontend:  cd frontend && npm run dev
- Run eval:      python eval/run_bird.py
- Gates:         ruff + mypy (backend), tsc --noEmit + eslint + next build (frontend), pytest

## Conventions
- Python-first. Pure functions for pipeline math; DB I/O isolated for testability.
- Match the existing portfolio design: dark theme, cyan accent, Geist fonts, SVG charts.
- Commit per phase. Run all gates before committing.

## Workflow
- Start each phase in plan mode. Read docs/SPEC.md and the target phase, produce a
  plan, wait for approval, then implement.
- Keep this file small; link to docs/ for detail.

## Docs
- Claude Code: https://docs.claude.com/en/docs/claude-code/overview
- Models: https://docs.claude.com/en/docs/about-claude/models
```

---

## 15. How to execute with Claude Code

1. Create an empty repo and drop this file at `docs/SPEC.md`. Download the Olist CSVs and the BIRD dev set into `data/raw/`.
2. Create `CLAUDE.md` from the Section 14 template before anything else, since `/init` is not useful on an empty repo.
3. Work one phase at a time. For each phase, enter plan mode, point Claude Code at `docs/SPEC.md` and the specific phase, review and edit the plan, then let it implement.
4. Run the verification gates after each phase and commit before moving on. Keep the trust layer central; if a plan drifts toward generic text-to-SQL, redirect it back to Section 2.
